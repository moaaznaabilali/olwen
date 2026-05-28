"""Olwen Apps — interactive surfaces that run on the host and stream to the browser.

The first app is a Terminal: a real PTY spawned as the user, piped over a
WebSocket to xterm.js in the browser. Lets the user run `claude`, `git`,
anything in their shell, from inside Olwen.

Architecture note: each PTY is a real subprocess as the backend user. Fine
for single-user local dev. If this ever runs multi-tenant, each PTY would
need to be containerised (a Docker container per session with cpu/mem limits).
"""
from __future__ import annotations

import asyncio
import fcntl
import json
import logging
import os
import pty
import signal
import struct
import termios
from typing import Any

import jwt
from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.user import User

router = APIRouter()
log = logging.getLogger("olwen.apps")


def _authenticate(token: str) -> str | None:
    """JWT in query string. Returns user_id or None."""
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        if payload.get("type") != "access":
            return None
        return str(payload.get("sub"))
    except Exception:
        return None


@router.websocket("/terminal/ws")
async def terminal_ws(ws: WebSocket, token: str = Query(...), cwd: str | None = Query(None)) -> None:
    """Bidirectional pipe between xterm.js and a host PTY.

    Wire protocol:
      Browser → server: binary frames (raw stdin bytes), OR
                        text frames with JSON envelope:
                          {"type":"resize","rows":N,"cols":N}
                          {"type":"signal","name":"SIGINT"}
      Server → browser: binary frames (raw PTY output)
    """
    user_id = _authenticate(token)
    if user_id is None:
        await ws.close(code=4401, reason="Invalid auth")
        return
    # Confirm user exists (cheap sanity check; PTY will run as backend uid regardless)
    async with SessionLocal() as session:
        user = await session.get(User, __import__("uuid").UUID(user_id))
        if user is None:
            await ws.close(code=4401, reason="No such user")
            return

    await ws.accept()
    log.info("Terminal opened for user=%s", user.email)

    # Sanity-check the cwd before fork (must exist + be a directory)
    target_cwd: str | None = None
    if cwd:
        try:
            real = os.path.realpath(cwd)
            if os.path.isdir(real):
                target_cwd = real
        except Exception:
            pass

    # Spawn the PTY — child becomes the user's interactive login shell
    pid, fd = pty.fork()
    if pid == 0:
        # CHILD: become the shell
        shell = os.environ.get("SHELL") or "/bin/zsh"
        env = dict(os.environ)
        env["TERM"] = "xterm-256color"
        env["OLWEN_APP"] = "terminal"
        if target_cwd:
            try:
                os.chdir(target_cwd)
            except OSError:
                pass
        try:
            os.execvpe(shell, [shell, "-l"], env)
        except Exception:
            os._exit(1)

    # PARENT: pipe between the WS and the PTY fd
    loop = asyncio.get_event_loop()

    async def pty_to_ws() -> None:
        try:
            while True:
                # blocking read on a thread so we don't stall the event loop
                data = await loop.run_in_executor(None, _safe_read, fd, 8192)
                if not data:
                    break
                await ws.send_bytes(data)
        except Exception as exc:  # noqa: BLE001
            log.debug("pty_to_ws ended: %s", exc)

    pump = asyncio.create_task(pty_to_ws())

    try:
        while True:
            msg = await ws.receive()
            kind = msg.get("type")
            if kind == "websocket.disconnect":
                break
            if msg.get("bytes"):
                try:
                    os.write(fd, msg["bytes"])
                except OSError:
                    break
                continue
            text = msg.get("text")
            if not text:
                continue
            try:
                ev: dict[str, Any] = json.loads(text)
            except Exception:
                # treat as plain stdin text
                try:
                    os.write(fd, text.encode())
                except OSError:
                    break
                continue
            etype = ev.get("type")
            if etype == "resize":
                rows = int(ev.get("rows", 24))
                cols = int(ev.get("cols", 80))
                _set_winsize(fd, rows, cols)
            elif etype == "input":
                payload = (ev.get("data") or "").encode()
                if payload:
                    try:
                        os.write(fd, payload)
                    except OSError:
                        break
            elif etype == "signal":
                name = (ev.get("name") or "SIGINT").upper()
                sig = getattr(signal, name, signal.SIGINT)
                try:
                    os.kill(pid, sig)
                except ProcessLookupError:
                    break
    except WebSocketDisconnect:
        pass
    except Exception as exc:  # noqa: BLE001
        log.warning("Terminal loop error: %s", exc)
    finally:
        # Cancel pump first so it doesn't try to read a closed fd.
        pump.cancel()
        try:
            await asyncio.wait_for(pump, timeout=0.5)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            pass
        # Tear down the child process aggressively — SIGHUP → SIGTERM → SIGKILL,
        # so a stuck PTY can't keep the worker alive past a uvicorn reload.
        for sig in (signal.SIGHUP, signal.SIGTERM, signal.SIGKILL):
            try:
                os.kill(pid, sig)
                await asyncio.sleep(0.05)
                # check if process is gone
                try:
                    done_pid, _ = os.waitpid(pid, os.WNOHANG)
                    if done_pid != 0:
                        break
                except ChildProcessError:
                    break
            except ProcessLookupError:
                break
        try:
            os.close(fd)
        except OSError:
            pass
        log.info("Terminal closed for user=%s", user.email)


def _safe_read(fd: int, n: int) -> bytes:
    try:
        return os.read(fd, n)
    except OSError:
        return b""


def _set_winsize(fd: int, rows: int, cols: int) -> None:
    try:
        size = struct.pack("HHHH", rows, cols, 0, 0)
        fcntl.ioctl(fd, termios.TIOCSWINSZ, size)
    except Exception:
        pass


# ---------- Catalog endpoint (so the dock can dynamically list installed apps) ----------
@router.get("/catalog")
async def catalog() -> dict:
    """What apps Olwen offers today + their status."""
    return {
        "apps": [
            {
                "key": "terminal", "name": "Terminal", "glyph": "▢", "color": "#5EEAD4",
                "description": "Real shell on this host. Run claude, git, anything.",
                "live": True,
            },
            {
                "key": "browser", "name": "Browser", "glyph": "◐", "color": "#67E8F9",
                "description": "Olwen-controlled browser pane. Inspect, scrape, fill forms.",
                "live": False,
            },
            {
                "key": "editor", "name": "Editor", "glyph": "✎", "color": "#A78BFA",
                "description": "Monaco editor over your workspace files.",
                "live": False,
            },
            {
                "key": "files", "name": "Files", "glyph": "▥", "color": "#FBBF24",
                "description": "Tree view over your filesystem with quick previews.",
                "live": False,
            },
        ],
    }
