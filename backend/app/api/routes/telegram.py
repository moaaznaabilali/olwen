"""Telegram link — connect a bot so you can chat with Olwen from your phone."""
from fastapi import APIRouter, status

from app.api.deps import CurrentUser, SessionDep
from app.core.security import encrypt_secret

router = APIRouter()


@router.post("/connect")
async def connect(payload: dict, user: CurrentUser, session: SessionDep) -> dict:
    """Save + verify a Telegram bot token. Create one with @BotFather, paste the
    token here, then message your bot once (/start) to link your chat."""
    from app.services.telegram_bot import verify_token
    token = (payload.get("token") or "").strip()
    if not token:
        return {"error": "token required"}
    bot = await verify_token(token)
    if not bot:
        return {"error": "that bot token didn't work — check it with @BotFather"}
    user.telegram_token_enc = encrypt_secret(token)
    user.telegram_chat_id = None  # re-link on the next /start
    await session.commit()
    return {"ok": True, "bot": bot.get("username"), "link": f"https://t.me/{bot.get('username')}"}


@router.get("/status")
async def status_(user: CurrentUser) -> dict:
    return {"connected": bool(user.telegram_token_enc), "linked": bool(user.telegram_chat_id)}


@router.delete("/disconnect", status_code=status.HTTP_204_NO_CONTENT)
async def disconnect(user: CurrentUser, session: SessionDep) -> None:
    user.telegram_token_enc = None
    user.telegram_chat_id = None
    await session.commit()
