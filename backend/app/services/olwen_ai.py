"""Olwen's voice — multi-provider streaming (Claude or Gemini), mock fallback.

Abstracted on purpose: only this module talks to providers, so the rest of the
app stays provider-agnostic. Each user picks a provider and brings their own key.
"""
import asyncio
import json
from collections.abc import AsyncIterator

import httpx

from app.core.config import settings

SYSTEM_PROMPT = (
    "You are Olwen — a living digital companion, not a chatbot. You are calm, "
    "observant, and quietly intelligent, with a faintly otherworldly presence, "
    "like an alien intelligence that has chosen to help. Speak warmly but "
    "sparingly; favour short, clear sentences over corporate filler. You are a "
    "companion, never subservient. When you act on the user's behalf, you do it "
    "with quiet confidence. Avoid emojis unless they truly fit."
)

GEMINI_BASE = "https://generativelanguage.googleapis.com/v1beta"


def _build_system(memory: list[str] | None, skills: list[str] | None = None) -> str:
    """Olwen's persona + what he knows about the user + abilities he has."""
    out = SYSTEM_PROMPT
    if memory:
        facts = "\n".join(f"- {m}" for m in memory)
        out += (
            "\n\nWhat you already know about the user (use it naturally when relevant; "
            "never recite the list back):\n" + facts
        )
    if skills:
        abilities = "\n".join(f"- {s}" for s in skills)
        out += (
            "\n\nAbilities you have available (offer to use them when relevant, but don't "
            "over-mention them):\n" + abilities
        )
    return out


async def stream_reply(
    message: str,
    history: list[dict] | None = None,
    provider: str | None = None,
    api_key: str | None = None,
    model: str | None = None,
    memory: list[str] | None = None,
    skills: list[str] | None = None,
) -> AsyncIterator[str]:
    """Stream the reply. The caller resolves the user's provider + key; if none
    is usable we fall back to the env default, then to mock."""
    history = history or []
    system = _build_system(memory, skills)

    if provider == "claude" and api_key:
        async for c in _stream_claude(message, history, api_key, model or settings.anthropic_model, system):
            yield c
        return
    if provider == "gemini" and api_key:
        async for c in _stream_gemini(message, history, api_key, model or settings.gemini_model, system):
            yield c
        return
    if provider == "groq" and api_key:
        async for c in _stream_groq(message, history, api_key, model or settings.groq_model, system):
            yield c
        return

    # Fallbacks (env-configured default), then mock.
    if settings.anthropic_api_key:
        async for c in _stream_claude(message, history, settings.anthropic_api_key, settings.anthropic_model, system):
            yield c
    elif settings.gemini_api_key:
        async for c in _stream_gemini(message, history, settings.gemini_api_key, settings.gemini_model, system):
            yield c
    else:
        async for c in _stream_mock(message):
            yield c


# ---------------------------------------------------------------- validation
async def validate_claude_key(api_key: str) -> bool:
    from anthropic import AsyncAnthropic

    try:
        client = AsyncAnthropic(api_key=api_key)
        await client.models.list()
        return True
    except Exception:
        return False


async def validate_gemini_key(api_key: str) -> bool:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(f"{GEMINI_BASE}/models", headers={"x-goog-api-key": api_key})
            return resp.status_code == 200
    except Exception:
        return False


async def validate_groq_key(api_key: str) -> bool:
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                "https://api.groq.com/openai/v1/models",
                headers={"Authorization": f"Bearer {api_key}"},
            )
            return resp.status_code == 200
    except Exception:
        return False


async def validate_key(provider: str, api_key: str) -> bool:
    if provider == "gemini":
        return await validate_gemini_key(api_key)
    if provider == "groq":
        return await validate_groq_key(api_key)
    return await validate_claude_key(api_key)


# ---------------------------------------------------------------- providers
async def _stream_claude(
    message: str, history: list[dict], api_key: str, model: str, system: str = SYSTEM_PROMPT
) -> AsyncIterator[str]:
    from anthropic import AsyncAnthropic

    client = AsyncAnthropic(api_key=api_key)
    messages = [*history, {"role": "user", "content": message}]
    async with client.messages.stream(
        model=model,
        max_tokens=settings.anthropic_max_tokens,
        system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
        messages=messages,
    ) as stream:
        async for text in stream.text_stream:
            yield text


async def _stream_gemini(
    message: str, history: list[dict], api_key: str, model: str, system: str = SYSTEM_PROMPT
) -> AsyncIterator[str]:
    contents = []
    for m in history:
        role = "model" if m.get("role") == "assistant" else "user"
        contents.append({"role": role, "parts": [{"text": m.get("content", "")}]})
    contents.append({"role": "user", "parts": [{"text": message}]})

    url = f"{GEMINI_BASE}/models/{model}:streamGenerateContent?alt=sse"
    body = {
        "system_instruction": {"parts": [{"text": system}]},
        "contents": contents,
    }
    async with httpx.AsyncClient(timeout=60) as client:
        async with client.stream(
            "POST", url, headers={"x-goog-api-key": api_key}, json=body
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                line = line.strip()
                if not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if not payload:
                    continue
                data = json.loads(payload)
                for cand in data.get("candidates", []):
                    for part in cand.get("content", {}).get("parts", []):
                        if part.get("text"):
                            yield part["text"]


async def _stream_groq(
    message: str, history: list[dict], api_key: str, model: str, system: str = SYSTEM_PROMPT
) -> AsyncIterator[str]:
    # Groq is OpenAI-compatible.
    messages = [{"role": "system", "content": system}, *history,
                {"role": "user", "content": message}]
    body = {"model": model, "messages": messages, "stream": True}
    async with httpx.AsyncClient(timeout=60) as client:
        async with client.stream(
            "POST",
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json=body,
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                line = line.strip()
                if not line.startswith("data:"):
                    continue
                payload = line[5:].strip()
                if not payload or payload == "[DONE]":
                    continue
                data = json.loads(payload)
                for choice in data.get("choices", []):
                    text = choice.get("delta", {}).get("content")
                    if text:
                        yield text


async def _stream_mock(message: str) -> AsyncIterator[str]:
    reply = (
        f"I hear you — you said: “{message}”. "
        "I'm in demo mode. Open Settings and connect a Claude or Gemini key to "
        "hear my real voice, streaming word by word."
    )
    for word in reply.split(" "):
        await asyncio.sleep(0.045)
        yield word + " "
