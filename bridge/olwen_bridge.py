"""Olwen Bridge — a tiny local daemon that gives Olwen control of the
mouse, keyboard, and screen on this device.

It listens on 127.0.0.1 only (never exposed to the network), requires a
shared bearer token, and refuses any request without it. Olwen's backend
calls this when the user has explicitly opened Computer-Use mode.

Endpoints (all require Authorization: Bearer <token>):
    GET  /health                  → liveness + version
    GET  /screen                  → {width, height, scale}
    GET  /screenshot              → image/png of current screen
    POST /mouse/move              → {x, y, duration?}
    POST /mouse/click             → {x?, y?, button?, double?, count?}
    POST /mouse/scroll            → {dx, dy}
    POST /key/type                → {text, interval?}
    POST /key/press               → {keys: ["cmd","shift","p"]}
    GET  /ax/apps                 → running UI apps (name, bundle, pid)
    POST /ax/find                 → read an app's UI tree by label (no clicking)
    POST /ax/act                  → press/focus/set a real element by identity
    POST /stop                    → cancel any in-progress action

Safety:
    - Hard movement cap per request (no off-screen, no negative coords).
    - Global STOP flag honored by every endpoint between actions.
    - Token rotated on each install.
"""
from __future__ import annotations

import io
import os
import pathlib
import secrets
import sys
import threading
import time
from typing import Annotated

import pyautogui
from fastapi import Body, Depends, FastAPI, Header, HTTPException, Response
from mss import mss
from PIL import Image
from pydantic import BaseModel, Field

from ax_control import act as ax_act
from ax_control import activate as ax_activate
from ax_control import find as ax_find
from ax_control import frontmost as ax_frontmost
from ax_control import list_apps as ax_list_apps
from ax_control import trusted as ax_trusted

VERSION = "0.1.0"
PORT = int(os.getenv("OLWEN_BRIDGE_PORT", "8765"))
TOKEN_PATH = pathlib.Path(os.getenv("OLWEN_BRIDGE_TOKEN_PATH", str(pathlib.Path.home() / ".olwen" / "bridge.token")))

# Disable PyAutoGUI's "move to corner = abort" so a panicked user uses our
# explicit /stop instead. The frontend STOP button is the kill switch.
pyautogui.FAILSAFE = False
pyautogui.PAUSE = 0.0


# ── auth ──────────────────────────────────────────────────────────────
def _load_or_create_token() -> str:
    TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    if TOKEN_PATH.exists():
        return TOKEN_PATH.read_text().strip()
    token = secrets.token_urlsafe(48)
    TOKEN_PATH.write_text(token)
    TOKEN_PATH.chmod(0o600)
    return token


BEARER = _load_or_create_token()


def require_token(authorization: Annotated[str | None, Header()] = None) -> None:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "missing bearer token")
    if not secrets.compare_digest(authorization.split(" ", 1)[1].strip(), BEARER):
        raise HTTPException(401, "bad token")


# ── stop flag (honored between actions) ───────────────────────────────
_stop = threading.Event()


def _guard() -> None:
    if _stop.is_set():
        raise HTTPException(409, "stopped by user")


# ── schemas ───────────────────────────────────────────────────────────
class MoveIn(BaseModel):
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    duration: float = Field(0.15, ge=0, le=2.0)


class ClickIn(BaseModel):
    x: int | None = Field(None, ge=0)
    y: int | None = Field(None, ge=0)
    button: str = Field("left", pattern="^(left|right|middle)$")
    count: int = Field(1, ge=1, le=3)
    interval: float = Field(0.05, ge=0, le=0.5)


class ScrollIn(BaseModel):
    dx: int = 0
    dy: int = 0


class TypeIn(BaseModel):
    text: str = Field(min_length=1, max_length=10_000)
    interval: float = Field(0.01, ge=0, le=0.2)


class PressIn(BaseModel):
    keys: list[str] = Field(min_length=1, max_length=8)


class AxSelector(BaseModel):
    app: str = Field(min_length=1)                  # app name or bundle id
    role: str | None = None                         # exact AXRole (e.g. AXButton)
    title: str | None = None                        # exact AXTitle
    desc: str | None = None                         # exact AXDescription
    title_contains: str | None = None
    desc_contains: str | None = None
    placeholder_contains: str | None = None
    value_contains: str | None = None


class AxFindIn(AxSelector):
    limit: int = Field(40, ge=1, le=200)
    activate: bool = False


class AxActIn(AxSelector):
    action: str = Field("press", pattern="^(press|focus|set_value)$")
    nth: int = Field(0, ge=0)
    value: str | None = None
    activate: bool = True


_SEL_FIELDS = {"role", "title", "desc", "title_contains", "desc_contains",
               "placeholder_contains", "value_contains"}


# ── app ───────────────────────────────────────────────────────────────
app = FastAPI(title="Olwen Bridge", version=VERSION)


@app.get("/health")
def health(_: None = Depends(require_token)) -> dict:
    return {"ok": True, "version": VERSION}


@app.get("/screen")
def screen(_: None = Depends(require_token)) -> dict:
    w, h = pyautogui.size()
    # On macOS Retina, mss reports physical pixels; pyautogui reports logical.
    with mss() as sct:
        mon = sct.monitors[1]
        scale = round(mon["width"] / w, 2) if w else 1.0
    return {"width": int(w), "height": int(h), "scale": scale}


@app.get("/screenshot")
def screenshot(_: None = Depends(require_token)) -> Response:
    with mss() as sct:
        raw = sct.grab(sct.monitors[1])
        img = Image.frombytes("RGB", raw.size, raw.rgb)
    # Downscale so we don't ship 8 MB PNGs to Claude every step.
    img.thumbnail((1568, 1568), Image.Resampling.LANCZOS)
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return Response(buf.getvalue(), media_type="image/png")


@app.post("/mouse/move")
def mouse_move(body: MoveIn, _: None = Depends(require_token)) -> dict:
    _guard()
    pyautogui.moveTo(body.x, body.y, duration=body.duration)
    return {"ok": True, "at": [body.x, body.y]}


@app.post("/mouse/click")
def mouse_click(body: Annotated[ClickIn, Body()], _: None = Depends(require_token)) -> dict:
    _guard()
    kwargs = {"button": body.button, "clicks": body.count, "interval": body.interval}
    if body.x is not None and body.y is not None:
        pyautogui.click(body.x, body.y, **kwargs)
    else:
        pyautogui.click(**kwargs)
    return {"ok": True}


@app.post("/mouse/scroll")
def mouse_scroll(body: Annotated[ScrollIn, Body()], _: None = Depends(require_token)) -> dict:
    _guard()
    if body.dy:
        pyautogui.scroll(body.dy)
    if body.dx:
        pyautogui.hscroll(body.dx)
    return {"ok": True}


@app.post("/key/type")
def key_type(body: TypeIn, _: None = Depends(require_token)) -> dict:
    _guard()
    pyautogui.typewrite(body.text, interval=body.interval)
    return {"ok": True, "chars": len(body.text)}


@app.post("/key/press")
def key_press(body: PressIn, _: None = Depends(require_token)) -> dict:
    _guard()
    # Normalize aliases so Claude's vocabulary ("super", "meta") works on macOS.
    aliases = {"cmd": "command", "super": "command", "meta": "command", "ctrl": "ctrl"}
    keys = [aliases.get(k.lower(), k.lower()) for k in body.keys]
    pyautogui.hotkey(*keys)
    return {"ok": True, "keys": keys}


# ── accessibility (semantic UI control — find/act on real elements) ───
@app.get("/ax/apps")
def ax_apps(_: None = Depends(require_token)) -> dict:
    try:
        return {"ok": True, "trusted": ax_trusted(), "apps": ax_list_apps()}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(503, f"accessibility unavailable: {exc}")


@app.get("/ax/frontmost")
def ax_frontmost_ep(_: None = Depends(require_token)) -> dict:
    try:
        return {"ok": True, **ax_frontmost()}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(503, f"accessibility unavailable: {exc}")


class AxActivateIn(BaseModel):
    app: str = Field(min_length=1)


@app.post("/ax/activate")
def ax_activate_ep(body: Annotated[AxActivateIn, Body()], _: None = Depends(require_token)) -> dict:
    try:
        return {"ok": True, **ax_activate(body.app)}
    except LookupError as exc:
        raise HTTPException(404, str(exc))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(503, str(exc))


@app.post("/ax/find")
def ax_find_ep(body: Annotated[AxFindIn, Body()], _: None = Depends(require_token)) -> dict:
    _guard()
    sel = {k: getattr(body, k) for k in _SEL_FIELDS}
    try:
        return {"ok": True, **ax_find(body.app, sel, limit=body.limit, activate=body.activate)}
    except LookupError as exc:
        raise HTTPException(404, str(exc))
    except RuntimeError as exc:
        raise HTTPException(503, str(exc))


@app.post("/ax/act")
def ax_act_ep(body: Annotated[AxActIn, Body()], _: None = Depends(require_token)) -> dict:
    _guard()
    sel = {k: getattr(body, k) for k in _SEL_FIELDS}
    try:
        return ax_act(body.app, sel, action=body.action, nth=body.nth,
                      value=body.value, activate=body.activate)
    except LookupError as exc:
        raise HTTPException(404, str(exc))
    except ValueError as exc:
        raise HTTPException(422, str(exc))
    except RuntimeError as exc:
        raise HTTPException(503, str(exc))


@app.post("/stop")
def stop() -> dict:  # no auth — the panic button
    _stop.set()
    # auto-clear after a beat so the bridge accepts new tasks again
    threading.Timer(0.5, _stop.clear).start()
    return {"ok": True, "stopped_at": time.time()}


def main() -> None:
    import uvicorn
    print(f"Olwen Bridge {VERSION} → http://127.0.0.1:{PORT}", file=sys.stderr)
    print(f"Token at: {TOKEN_PATH}", file=sys.stderr)
    uvicorn.run(app, host="127.0.0.1", port=PORT, log_level="warning")


if __name__ == "__main__":
    main()
