"""Chat with Olwen — streamed over SSE."""
import json
import re
from collections.abc import AsyncIterator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import CurrentUser, SessionDep
from app.core.config import settings
from app.core.security import decrypt_secret
from app.models.installed_skill import InstalledSkill
from app.models.memory import Memory
from app.services.agent import build_tools, run_agent, stream_text
from app.services.olwen_ai import _build_system, stream_reply
from app.services.skills import catalog_by_key

router = APIRouter()

# "remember that I prefer mornings" → saves "I prefer mornings"
_REMEMBER = re.compile(r"^\s*(?:remember|note|keep in mind|don'?t forget)(?:\s+(?:that|to))?[:,]?\s*(.+)", re.IGNORECASE)
# Does the message look like it might want a tool? (tasks, search, lookups, app control, etc.)
_AGENT_INTENT = re.compile(
    # tasks / lookups
    r"\b(task|tasks|to-?do|to do|my list|remind|reminder|"
    r"search|find|look\s?up|google|browse|fetch|"
    r"what\s+is|who\s+is|where|when\s+did|how\s+do|tell\s+me\s+about)\b"
    r"|\b(add|create|complete|mark|done|finish)\b"
    # opening apps / surfaces inside Olwen
    r"|\b(open|launch|start|run|enter|show|go\s+to)\s+(terminal|shell|console|dev\s*mode|focus|"
    r"settings|inbox|email|compose|news|brief)\b"
    # opening any native macOS app — generic "open/launch/start <something>"
    r"|\b(open|launch|start)\s+\S{2,}"
    r"|\b(write|send|compose|reply|text|dm)\s+(an?\s+)?(email|mess?age|msg|whats\s*app|tele\s*gram|wa|tg|sms)\b"
    r"|\b(mess?age|whats\s*app|tele\s*gram|wa|tg)\b.*\b(me|him|her|them|to|say|saying|that)\b"
    r"|\b(send|text|tell)\b.*\b(whats\s*app|tele\s*gram|message|mesage)\b"
    r"|\b(begin|start)\s+work(ing)?\b"
    r"|\b(let'?s|lets)\s+(code|build|hack|ship)\b"
    r"|\b(coding|dev|developer)\s+(session|studio|mode)\b"
    r"|\b(start|open)\s+(coding|a\s+coding)\b"
    r"|\b(claude|claude\s*code|code\s+mode)\b",
    re.IGNORECASE,
)


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    history: list[ChatMessage] = Field(default_factory=list)


def _auto_route(message: str, enc_by: dict[str, str | None]) -> str | None:
    """Pick the best connected provider for this message.

    Tools (open apps, send messages, take the wheel, tasks, search) are wired
    on Gemini, so any *actionable* request routes to Gemini when connected.
    Plain conversation routes to the fastest/cheapest connected provider.

    Returns a provider key, or None if nothing is connected.
    """
    connected = [p for p in ("claude", "gemini", "groq") if enc_by.get(p)]
    if not connected:
        return None
    # Actionable / tool-ish message → Gemini (where tools work) if available.
    if _AGENT_INTENT.search(message) and "gemini" in connected:
        return "gemini"
    # Otherwise plain chat: fast & cheap first.
    for pref in ("groq", "gemini", "claude"):
        if pref in connected:
            return pref
    return connected[0]


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event)}\n\n"


@router.post("/stream")
async def chat_stream(data: ChatRequest, user: CurrentUser, session: SessionDep) -> StreamingResponse:
    history = [{"role": m.role, "content": m.content} for m in data.history]

    # "remember …" → save a memory immediately (no extra AI call)
    m = _REMEMBER.match(data.message)
    if m:
        fact = m.group(1).strip().rstrip(".")
        if fact:
            session.add(Memory(user_id=user.id, content=fact[:500]))
            await session.commit()

    # Load what Olwen knows about this user (compact, injected into the prompt).
    rows = await session.scalars(
        select(Memory).where(Memory.user_id == user.id).order_by(Memory.created_at.desc()).limit(40)
    )
    memories = [r.content for r in rows]

    # Installed skills → Olwen is aware of them.
    installed_keys = list(await session.scalars(
        select(InstalledSkill.skill_key).where(InstalledSkill.user_id == user.id)
    ))
    cat = catalog_by_key()
    skills = [f"{cat[k]['name']} — {cat[k]['description']}" for k in installed_keys if k in cat]

    # Resolve the user's chosen provider + their key (decrypted just in time).
    # "auto" → pick the best connected provider for THIS message.
    _enc_by = {
        "claude": user.llm_api_key_enc,
        "gemini": user.gemini_key_enc,
        "groq": user.groq_key_enc,
    }
    provider = user.llm_provider
    if provider == "auto":
        provider = _auto_route(data.message, _enc_by)
    user_key: str | None = None
    _enc = _enc_by.get(provider or "")
    if _enc:
        user_key = decrypt_secret(_enc)
    else:
        provider = None  # nothing connected → falls back to env/mock

    # Tools (open apps, send messages, take the wheel, tasks, search) run on the
    # Gemini agent loop. Use it for any ACTIONABLE message whenever a Gemini key
    # is connected — regardless of which provider the user picked for chat. This
    # way "send a whatsapp" works even when the chat brain is Claude or Groq.
    _gem_enc = _enc_by.get("gemini")
    gemini_key = decrypt_secret(_gem_enc) if _gem_enc else None
    tools = build_tools(installed_keys) if gemini_key else []
    use_agent = bool(tools) and bool(_AGENT_INTENT.search(data.message))

    async def event_source() -> AsyncIterator[str]:
        try:
            if use_agent:
                system = _build_system(memories, skills)
                result = await run_agent(
                    data.message, history, gemini_key, settings.gemini_model,
                    system, tools, user, session,
                )
                # Surface UI actions first so the frontend can dispatch them
                # while the typed answer is still streaming in.
                for action in result.get("ui_actions", []):
                    yield _sse({"type": "ui_action", **action})
                async for delta in stream_text(result.get("text", "")):
                    yield _sse({"type": "delta", "text": delta})
            else:
                async for delta in stream_reply(
                    data.message, history, provider=provider, api_key=user_key,
                    memory=memories, skills=skills,
                ):
                    yield _sse({"type": "delta", "text": delta})
            yield _sse({"type": "done"})
        except Exception as exc:  # surface a clean error to the client
            yield _sse({"type": "error", "message": str(exc)})

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
