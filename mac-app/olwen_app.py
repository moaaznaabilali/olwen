"""Olwen.app — a real macOS application that hosts the bridge with a native
PyObjC window so the user can see it running, copy the token, and quit.

The bridge daemon runs in a worker thread; the main thread owns the AppKit UI
(this is non-negotiable — AppKit must run on thread 0). The window lives in
the Dock and the menu bar like any other Mac app, and the close button hides
it (the bridge keeps running) — choose Quit Olwen from the menu to actually
stop the daemon.

Build into a .app with build.sh (uses py2app).
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
    NSBezelStyleRegularSquare,
    NSButton,
    NSColor,
    NSFont,
    NSImage,
    NSImageView,
    NSMakeRect,
    NSPasteboard,
    NSPasteboardTypeString,
    NSScrollView,
    NSTextField,
    NSTextView,
    NSWindow,
    NSWindowCloseButton,
    NSWindowStyleMaskClosable,
    NSWindowStyleMaskMiniaturizable,
    NSWindowStyleMaskResizable,
    NSWindowStyleMaskTitled,
    NSWindowStyleMaskFullSizeContentView,
)
from Foundation import NSObject  # type: ignore
from PyObjCTools import AppHelper  # type: ignore

# ── bridge embedded in-process ───────────────────────────────────────
PORT = 8765
HOME = pathlib.Path.home()
APP_DIR = HOME / ".olwen"
TOKEN_FILE = APP_DIR / "bridge.token"
LOG_RING_SIZE = 60
APP_DIR.mkdir(parents=True, exist_ok=True)

_action_log: collections.deque[str] = collections.deque(maxlen=LOG_RING_SIZE)


def _load_or_create_token() -> str:
    if TOKEN_FILE.exists():
        return TOKEN_FILE.read_text().strip()
    t = secrets.token_urlsafe(48)
    TOKEN_FILE.write_text(t)
    TOKEN_FILE.chmod(0o600)
    return t


TOKEN = _load_or_create_token()


def _log(line: str) -> None:
    stamp = datetime.now().strftime("%H:%M:%S")
    _action_log.append(f"{stamp}  {line}")


def _start_bridge() -> None:
    """Start uvicorn on 127.0.0.1:PORT in this thread."""
    import uvicorn
    from fastapi import Depends, FastAPI, Header, HTTPException, Response
    from mss import mss
    from PIL import Image
    import pyautogui
    from pydantic import BaseModel, Field
    import io as _io

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
        pyautogui.moveTo(b.x, b.y, duration=b.duration)
        _log(f"→ move ({b.x}, {b.y})")
        return {"ok": True}

    @api.post("/mouse/click")
    def m_click(b: ClickIn, _=Depends(auth)) -> dict:
        kw = {"button": b.button, "clicks": b.count, "interval": b.interval}
        if b.x is not None and b.y is not None:
            pyautogui.click(b.x, b.y, **kw); _log(f"● {b.button} click ({b.x}, {b.y})")
        else:
            pyautogui.click(**kw); _log(f"● {b.button} click")
        return {"ok": True}

    @api.post("/mouse/scroll")
    def m_scroll(b: ScrollIn, _=Depends(auth)) -> dict:
        if b.dy: pyautogui.scroll(b.dy)
        if b.dx: pyautogui.hscroll(b.dx)
        _log(f"⇅ scroll dy={b.dy}")
        return {"ok": True}

    @api.post("/key/type")
    def k_type(b: TypeIn, _=Depends(auth)) -> dict:
        pyautogui.typewrite(b.text, interval=b.interval)
        _log(f'⌨  type "{b.text[:36]}{"…" if len(b.text) > 36 else ""}"')
        return {"ok": True}

    @api.post("/key/press")
    def k_press(b: PressIn, _=Depends(auth)) -> dict:
        aliases = {"cmd": "command", "super": "command", "meta": "command"}
        keys = [aliases.get(k.lower(), k.lower()) for k in b.keys]
        pyautogui.hotkey(*keys)
        _log(f"⌘ {'+'.join(keys)}")
        return {"ok": True}

    @api.post("/stop")
    def stop() -> dict:
        _log("⏹ STOP")
        return {"ok": True}

    _log(f"bridge online → http://127.0.0.1:{PORT}")
    uvicorn.run(api, host="127.0.0.1", port=PORT, log_level="warning")


# ── AppKit window ────────────────────────────────────────────────────
TEAL = NSColor.colorWithSRGBRed_green_blue_alpha_(94 / 255, 234 / 255, 212 / 255, 1.0)
INK = NSColor.colorWithSRGBRed_green_blue_alpha_(248 / 255, 250 / 255, 252 / 255, 1.0)
DIM = NSColor.colorWithSRGBRed_green_blue_alpha_(148 / 255, 163 / 255, 184 / 255, 1.0)
BG = NSColor.colorWithSRGBRed_green_blue_alpha_(2 / 255, 6 / 255, 10 / 255, 1.0)
PANEL = NSColor.colorWithSRGBRed_green_blue_alpha_(4 / 255, 16 / 255, 26 / 255, 1.0)


class OlwenAppDelegate(NSObject):
    window = None
    status_label = None
    log_view = None
    token_field = None

    def applicationDidFinishLaunching_(self, _notification) -> None:
        NSApp.setActivationPolicy_(NSApplicationActivationPolicyRegular)
        self._build_window()
        # poll the in-process log every 600ms and reflect into the text view
        AppHelper.callLater(0.6, self._refresh_log)

    def applicationShouldTerminateAfterLastWindowClosed_(self, _sender) -> bool:
        # Closing the window does NOT quit — bridge keeps running. Use ⌘Q.
        return False

    def _build_window(self) -> None:
        rect = NSMakeRect(160, 160, 640, 520)
        mask = (
            NSWindowStyleMaskTitled
            | NSWindowStyleMaskClosable
            | NSWindowStyleMaskMiniaturizable
            | NSWindowStyleMaskResizable
            | NSWindowStyleMaskFullSizeContentView
        )
        win = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            rect, mask, NSBackingStoreBuffered, False
        )
        win.setTitle_("Olwen")
        win.setTitlebarAppearsTransparent_(True)
        win.setBackgroundColor_(BG)
        win.setMinSize_((460, 360))
        win.center()
        self.window = win

        content = win.contentView()
        bounds = content.bounds()

        # ── title row ────────────────────────────────────────────────
        title = NSTextField.labelWithString_("OLWEN")
        title.setFont_(NSFont.systemFontOfSize_weight_(15, 0.3))
        title.setTextColor_(INK)
        title.setFrame_(NSMakeRect(28, bounds.size.height - 72, 200, 24))
        title.setAutoresizingMask_(8)  # NSViewMinYMargin
        content.addSubview_(title)

        subtitle = NSTextField.labelWithString_("quietly knows everything")
        subtitle.setFont_(NSFont.systemFontOfSize_(11))
        subtitle.setTextColor_(DIM)
        subtitle.setFrame_(NSMakeRect(28, bounds.size.height - 92, 300, 18))
        subtitle.setAutoresizingMask_(8)
        content.addSubview_(subtitle)

        # ── status pill ──────────────────────────────────────────────
        status = NSTextField.labelWithString_(f"  ●  bridge online · 127.0.0.1:{PORT}")
        status.setFont_(NSFont.monospacedSystemFontOfSize_weight_(11, 0.2))
        status.setTextColor_(TEAL)
        status.setFrame_(NSMakeRect(28, bounds.size.height - 130, 380, 24))
        status.setAutoresizingMask_(8)
        content.addSubview_(status)
        self.status_label = status

        # ── token box + copy button ──────────────────────────────────
        token_lbl = NSTextField.labelWithString_("Token")
        token_lbl.setFont_(NSFont.systemFontOfSize_(10))
        token_lbl.setTextColor_(DIM)
        token_lbl.setFrame_(NSMakeRect(28, bounds.size.height - 170, 60, 16))
        token_lbl.setAutoresizingMask_(8)
        content.addSubview_(token_lbl)

        token_field = NSTextField.alloc().initWithFrame_(
            NSMakeRect(28, bounds.size.height - 196, bounds.size.width - 156, 26)
        )
        token_field.setStringValue_(TOKEN[:16] + "…" + TOKEN[-8:])
        token_field.setEditable_(False)
        token_field.setSelectable_(True)
        token_field.setBezeled_(False)
        token_field.setDrawsBackground_(True)
        token_field.setBackgroundColor_(PANEL)
        token_field.setTextColor_(INK)
        token_field.setFont_(NSFont.monospacedSystemFontOfSize_weight_(11, 0.0))
        token_field.setAutoresizingMask_(2 | 8)  # width + minY
        content.addSubview_(token_field)
        self.token_field = token_field

        copy_btn = NSButton.alloc().initWithFrame_(
            NSMakeRect(bounds.size.width - 120, bounds.size.height - 198, 92, 28)
        )
        copy_btn.setTitle_("Copy token")
        copy_btn.setBezelStyle_(NSBezelStyleRegularSquare)
        copy_btn.setTarget_(self)
        copy_btn.setAction_("copyToken:")
        copy_btn.setAutoresizingMask_(1 | 8)  # minX + minY
        content.addSubview_(copy_btn)

        # ── activity log ─────────────────────────────────────────────
        log_lbl = NSTextField.labelWithString_("Recent activity")
        log_lbl.setFont_(NSFont.systemFontOfSize_(10))
        log_lbl.setTextColor_(DIM)
        log_lbl.setFrame_(NSMakeRect(28, bounds.size.height - 240, 200, 16))
        log_lbl.setAutoresizingMask_(8)
        content.addSubview_(log_lbl)

        scroll = NSScrollView.alloc().initWithFrame_(
            NSMakeRect(28, 60, bounds.size.width - 56, bounds.size.height - 320)
        )
        scroll.setBorderType_(0)
        scroll.setHasVerticalScroller_(True)
        scroll.setAutoresizingMask_(2 | 16)  # width + height

        text = NSTextView.alloc().initWithFrame_(scroll.bounds())
        text.setEditable_(False)
        text.setSelectable_(True)
        text.setBackgroundColor_(PANEL)
        text.setTextColor_(INK)
        text.setFont_(NSFont.monospacedSystemFontOfSize_weight_(11, 0.0))
        text.setAutoresizingMask_(2)  # width
        text.setString_("waiting for activity…\n")
        scroll.setDocumentView_(text)
        content.addSubview_(scroll)
        self.log_view = text

        # ── footer ───────────────────────────────────────────────────
        footer = NSTextField.labelWithString_(
            "Olwen runs in the background. Close this window to hide; ⌘Q to quit."
        )
        footer.setFont_(NSFont.systemFontOfSize_(10))
        footer.setTextColor_(DIM)
        footer.setFrame_(NSMakeRect(28, 24, bounds.size.width - 56, 18))
        footer.setAutoresizingMask_(2)
        content.addSubview_(footer)

        win.makeKeyAndOrderFront_(None)
        NSApp.activateIgnoringOtherApps_(True)

    @objc.IBAction
    def copyToken_(self, _sender) -> None:
        pb = NSPasteboard.generalPasteboard()
        pb.clearContents()
        pb.setString_forType_(TOKEN, NSPasteboardTypeString)
        # flash the field bg
        self.token_field.setStringValue_("copied to clipboard ✓")
        AppHelper.callLater(1.6, lambda: self.token_field.setStringValue_(
            TOKEN[:16] + "…" + TOKEN[-8:]
        ))

    def _refresh_log(self) -> None:
        if self.log_view is not None:
            text = "\n".join(_action_log) or "waiting for activity…"
            self.log_view.setString_(text + "\n")
            # auto-scroll to bottom
            self.log_view.scrollToEndOfDocument_(None)
        AppHelper.callLater(0.6, self._refresh_log)


def main() -> None:
    # Start the bridge in a background thread so AppKit owns the main thread.
    th = threading.Thread(target=_start_bridge, daemon=True)
    th.start()

    # Tiny race-protector — wait for the port to actually accept connections
    # before showing the green status, so the label doesn't lie.
    for _ in range(50):
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
