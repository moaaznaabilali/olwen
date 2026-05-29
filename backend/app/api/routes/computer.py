"""Computer-Use route — start, stream, stop, status, screenshot proxy.

The bridge lives at ``127.0.0.1:8765`` on the user's device. We never expose
the bridge to the browser directly; the frontend talks to *us* and we relay.

Endpoints:
    GET  /api/computer/status          → bridge reachable? screen size?
    GET  /api/computer/screenshot      → live PNG from the bridge
    POST /api/computer/stop            → emergency stop (panic button)
    POST /api/computer/run             → SSE stream of a computer-use task
"""
from __future__ import annotations

import asyncio
import json

import httpx
from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import SessionDep, get_current_user
from app.core.config import settings
from app.core.security import decrypt_secret
from app.models.user import User
from app.services import computer_use as cu

router = APIRouter()


class RunIn(BaseModel):
    instruction: str = Field(min_length=4, max_length=4000)


# A single shared cancel event per process. The frontend's STOP button flips
# it; the in-progress run sees it on the next iteration and tears down. Fine
# for a single-user dev install — production swaps this for a Redis flag.
_cancel = asyncio.Event()


def _user_anthropic_key(user: User) -> str:
    """User's BYO Claude key (decrypted) or the server-wide env fallback."""
    if user.llm_api_key_enc:
        try:
            return decrypt_secret(user.llm_api_key_enc)
        except Exception:  # noqa: BLE001 — fall back rather than crash the stream
            pass
    return settings.anthropic_api_key


@router.get("/status")
async def status(_: User = Depends(get_current_user)) -> dict:
    bridge = cu.BridgeClient()
    try:
        health = await bridge.health()
        screen = await bridge.screen()
        return {"ok": True, "bridge": health, "screen": screen}
    except FileNotFoundError as exc:
        return {"ok": False, "reason": str(exc)}
    except httpx.HTTPError as exc:
        return {"ok": False, "reason": f"bridge not reachable: {exc}"}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "reason": str(exc)}
    finally:
        await bridge.aclose()


@router.get("/screenshot")
async def screenshot(_: User = Depends(get_current_user)) -> Response:
    bridge = cu.BridgeClient()
    try:
        png = await bridge.screenshot_png()
        return Response(png, media_type="image/png", headers={"Cache-Control": "no-store"})
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"bridge unreachable: {exc}") from exc
    finally:
        await bridge.aclose()


@router.post("/stop")
async def stop(_: User = Depends(get_current_user)) -> dict:
    _cancel.set()
    bridge = cu.BridgeClient()
    try:
        await bridge.stop()
    except Exception:
        pass  # best-effort; the run loop also notices the cancel flag
    finally:
        await bridge.aclose()
    return {"ok": True}


@router.post("/run")
async def run(
    body: RunIn,
    session: SessionDep,
    user: User = Depends(get_current_user),
) -> StreamingResponse:
    """Stream Server-Sent Events as the computer-use loop progresses."""
    _cancel.clear()
    api_key = _user_anthropic_key(user)
    bridge = cu.BridgeClient()

    async def gen():
        try:
            async for event in cu.run_computer_use(
                user_instruction=body.instruction,
                anthropic_api_key=api_key,
                bridge=bridge,
                cancel=_cancel,
            ):
                yield f"data: {json.dumps(event.to_json())}\n\n"
        except Exception as exc:  # noqa: BLE001
            yield f"data: {json.dumps({'kind': 'error', 'text': str(exc)})}\n\n"
        finally:
            await bridge.aclose()
            yield "event: end\ndata: {}\n\n"

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-store",
            "X-Accel-Buffering": "no",  # disable nginx/cloudflare buffering
        },
    )
