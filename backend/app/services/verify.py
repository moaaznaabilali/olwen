"""Action verifier — Olwen's eyes.

Piece #2 of the agent-v2 architecture. A tool that ACTS in the real world must
not claim success on faith. After a real action (sending a message, opening an
app) we grab a screenshot from the bridge and ask a vision model whether the
goal was actually achieved. The caller then reports the TRUTH instead of a
hopeful "Sent."

Degrades honestly: if the bridge is down or no Claude key is connected we return
verified=None ("unknown") so callers say "I couldn't confirm" — never a lie.
"""
import base64

import httpx

from app.core.config import settings
from app.services.computer_use import ANTHROPIC_BASE, BridgeClient


async def verify_goal(goal: str, claude_key: str | None) -> dict:
    """Look at the screen and judge whether `goal` was achieved.

    Returns {"verified": True | False | None, "reason": str}:
      True  -> the screen proves it happened
      False -> the screen proves it did NOT
      None  -> couldn't look (no bridge / no key) — unknown, don't claim success
    """
    if not claude_key:
        return {"verified": None, "reason": "no Claude key to see with"}

    # Grab the screen through the bridge (our only pair of eyes).
    try:
        bridge = BridgeClient()
        png = await bridge.screenshot_png()
        await bridge.aclose()
    except Exception as exc:  # noqa: BLE001
        return {"verified": None, "reason": f"bridge unavailable: {exc}"}

    b64 = base64.b64encode(png).decode()
    prompt = (
        "You are a strict verifier. Look at this screenshot and decide whether "
        f'this goal was actually achieved: "{goal}". '
        "Answer with ONE word first — YES, NO, or UNSURE — then a short reason. "
        "Only say YES if the screen clearly proves it (e.g. the message is "
        "visible as the most recent outgoing bubble in the correct chat)."
    )
    headers = {
        "x-api-key": claude_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    body = {
        "model": settings.computer_use_model,
        "max_tokens": 200,
        "messages": [{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": b64}},
            {"type": "text", "text": prompt},
        ]}],
    }
    try:
        async with httpx.AsyncClient(timeout=30.0) as http:
            resp = await http.post(f"{ANTHROPIC_BASE}/messages", headers=headers, json=body)
            resp.raise_for_status()
            data = resp.json()
    except httpx.HTTPError as exc:
        return {"verified": None, "reason": f"vision check failed: {exc}"}

    text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text").strip()
    head = text.lstrip().upper()
    if head.startswith("YES"):
        return {"verified": True, "reason": text}
    if head.startswith("NO"):
        return {"verified": False, "reason": text}
    return {"verified": None, "reason": text or "unsure"}
