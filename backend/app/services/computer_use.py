"""Computer-Use loop.

Talks to two parties:
  1. ``olwen-bridge`` running on the user's device (mouse / keyboard / screen)
  2. Anthropic's Claude with the ``computer_20241022`` tool

Each step:
  • we ship the latest screenshot + the user's instruction to Claude
  • Claude returns one or more ``tool_use`` blocks (action = screenshot, key,
    type, mouse_move, left_click, double_click, scroll, …)
  • we execute every action against the bridge and reply with a ``tool_result``
    (a fresh screenshot when relevant)
  • we repeat until Claude says ``end_turn`` or we hit the per-task step cap

The whole loop is async and yields ``ComputerUseEvent``s so the API route can
stream progress to the frontend via SSE — the user sees every click before it
hits the wire and can hit STOP at any point.
"""
from __future__ import annotations

import asyncio
import base64
import os
import pathlib
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.core.config import settings

# ── shared types ───────────────────────────────────────────────────────
@dataclass
class ComputerUseEvent:
    """One step's worth of output for the streaming endpoint."""
    kind: str                       # "thought" | "action" | "screenshot" | "done" | "error"
    text: str | None = None
    action: dict | None = None      # the tool_use block we executed
    image_b64: str | None = None    # PNG, base64
    ts: float = field(default_factory=time.time)

    def to_json(self) -> dict:
        out: dict[str, Any] = {"kind": self.kind, "ts": self.ts}
        if self.text is not None:
            out["text"] = self.text
        if self.action is not None:
            out["action"] = self.action
        if self.image_b64 is not None:
            out["image_b64"] = self.image_b64
        return out


# ── bridge client ──────────────────────────────────────────────────────
def _load_bridge_token() -> str:
    path = pathlib.Path(os.path.expanduser(settings.bridge_token_path))
    if not path.exists():
        raise RuntimeError(
            f"Bridge token not found at {path}. Install the bridge first: "
            "`cd bridge && ./install_bridge.sh`."
        )
    return path.read_text().strip()


class BridgeClient:
    """Thin async wrapper around the olwen-bridge HTTP API."""

    def __init__(self) -> None:
        self.base = settings.bridge_url.rstrip("/")
        self._token = _load_bridge_token()
        self._client = httpx.AsyncClient(
            base_url=self.base,
            headers={"Authorization": f"Bearer {self._token}"},
            timeout=10.0,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def health(self) -> dict:
        r = await self._client.get("/health")
        r.raise_for_status()
        return r.json()

    async def screen(self) -> dict:
        r = await self._client.get("/screen")
        r.raise_for_status()
        return r.json()

    async def screenshot_png(self) -> bytes:
        r = await self._client.get("/screenshot")
        r.raise_for_status()
        return r.content

    async def stop(self) -> None:
        # /stop is auth-free on the bridge — the panic button
        async with httpx.AsyncClient(base_url=self.base, timeout=2.0) as c:
            await c.post("/stop")

    # ── action dispatch ────────────────────────────────────────────────
    async def execute(self, action: str, params: dict) -> dict:
        """Map a Claude computer-use action to the bridge endpoint."""
        match action:
            case "screenshot":
                # the loop fetches a fresh screenshot after every action anyway
                return {"ok": True}
            case "mouse_move":
                x, y = params["coordinate"]
                return await self._post("/mouse/move", {"x": x, "y": y, "duration": 0.15})
            case "left_click":
                return await self._click(params, button="left")
            case "right_click":
                return await self._click(params, button="right")
            case "middle_click":
                return await self._click(params, button="middle")
            case "double_click":
                return await self._click(params, button="left", count=2)
            case "left_click_drag":
                # Move to start, hold, move to end — bridge has no drag primitive yet,
                # so emulate via move+click for now. A first-class drag endpoint is a
                # future addition (tracked in bridge/README.md).
                start = params.get("start_coordinate")
                end = params["coordinate"]
                if start:
                    await self._post("/mouse/move", {"x": start[0], "y": start[1]})
                return await self._post("/mouse/move", {"x": end[0], "y": end[1]})
            case "type":
                return await self._post("/key/type", {"text": params["text"]})
            case "key":
                # Claude sends xdotool-style: e.g. "cmd+shift+t", "Return", "Tab"
                keys = _split_chord(params["text"])
                return await self._post("/key/press", {"keys": keys})
            case "scroll":
                amount = params.get("amount", 3)
                direction = params.get("direction", "down")
                dy = -amount if direction == "down" else amount
                return await self._post("/mouse/scroll", {"dx": 0, "dy": dy})
            case "cursor_position":
                # Bridge doesn't expose this yet; return 0,0 so Claude doesn't choke.
                return {"x": 0, "y": 0}
            case _:
                raise ValueError(f"unsupported action: {action}")

    async def _click(self, params: dict, *, button: str, count: int = 1) -> dict:
        body: dict[str, Any] = {"button": button, "count": count}
        if "coordinate" in params:
            x, y = params["coordinate"]
            body |= {"x": x, "y": y}
        return await self._post("/mouse/click", body)

    async def _post(self, path: str, body: dict) -> dict:
        r = await self._client.post(path, json=body)
        r.raise_for_status()
        return r.json()


def _split_chord(chord: str) -> list[str]:
    # "cmd+shift+t" → ["cmd", "shift", "t"]; single keys ("Return") → ["return"]
    return [k.strip().lower() for k in chord.replace(" ", "").split("+")] if "+" in chord else [chord.strip().lower()]


# ── Claude loop ────────────────────────────────────────────────────────
ANTHROPIC_BASE = "https://api.anthropic.com/v1"
COMPUTER_TOOL = {
    "type": "computer_20241022",
    "name": "computer",
    "display_width_px": 1280,
    "display_height_px": 800,
    "display_number": 1,
}
SYSTEM_PROMPT = (
    "You are Olwen, a calm AI companion controlling the user's computer through "
    "the `computer` tool. Move deliberately. Verify the screen state before "
    "acting. Prefer keyboard shortcuts over click sequences when both work. "
    "Stop and explain when you are uncertain instead of guessing. Never enter "
    "credentials, never approve a purchase, never send a message on the user's "
    "behalf without an explicit instruction to do so."
)


async def run_computer_use(
    *,
    user_instruction: str,
    anthropic_api_key: str,
    bridge: BridgeClient,
    cancel: asyncio.Event,
) -> AsyncIterator[ComputerUseEvent]:
    """Drive Claude's computer-use loop, yielding one event per step."""
    if not anthropic_api_key:
        yield ComputerUseEvent("error", text="No Anthropic API key configured. Set one in Settings → AI provider.")
        return

    # Update the computer tool to reflect the real screen size.
    try:
        screen = await bridge.screen()
        tool = dict(COMPUTER_TOOL)
        tool["display_width_px"] = int(screen["width"])
        tool["display_height_px"] = int(screen["height"])
    except Exception as exc:  # noqa: BLE001
        yield ComputerUseEvent("error", text=f"Bridge unreachable: {exc}. Is olwen-bridge running?")
        return

    # Seed the conversation with the user's request + an initial screenshot.
    initial_png = await bridge.screenshot_png()
    initial_b64 = base64.b64encode(initial_png).decode()
    yield ComputerUseEvent("screenshot", image_b64=initial_b64)

    messages: list[dict] = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": user_instruction},
                {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": initial_b64}},
            ],
        }
    ]

    headers = {
        "x-api-key": anthropic_api_key,
        "anthropic-version": "2023-06-01",
        "anthropic-beta": "computer-use-2024-10-22",
        "content-type": "application/json",
    }

    async with httpx.AsyncClient(timeout=60.0) as http:
        for step in range(settings.computer_use_max_steps):
            if cancel.is_set():
                await bridge.stop()
                yield ComputerUseEvent("done", text="stopped by user")
                return

            body = {
                "model": settings.computer_use_model,
                "max_tokens": 1024,
                "system": SYSTEM_PROMPT,
                "tools": [tool],
                "messages": messages,
            }
            try:
                r = await http.post(f"{ANTHROPIC_BASE}/messages", json=body, headers=headers)
                r.raise_for_status()
                response = r.json()
            except httpx.HTTPStatusError as exc:
                yield ComputerUseEvent("error", text=f"Claude rejected the request: {exc.response.status_code} {exc.response.text[:200]}")
                return
            except httpx.HTTPError as exc:
                yield ComputerUseEvent("error", text=f"Network error talking to Claude: {exc}")
                return

            assistant_blocks = response.get("content", [])
            tool_results: list[dict] = []

            for block in assistant_blocks:
                btype = block.get("type")
                if btype == "text":
                    text = (block.get("text") or "").strip()
                    if text:
                        yield ComputerUseEvent("thought", text=text)
                elif btype == "tool_use":
                    name = block.get("name", "")
                    inp = block.get("input", {}) or {}
                    if name != "computer":
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block["id"],
                            "content": [{"type": "text", "text": f"unknown tool: {name}"}],
                            "is_error": True,
                        })
                        continue

                    action = inp.get("action", "")
                    yield ComputerUseEvent("action", action={"action": action, **inp})

                    try:
                        await bridge.execute(action, inp)
                    except Exception as exc:  # noqa: BLE001
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block["id"],
                            "content": [{"type": "text", "text": f"action failed: {exc}"}],
                            "is_error": True,
                        })
                        continue

                    # After each action, give Claude the new screen.
                    await asyncio.sleep(0.4)  # let the UI settle
                    png = await bridge.screenshot_png()
                    b64 = base64.b64encode(png).decode()
                    yield ComputerUseEvent("screenshot", image_b64=b64)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block["id"],
                        "content": [
                            {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": b64}},
                        ],
                    })

            # Append the assistant turn + our tool results, then continue or finish.
            messages.append({"role": "assistant", "content": assistant_blocks})
            if response.get("stop_reason") == "end_turn" or not tool_results:
                yield ComputerUseEvent("done", text="task complete")
                return
            messages.append({"role": "user", "content": tool_results})

        yield ComputerUseEvent("done", text=f"stopped — hit the {settings.computer_use_max_steps}-step cap")
