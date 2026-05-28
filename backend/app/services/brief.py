"""Compose Olwen's morning brief.

Aggregates the user's day-ahead surface (calendar, tasks, inbox-triage,
weather, news) and asks the LLM to weave it into a 4–6 sentence narrative
that Olwen will speak aloud.
"""
from __future__ import annotations

import datetime as dt
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decrypt_secret, encrypt_secret
from app.models.email_account import EmailAccount
from app.models.task import Task
from app.models.user import User
from app.services import app_config as app_cfg
from app.services import google_oauth
from app.services.news_feeds import fetch_news
from app.services.olwen_ai import stream_reply


async def _gather_tasks(session: AsyncSession, user_id) -> list[dict]:
    """Top 5 open tasks, high-priority first."""
    rows = await session.scalars(
        select(Task).where(Task.user_id == user_id, Task.done == False)  # noqa: E712
        .order_by(Task.priority.desc(), Task.created_at.asc()).limit(5)
    )
    return [{"text": t.text, "priority": t.priority} for t in rows]


async def _gather_calendar(session: AsyncSession, user) -> list[dict]:
    """Today's + tonight's events from primary Google calendar."""
    acc = await session.scalar(
        select(EmailAccount).where(EmailAccount.user_id == user.id, EmailAccount.provider == "google")
    )
    if acc is None or not acc.access_token_enc:
        return []
    try:
        access = decrypt_secret(acc.access_token_enc)
        if acc.token_expiry and acc.token_expiry <= dt.datetime.now(dt.timezone.utc):
            cid, csec = await app_cfg.google_creds(session)
            tokens = await google_oauth.refresh_access(decrypt_secret(acc.refresh_token_enc), client_id=cid, client_secret=csec)
            access = tokens["access_token"]
            acc.access_token_enc = encrypt_secret(access)
            acc.token_expiry = dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=int(tokens.get("expires_in", 3600)) - 60)
            await session.commit()
        return await google_oauth.fetch_calendar_events(access, hours_ahead=24, limit=8)
    except Exception:
        return []


async def _gather_inbox_highlights(session: AsyncSession, user) -> list[dict]:
    """Top 3 unread emails from the primary mailbox. No triage call — too slow
    for a morning brief; just surface what's unread + recent."""
    acc = await session.scalar(
        select(EmailAccount).where(EmailAccount.user_id == user.id).order_by(EmailAccount.created_at)
    )
    if acc is None:
        return []
    try:
        if acc.provider == "google" and acc.access_token_enc:
            access = decrypt_secret(acc.access_token_enc)
            if acc.token_expiry and acc.token_expiry <= dt.datetime.now(dt.timezone.utc):
                cid, csec = await app_cfg.google_creds(session)
                tokens = await google_oauth.refresh_access(decrypt_secret(acc.refresh_token_enc), client_id=cid, client_secret=csec)
                access = tokens["access_token"]
                acc.access_token_enc = encrypt_secret(access)
                acc.token_expiry = dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=int(tokens.get("expires_in", 3600)) - 60)
                await session.commit()
            msgs = await google_oauth.fetch_inbox(access, limit=8)
            unread = [m for m in msgs if m.get("unread")][:3]
            return unread
        # IMAP path skipped for now — login is sync + slow
    except Exception:
        return []
    return []


async def _gather_weather(lat: float = 24.71, lon: float = 46.68) -> dict:
    """Open-Meteo daily forecast — free, no key. Defaults to Riyadh."""
    try:
        async with httpx.AsyncClient(timeout=8) as c:
            r = await c.get(
                "https://api.open-meteo.com/v1/forecast",
                params={
                    "latitude": lat, "longitude": lon,
                    "current": "temperature_2m,weather_code",
                    "daily": "temperature_2m_max,temperature_2m_min,weather_code",
                    "forecast_days": 1,
                    "timezone": "auto",
                },
            )
            j = r.json()
            return {
                "now_c": round(j["current"]["temperature_2m"]),
                "high_c": round(j["daily"]["temperature_2m_max"][0]),
                "low_c": round(j["daily"]["temperature_2m_min"][0]),
                "code": j["current"]["weather_code"],
            }
    except Exception:
        return {}


def _weather_desc(code: int) -> str:
    if code == 0: return "clear"
    if code <= 3: return "partly cloudy"
    if code <= 48: return "foggy"
    if code <= 67: return "rainy"
    if code <= 77: return "snowy"
    if code <= 82: return "showering"
    return "stormy"


async def build_brief(user: User, session: AsyncSession) -> dict[str, Any]:
    """Aggregate the user's day-ahead surface, then ask the LLM for a narrative.

    DB-touching helpers run sequentially (sharing one async session); the
    external HTTP fetches (weather, news) run in parallel since they don't
    touch the session.
    """
    import asyncio
    tasks = await _gather_tasks(session, user.id)
    calendar = await _gather_calendar(session, user)
    inbox = await _gather_inbox_highlights(session, user)
    weather, news = await asyncio.gather(
        _gather_weather(),
        fetch_news(list(user.news_topics or ["ai", "tech"]), per_topic=2, total=4),
    )

    # Build the LLM prompt — give it everything, ask for a warm spoken brief
    name = (user.display_name or user.email.split("@")[0]).split()[0]
    now = dt.datetime.now()
    greeting = "Good morning" if now.hour < 12 else ("Good afternoon" if now.hour < 18 else "Good evening")

    parts = [f"It's {greeting.lower()}, {name}. The user just opened Olwen."]
    if weather:
        parts.append(f"Weather: now {weather.get('now_c')}°C, high {weather.get('high_c')}°, low {weather.get('low_c')}°, {_weather_desc(weather.get('code', 0))}.")
    if calendar:
        evs = [f"{(e.get('start') or '')[11:16] or 'all day'} {e.get('title','')}" for e in calendar[:4]]
        parts.append("Today's calendar: " + "; ".join(evs))
    else:
        parts.append("Calendar is empty for the next 24 hours.")
    if tasks:
        ts = [f"({t['priority']}) {t['text']}" for t in tasks[:4]]
        parts.append("Open tasks (top): " + "; ".join(ts))
    if inbox:
        ms = [f"{i['sender']}: {i['subject']}" for i in inbox]
        parts.append("Unread inbox: " + "; ".join(ms))
    if news:
        ns = [f"{n['tag']}: {n['title']}" for n in news[:3]]
        parts.append("News headlines: " + "; ".join(ns))

    context = "\n".join(parts)

    enc = {"claude": user.llm_api_key_enc, "gemini": user.gemini_key_enc, "groq": user.groq_key_enc}.get(user.llm_provider or "")
    if not enc:
        # Deterministic fallback so the brief always says something useful
        narrative = (
            f"{greeting}, {name}. "
            + (f"It's {weather.get('now_c')} degrees outside. " if weather else "")
            + (f"You have {len(calendar)} events today. " if calendar else "Calendar is clear. ")
            + (f"{len(tasks)} open tasks. " if tasks else "")
            + (f"{len(inbox)} new emails waiting." if inbox else "Inbox is quiet.")
        )
        return _result(narrative, weather, calendar, tasks, inbox, news)

    api_key = decrypt_secret(enc)
    prompt = (
        f"You are Olwen, the user's calm AI companion. Write a {greeting.lower()} brief — "
        "4 to 6 short sentences, spoken-word natural, no bullet points, no headers, no markdown. "
        f"Address the user as {name}. Acknowledge weather only if interesting. Mention the most "
        "important calendar event (if any), the top 1–2 tasks, the most pressing unread email "
        "(if any), and weave in a single news headline only if it's genuinely newsworthy. "
        "Tone: warm, brief, no jargon, no 'I hope you...' filler. End with one concrete suggestion "
        "for where to start.\n\nDATA:\n" + context
    )
    try:
        chunks: list[str] = []
        async for c in stream_reply(prompt, [], provider=user.llm_provider, api_key=api_key, memory=[]):
            chunks.append(c)
        narrative = "".join(chunks).strip()
    except Exception:
        narrative = ""
    if not narrative:
        narrative = f"{greeting}, {name}. Olwen is here. Pick up where you left off."
    return _result(narrative, weather, calendar, tasks, inbox, news)


def _result(narrative: str, weather, calendar, tasks, inbox, news) -> dict:
    return {
        "narrative": narrative,
        "weather": weather or None,
        "calendar": calendar,
        "tasks": tasks,
        "inbox": inbox,
        "news": news,
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
    }
