"""Olwen.app — native macOS shell hosting the full Olwen dashboard.

Two pieces in one process:
  • Bridge daemon (FastAPI on 127.0.0.1:8765) for mouse / keyboard / screen
  • WKWebView pointing at the Olwen frontend (default http://localhost:3100)

You get the exact same UI as the website, in a real Mac window, plus the
bridge already plugged in so Computer-Use works out of the box. Choose Web
or App — same dashboard either way.
"""
from __future__ import annotations

import collections
import os
import pathlib
import secrets
import socket
import sys
import threading
import time
from datetime import datetime

import objc  # type: ignore
from AppKit import (  # type: ignore
    NSApp,
    NSApplication,
    NSApplicationActivationPolicyRegular,
    NSBackingStoreBuffered,
    NSColor,
    NSFont,
    NSMakeRect,
    NSMenu,
    NSMenuItem,
    NSPasteboard,
    NSPasteboardTypeString,
    NSScreen,
    NSTextField,
    NSWindow,
    NSWindowStyleMaskClosable,
    NSWindowStyleMaskFullSizeContentView,
    NSWindowStyleMaskMiniaturizable,
    NSWindowStyleMaskResizable,
    NSWindowStyleMaskTitled,
)
from Foundation import NSObject, NSURL, NSURLRequest  # type: ignore
from PyObjCTools import AppHelper  # type: ignore
from WebKit import WKWebView, WKWebViewConfiguration  # type: ignore

# ── config ────────────────────────────────────────────────────────────
DASHBOARD_URL = os.getenv("OLWEN_DASHBOARD_URL", "http://localhost:3100")
PORT = 8765
HOME = pathlib.Path.home()
APP_DIR = HOME / ".olwen"
TOKEN_FILE = APP_DIR / "bridge.token"
LOG_RING = collections.deque(maxlen=60)
APP_DIR.mkdir(parents=True, exist_ok=True)


def _load_or_create_token() -> str:
    if TOKEN_FILE.exists():
        return TOKEN_FILE.read_text().strip()
    t = secrets.token_urlsafe(48)
    TOKEN_FILE.write_text(t)
    TOKEN_FILE.chmod(0o600)
    return t


TOKEN = _load_or_create_token()


def _log(line: str) -> None:
    LOG_RING.append(f"{datetime.now().strftime('%H:%M:%S')}  {line}")


# ── bridge (runs in worker thread) ───────────────────────────────────
def _start_bridge() -> None:
    import io as _io
    import uvicorn
    from fastapi import Body, Depends, FastAPI, Header, HTTPException, Response
    from mss import mss
    from PIL import Image
    import pyautogui
    from pydantic import BaseModel, Field

    pyautogui.FAILSAFE = False
    pyautogui.PAUSE = 0.0
    api = FastAPI(title="Olwen Bridge", version="0.1.0")

    def auth(authorization: str | None = Header(default=None)) -> None:
        if not authorization or not authorization.lower().startswith("bearer "):
            raise HTTPException(401, "missing token")
        if not secrets.compare_digest(authorization.split(" ", 1)[1].strip(), TOKEN):
            raise HTTPException(401, "bad token")

    class MoveIn(BaseModel):
        x: int = Field(ge=0); y: int = Field(ge=0); duration: float = 0.15
    class ClickIn(BaseModel):
        x: int | None = None; y: int | None = None
        button: str = "left"; count: int = 1; interval: float = 0.05
    class TypeIn(BaseModel):
        text: str = Field(min_length=1, max_length=10_000); interval: float = 0.01
    class PressIn(BaseModel):
        keys: list[str] = Field(min_length=1, max_length=8)
    class ScrollIn(BaseModel):
        dx: int = 0; dy: int = 0

    @api.get("/health")
    def health(_=Depends(auth)) -> dict:
        return {"ok": True, "version": "0.1.0"}

    @api.get("/screen")
    def screen(_=Depends(auth)) -> dict:
        w, h = pyautogui.size()
        return {"width": int(w), "height": int(h)}

    @api.get("/screenshot")
    def screenshot(_=Depends(auth)) -> Response:
        with mss() as sct:
            raw = sct.grab(sct.monitors[1])
            img = Image.frombytes("RGB", raw.size, raw.rgb)
        img.thumbnail((1568, 1568), Image.Resampling.LANCZOS)
        buf = _io.BytesIO(); img.save(buf, format="PNG", optimize=True)
        _log("📷 screenshot")
        return Response(buf.getvalue(), media_type="image/png")

    @api.post("/mouse/move")
    def m_move(b: MoveIn, _=Depends(auth)) -> dict:
        pyautogui.moveTo(b.x, b.y, duration=b.duration); _log(f"→ move ({b.x},{b.y})")
        return {"ok": True}

    @api.post("/mouse/click")
    def m_click(b: ClickIn = Body(...), _=Depends(auth)) -> dict:  # Body() forces JSON-body binding (all-optional models otherwise bind as query params on older FastAPI)
        kw = {"button": b.button, "clicks": b.count, "interval": b.interval}
        if b.x is not None and b.y is not None:
            pyautogui.click(b.x, b.y, **kw); _log(f"● {b.button} ({b.x},{b.y})")
        else:
            pyautogui.click(**kw); _log(f"● {b.button}")
        return {"ok": True}

    @api.post("/mouse/scroll")
    def m_scroll(b: ScrollIn = Body(...), _=Depends(auth)) -> dict:
        if b.dy: pyautogui.scroll(b.dy)
        if b.dx: pyautogui.hscroll(b.dx)
        _log(f"⇅ scroll dy={b.dy}")
        return {"ok": True}

    @api.post("/key/type")
    def k_type(b: TypeIn, _=Depends(auth)) -> dict:
        pyautogui.typewrite(b.text, interval=b.interval)
        _log(f'⌨  "{b.text[:36]}{"…" if len(b.text)>36 else ""}"')
        return {"ok": True}

    @api.post("/key/press")
    def k_press(b: PressIn, _=Depends(auth)) -> dict:
        aliases = {"cmd": "command", "super": "command", "meta": "command"}
        keys = [aliases.get(k.lower(), k.lower()) for k in b.keys]
        pyautogui.hotkey(*keys); _log(f"⌘ {'+'.join(keys)}")
        return {"ok": True}

    @api.post("/stop")
    def stop() -> dict:
        _log("⏹ STOP"); return {"ok": True}

    # ── accessibility (semantic UI control — find/act on real elements) ──
    from AppKit import NSWorkspace  # type: ignore
    try:
        from ApplicationServices import (  # type: ignore
            AXIsProcessTrusted, AXUIElementCopyAttributeValue,
            AXUIElementCreateApplication, AXUIElementPerformAction,
            AXUIElementSetAttributeValue,
        )
        _AX_OK = True
    except Exception:  # noqa: BLE001
        _AX_OK = False

    def _axnorm(s):
        s = str(s) if s is not None else ""
        for ch in ("‎", "‏", "‪", "‬"):
            s = s.replace(ch, "")
        return s.replace(" ", " ").strip()

    def _axattr(el, n):
        e, v = AXUIElementCopyAttributeValue(el, n, None); return v if e == 0 else None

    def _axresolve(q):
        q = (q or "").lower().strip(); best = None
        for a in NSWorkspace.sharedWorkspace().runningApplications():
            nm = _axnorm(a.localizedName()).lower(); bid = (a.bundleIdentifier() or "").lower()
            if q and (q == nm or q == bid):
                return a
            if q and (q in nm or q in bid):
                best = best or a
        return best

    def _axdesc(el):
        return {"role": _axnorm(_axattr(el, "AXRole")), "title": _axnorm(_axattr(el, "AXTitle")),
                "desc": _axnorm(_axattr(el, "AXDescription")),
                "placeholder": _axnorm(_axattr(el, "AXPlaceholderValue")),
                "value": _axnorm(_axattr(el, "AXValue"))[:160]}

    def _axcollect(root, maxd=18, cap=6000):
        out = []; st = [(root, 0)]
        while st and len(out) < cap:
            el, d = st.pop()
            if el is None or d > maxd:
                continue
            out.append((el, _axdesc(el)))
            for k in reversed(list(_axattr(el, "AXChildren") or [])):
                st.append((k, d + 1))
        return out

    _SELK = ("role", "title", "desc", "title_contains", "desc_contains",
             "placeholder_contains", "value_contains")

    def _axmatch(dd, sel):
        if sel.get("role") and dd["role"] != sel["role"]:
            return False
        if sel.get("title") and dd["title"] != sel["title"]:
            return False
        if sel.get("desc") and dd["desc"] != sel["desc"]:
            return False
        for f, k in (("title", "title_contains"), ("desc", "desc_contains"),
                     ("placeholder", "placeholder_contains"), ("value", "value_contains")):
            w = sel.get(k)
            if w and w.lower() not in dd[f].lower():
                return False
        return True

    class AxFind(BaseModel):
        app: str; role: str | None = None; title: str | None = None; desc: str | None = None
        title_contains: str | None = None; desc_contains: str | None = None
        placeholder_contains: str | None = None; value_contains: str | None = None
        limit: int = 40; activate: bool = False

    class AxAct(AxFind):
        action: str = "press"; nth: int = 0; value: str | None = None; activate: bool = True

    class AxActivate(BaseModel):
        app: str

    @api.get("/ax/apps")
    def ax_apps(_=Depends(auth)) -> dict:
        if not _AX_OK:
            raise HTTPException(503, "accessibility unavailable")
        return {"ok": True, "trusted": bool(AXIsProcessTrusted()),
                "apps": [{"name": _axnorm(a.localizedName()), "bundle": a.bundleIdentifier() or "",
                          "pid": int(a.processIdentifier())}
                         for a in NSWorkspace.sharedWorkspace().runningApplications()
                         if a.activationPolicy() == 0]}

    @api.get("/ax/frontmost")
    def ax_frontmost(_=Depends(auth)) -> dict:
        a = NSWorkspace.sharedWorkspace().frontmostApplication()
        return {"ok": True, "name": _axnorm(a.localizedName()) if a else "",
                "bundle": (a.bundleIdentifier() if a else "") or ""}

    @api.post("/ax/activate")
    def ax_activate(b: AxActivate = Body(...), _=Depends(auth)) -> dict:
        a = _axresolve(b.app)
        if a is None:
            raise HTTPException(404, "app not running")
        a.activateWithOptions_(2); return {"ok": True, "activated": _axnorm(a.localizedName())}

    @api.post("/ax/find")
    def ax_find(b: AxFind = Body(...), _=Depends(auth)) -> dict:
        if not _AX_OK:
            raise HTTPException(503, "accessibility unavailable")
        a = _axresolve(b.app)
        if a is None:
            raise HTTPException(404, "app not running")
        if b.activate:
            a.activateWithOptions_(2); time.sleep(0.6)
        sel = {k: getattr(b, k) for k in _SELK}
        nodes = _axcollect(AXUIElementCreateApplication(a.processIdentifier()))
        ms = [dd for _, dd in nodes if _axmatch(dd, sel)]
        return {"ok": True, "app": _axnorm(a.localizedName()), "count": len(ms), "matches": ms[:b.limit]}

    @api.post("/ax/act")
    def ax_act(b: AxAct = Body(...), _=Depends(auth)) -> dict:
        if not _AX_OK:
            raise HTTPException(503, "accessibility unavailable")
        sel = {k: getattr(b, k) for k in _SELK}
        if not any(sel.values()):
            raise HTTPException(422, "need at least one selector")
        a = _axresolve(b.app)
        if a is None:
            raise HTTPException(404, "app not running")
        if b.activate:
            a.activateWithOptions_(2); time.sleep(0.6)
        nodes = _axcollect(AXUIElementCreateApplication(a.processIdentifier()))
        matched = [(el, dd) for el, dd in nodes if _axmatch(dd, sel)]
        if not matched:
            raise HTTPException(404, "no element matched")
        nth = b.nth if 0 <= b.nth < len(matched) else 0
        el, dd = matched[nth]
        if b.action == "press":
            AXUIElementPerformAction(el, "AXPress")
        elif b.action == "focus":
            AXUIElementSetAttributeValue(el, "AXFocused", True)
        elif b.action == "set_value":
            AXUIElementSetAttributeValue(el, "AXValue", b.value or "")
        else:
            raise HTTPException(422, "bad action")
        return {"ok": True, "action": b.action, "matched": dd, "candidates": len(matched), "nth": nth}

    _log(f"bridge online → http://127.0.0.1:{PORT}")
    uvicorn.run(api, host="127.0.0.1", port=PORT, log_level="warning")


# ── AppKit window with WKWebView ─────────────────────────────────────
BG_DARK = NSColor.colorWithSRGBRed_green_blue_alpha_(2/255, 6/255, 10/255, 1.0)


class OlwenAppDelegate(NSObject):
    window = None
    webview = None
    status_label = None

    def applicationDidFinishLaunching_(self, _n) -> None:
        NSApp.setActivationPolicy_(NSApplicationActivationPolicyRegular)
        self._build_menu()
        self._build_window()

    def applicationShouldTerminateAfterLastWindowClosed_(self, _s) -> bool:
        # Close = hide. ⌘Q quits properly. Keeps bridge alive.
        return False

    # standard menu so ⌘Q + ⌘W + Edit shortcuts work
    def _build_menu(self) -> None:
        bar = NSMenu.alloc().init()
        app_item = NSMenuItem.alloc().init()
        bar.addItem_(app_item)
        NSApp.setMainMenu_(bar)
        app_menu = NSMenu.alloc().init()

        copy_token = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Copy bridge token", "copyToken:", ""
        )
        copy_token.setTarget_(self)
        app_menu.addItem_(copy_token)

        reload = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Reload dashboard", "reload:", "r"
        )
        reload.setTarget_(self)
        app_menu.addItem_(reload)

        app_menu.addItem_(NSMenuItem.separatorItem())

        quit_item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            "Quit Olwen", "terminate:", "q"
        )
        app_menu.addItem_(quit_item)
        app_item.setSubmenu_(app_menu)

    def _build_window(self) -> None:
        screen = NSScreen.mainScreen().frame()
        w = min(1280, int(screen.size.width * 0.86))
        h = min(820, int(screen.size.height * 0.86))
        x = int((screen.size.width - w) / 2)
        y = int((screen.size.height - h) / 2)

        mask = (
            NSWindowStyleMaskTitled
            | NSWindowStyleMaskClosable
            | NSWindowStyleMaskMiniaturizable
            | NSWindowStyleMaskResizable
            | NSWindowStyleMaskFullSizeContentView
        )
        win = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(x, y, w, h), mask, NSBackingStoreBuffered, False
        )
        win.setTitle_("Olwen")
        win.setTitlebarAppearsTransparent_(True)
        win.setBackgroundColor_(BG_DARK)
        win.setMinSize_((720, 520))
        self.window = win
        content = win.contentView()
        bounds = content.bounds()

        # ── WebView (fills whole window minus a slim bottom status bar) ──
        cfg = WKWebViewConfiguration.alloc().init()
        webview = WKWebView.alloc().initWithFrame_configuration_(
            NSMakeRect(0, 28, bounds.size.width, bounds.size.height - 28), cfg
        )
        webview.setAutoresizingMask_(2 | 16)  # width + height
        # Set base layer color via the underlying NSView so there's no white flash
        try:
            webview.setValue_forKey_(BG_DARK, "backgroundColor")
        except Exception:
            pass
        content.addSubview_(webview)
        self.webview = webview

        # ── bottom status bar (token + bridge state) ──
        status = NSTextField.labelWithString_(
            f"  ●  bridge online · 127.0.0.1:{PORT}    ⌘C  copy token    ⌘R  reload    ⌘Q  quit"
        )
        status.setFont_(NSFont.monospacedSystemFontOfSize_weight_(10.5, 0.0))
        status.setTextColor_(NSColor.colorWithSRGBRed_green_blue_alpha_(94/255, 234/255, 212/255, 0.85))
        status.setBackgroundColor_(NSColor.colorWithSRGBRed_green_blue_alpha_(4/255, 16/255, 26/255, 1.0))
        status.setDrawsBackground_(True)
        status.setFrame_(NSMakeRect(0, 0, bounds.size.width, 28))
        status.setAutoresizingMask_(2)  # width
        content.addSubview_(status)
        self.status_label = status

        self._load_dashboard()
        win.makeKeyAndOrderFront_(None)
        NSApp.activateIgnoringOtherApps_(True)

    def _load_dashboard(self) -> None:
        url = NSURL.URLWithString_(DASHBOARD_URL)
        if url is None:
            return
        req = NSURLRequest.requestWithURL_(url)
        self.webview.loadRequest_(req)

    @objc.IBAction
    def copyToken_(self, _s) -> None:
        pb = NSPasteboard.generalPasteboard()
        pb.clearContents()
        pb.setString_forType_(TOKEN, NSPasteboardTypeString)
        self.status_label.setStringValue_("  ✓  token copied to clipboard")
        AppHelper.callLater(1.6, self._reset_status)

    @objc.IBAction
    def reload_(self, _s) -> None:
        self.webview.reload_(None)

    def _reset_status(self) -> None:
        self.status_label.setStringValue_(
            f"  ●  bridge online · 127.0.0.1:{PORT}    ⌘C  copy token    ⌘R  reload    ⌘Q  quit"
        )


def main() -> None:
    th = threading.Thread(target=_start_bridge, daemon=True)
    th.start()
    # Wait briefly so the status label doesn't lie about bridge state
    for _ in range(40):
        try:
            with socket.create_connection(("127.0.0.1", PORT), timeout=0.1):
                break
        except OSError:
            time.sleep(0.1)

    app = NSApplication.sharedApplication()
    delegate = OlwenAppDelegate.alloc().init()
    app.setDelegate_(delegate)
    AppHelper.runEventLoop()


if __name__ == "__main__":
    main()
