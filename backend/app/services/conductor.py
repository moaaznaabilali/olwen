"""Conductor — Olwen supervising a Claude Code session in the terminal.

Given the coding goal and a snapshot of what Claude Code's terminal currently
shows, decide the single next thing to type into it — or that the task is done /
blocked. Olwen never edits code himself; Claude Code (the user's subscription,
running in the PTY) does. Olwen just drives the conversation to completion.
"""
import json
import re

import httpx

from app.core.config import settings

ANTHROPIC_BASE = "https://api.anthropic.com/v1"

# Cheap model — Olwen only MANAGES (classifies state, picks the next nudge); the
# heavy coding is done by Claude Code on the user's subscription. Keep tokens tiny.
_MANAGER_MODEL = "claude-haiku-4-5-20251001"

_SYSTEM = (
    "You are Olwen, an engineering manager pairing a developer (Moaz) with Claude "
    "Code, which runs in a terminal and does the actual coding. You do NOT write code "
    "— you turn Moaz's request into clear work for Claude Code and keep it on track.\n\n"
    "INTERPRET like a senior engineer taking a ticket: fix obvious typos, infer what "
    "Moaz actually wants, and be specific about the outcome. Don't parrot his words.\n\n"
    "When the terminal is EMPTY, produce the FIRST instruction: a clear, complete, "
    "self-contained brief telling Claude Code exactly what to build and to do it "
    "autonomously (explore the code, make the edits, verify). Example: Moaz says "
    "'improve fppter design of website' -> message: 'Look at the site footer component, "
    "then redesign it to be cleaner and more polished — consistent with the site's "
    "existing style. Make the edits and verify the build.'\n\n"
    "On later turns, READ the terminal and decide:\n"
    "- Claude Code is asking a question / for confirmation -> answer it to keep moving, "
    "consistent with the goal (usually approve).\n"
    "- Claude Code finished a step and is waiting -> give the next concrete instruction.\n"
    "- The goal is fully accomplished -> action='done'.\n"
    "- It's stuck/looping or you genuinely need Moaz -> action='blocked' with the reason.\n\n"
    "IMPORTANT: your 'message' is typed verbatim into Claude Code's input as ONE line "
    "and submitted — write it as a single line (no newlines), clear and imperative.\n\n"
    "Reply with ONLY a JSON object, no prose:\n"
    '{"action":"send|done|blocked","message":"the single-line instruction (empty if '
    'done/blocked)","note":"one short line telling Moaz what you\'re doing"}'
)


def _extract_json(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return {"action": "blocked", "message": "", "note": "couldn't parse a decision"}
    try:
        d = json.loads(m.group(0))
    except Exception:  # noqa: BLE001
        return {"action": "blocked", "message": "", "note": "couldn't parse a decision"}
    action = d.get("action") if d.get("action") in ("send", "done", "blocked") else "blocked"
    return {"action": action, "message": str(d.get("message") or "")[:2000],
            "note": str(d.get("note") or "")[:200]}


async def conduct_step(claude_key: str, goal: str, output: str,
                       transcript: list[dict]) -> dict:
    """Decide the next move. `output` is the (ANSI-stripped) terminal snapshot."""
    if not claude_key:
        return {"action": "blocked", "message": "", "note": "no Claude key connected"}

    convo = "\n".join(
        f"{t.get('from', '?')}: {t.get('text', '')}" for t in transcript[-8:]
    ) or "(nothing yet — send Claude Code the first instruction)"
    user = (
        f"GOAL:\n{goal}\n\n"
        f"WHAT YOU'VE SAID TO CLAUDE CODE SO FAR:\n{convo}\n\n"
        f"CLAUDE CODE TERMINAL (most recent lines, ANSI stripped):\n"
        f"```\n{output[-1800:]}\n```\n\n"
        "Decide the next move as JSON."
    )
    body = {
        "model": _MANAGER_MODEL,
        "max_tokens": 400,
        "system": _SYSTEM,
        "messages": [{"role": "user", "content": user}],
    }
    headers = {
        "x-api-key": claude_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=40.0) as http:
            r = await http.post(f"{ANTHROPIC_BASE}/messages", headers=headers, json=body)
            r.raise_for_status()
            data = r.json()
    except httpx.HTTPError as exc:
        return {"action": "blocked", "message": "", "note": f"Olwen couldn't think: {exc}"}
    text = "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text")
    return _extract_json(text)
