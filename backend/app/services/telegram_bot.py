"""Telegram link — chat with Olwen from your phone and have him do tasks.

A long-polling bot (no public URL needed — Olwen runs locally). The first person
to message the bot is linked as the owner; after that, their messages run through
Olwen's agent (tasks, send a message, your day, queue a coding job…) and the reply
comes back in Telegram. Telegram has a real inbound API, so this is a clean two-way
channel — unlike WhatsApp.
"""
import asyncio

import httpx
from sqlalchemy import select

from app.core.config import settings
from app.core.security import decrypt_secret
from app.models.user import User

_API = "https://api.telegram.org/bot{token}/{method}"
_offset = 0


async def verify_token(token: str) -> dict | None:
    """getMe — returns the bot info if the token is valid, else None."""
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.get(_API.format(token=token, method="getMe"))
            data = r.json()
            return data.get("result") if data.get("ok") else None
    except Exception:  # noqa: BLE001
        return None


async def send_message(token: str, chat_id: str, text: str) -> None:
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            await c.post(_API.format(token=token, method="sendMessage"),
                         json={"chat_id": chat_id, "text": text[:4000]})
    except Exception:  # noqa: BLE001
        pass


async def _get_updates(token: str, offset: int) -> list[dict]:
    async with httpx.AsyncClient(timeout=40) as c:
        r = await c.get(_API.format(token=token, method="getUpdates"),
                        params={"offset": offset, "timeout": 25, "allowed_updates": '["message"]'})
        data = r.json()
        return data.get("result", []) if data.get("ok") else []


async def _agent_reply(text: str, user: User, db) -> str:
    """Run Olwen's agent on a Telegram message and return a plain-text reply."""
    from app.models.installed_skill import InstalledSkill
    from app.services.agent import build_tools, run_agent
    from app.services.olwen_ai import _build_system
    enc = user.gemini_key_enc
    if not enc:
        return "I need a Gemini key connected (Settings → AI) to actually run tasks."
    gemini_key = decrypt_secret(enc)
    installed = list(await db.scalars(
        select(InstalledSkill.skill_key).where(InstalledSkill.user_id == user.id)
    ))
    tools = build_tools(installed)
    system = _build_system([], []) + (
        "\n\nYou are replying over Telegram (text only). Do the task with your tools "
        "and answer in one short message. Surfaces that open a screen (terminal, dev "
        "mode, computer-use) aren't available here — for coding work, use queue_dev_job."
    )
    try:
        result = await run_agent(text, [], gemini_key, settings.gemini_model, system, tools, user, db)
        return (result.get("text") or "Done.").strip()
    except Exception as exc:  # noqa: BLE001
        return f"I hit an error: {exc}"[:300]


async def _handle(token: str, chat_id: str, text: str) -> None:
    from app.core.database import SessionLocal
    async with SessionLocal() as db:
        user = (await db.execute(select(User).where(User.telegram_token_enc.isnot(None)))).scalars().first()
        if user is None:
            return
        # First contact links this chat as the owner.
        if not user.telegram_chat_id:
            user.telegram_chat_id = chat_id
            await db.commit()
            await send_message(token, chat_id,
                               "✦ Connected — I'm Olwen. Text me things like:\n"
                               "• add a task: call the bank\n"
                               "• what's on my plate today?\n"
                               "• message mom on whatsapp: running late\n"
                               "• run a job in olwen: fix the failing tests")
            return
        if user.telegram_chat_id != chat_id:
            await send_message(token, chat_id, "This Olwen is linked to someone else.")
            return
        if text.strip().lower() in ("/start", "/help"):
            await send_message(token, chat_id,
                               "I'm Olwen. Tell me to add/check tasks, send a WhatsApp, "
                               "read your day, or run a coding job — and I'll do it.")
            return
        # Surface the incoming message live on the dashboard.
        from app.services.notifications import push
        await push(user.id, "telegram", title="New Telegram message", body=text[:300],
                   meta={"chat_id": chat_id})
        reply = await _agent_reply(text, user, db)
        await send_message(token, chat_id, reply)


async def telegram_poller() -> None:
    """Background loop: poll the connected bot and route messages to the agent."""
    global _offset
    from app.core.database import SessionLocal
    while True:
        try:
            async with SessionLocal() as db:
                user = (await db.execute(select(User).where(User.telegram_token_enc.isnot(None)))).scalars().first()
                token = decrypt_secret(user.telegram_token_enc) if user else None
            if not token:
                await asyncio.sleep(15)
                continue
            updates = await _get_updates(token, _offset)
            for u in updates:
                _offset = max(_offset, u.get("update_id", 0) + 1)
                msg = u.get("message") or {}
                chat = (msg.get("chat") or {}).get("id")
                text = msg.get("text") or ""
                if chat and text:
                    await _handle(token, str(chat), text)
        except Exception:  # noqa: BLE001
            await asyncio.sleep(5)
