"""Curate today's top news, with Olwen's commentary per story.

Pulls items from the user's `news_topics`, asks the LLM to pick the most
important 3–5 and write a one-sentence "why this matters to you" beat for each.
Returns structured items + a 3–4 sentence spoken narrative.
"""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decrypt_secret
from app.models.user import User
from app.services.news_feeds import fetch_news
from app.services.olwen_ai import stream_reply


async def build_news_brief(user: User, session: AsyncSession) -> dict[str, Any]:
    topics = list(user.news_topics or ["ai", "tech"])
    # Pull more candidates so the LLM has room to choose
    raw = await fetch_news(topics, per_topic=5, total=20)
    if not raw:
        return {"narrative": "No fresh stories on your topics right now.", "items": [], "topics": topics}

    listing = "\n".join(
        f"{i+1}. [{n['tag']}] {n['title']}  ({n['source']})"
        for i, n in enumerate(raw)
    )
    name = (user.display_name or user.email.split("@")[0]).split()[0]

    enc = {"claude": user.llm_api_key_enc, "gemini": user.gemini_key_enc, "groq": user.groq_key_enc}.get(user.llm_provider or "")
    if not enc:
        # No AI — return the top 5 as-is with a flat narrative
        items = [{
            "title": n["title"], "source": n["source"], "url": n["url"],
            "tag": n["tag"], "why": "",
        } for n in raw[:5]]
        narrative = f"Top stories across {', '.join(topics)}: " + "; ".join(n["title"] for n in raw[:3])
        return {"narrative": narrative, "items": items, "topics": topics}

    api_key = decrypt_secret(enc)
    prompt = (
        f"You are Olwen, the user's calm AI companion. Below are {len(raw)} news items "
        f"on the topics {name} follows ({', '.join(topics)}). "
        "Pick the 3–5 most important — favour breaking developments, named entities the user "
        "would recognise, and concrete numbers. For each, write a one-sentence 'why this matters' "
        "tied to the topic, not a summary.\n\n"
        "Then write a 3–4 sentence spoken narrative weaving the picks together — natural, "
        "no bullets, no headlines, no preamble.\n\n"
        'Return ONLY this JSON: {"picks":[{"index":<1-based>,"why":"…"}],'
        '"narrative":"…"}\n\nITEMS:\n' + listing
    )
    try:
        chunks: list[str] = []
        async for c in stream_reply(prompt, [], provider=user.llm_provider, api_key=api_key, memory=[]):
            chunks.append(c)
        text = "".join(chunks).strip()
        s, e = text.index("{"), text.rindex("}") + 1
        obj = json.loads(text[s:e])
    except Exception:
        obj = {"picks": [], "narrative": ""}

    picks = obj.get("picks") or []
    chosen: list[dict] = []
    for p in picks[:5]:
        try:
            idx = int(p.get("index", 0)) - 1
            if 0 <= idx < len(raw):
                src = raw[idx]
                chosen.append({
                    "title": src["title"], "source": src["source"], "url": src["url"],
                    "tag": src["tag"], "why": str(p.get("why", ""))[:240],
                })
        except (ValueError, TypeError):
            continue
    if not chosen:
        chosen = [{**n, "why": ""} for n in raw[:5]]

    narrative = str(obj.get("narrative", "")).strip()
    if not narrative:
        narrative = f"Top stories today on {', '.join(topics)}: " + "; ".join(c["title"] for c in chosen[:3])
    return {"narrative": narrative, "items": chosen, "topics": topics}
