"""Read/write deployment-level config (encrypted) from the DB.

Used by `services/github_oauth.py` so admins can paste GitHub OAuth credentials
through the UI instead of editing .env and restarting.
"""
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings as env_settings
from app.core.security import decrypt_secret, encrypt_secret
from app.models.app_config import AppConfig


async def get_value(session: AsyncSession, key: str) -> str | None:
    row = await session.get(AppConfig, key)
    if row is None:
        return None
    try:
        return decrypt_secret(row.value)
    except Exception:
        return None


async def set_value(session: AsyncSession, key: str, value: str) -> None:
    enc = encrypt_secret(value)
    row = await session.get(AppConfig, key)
    if row is None:
        session.add(AppConfig(key=key, value=enc))
    else:
        row.value = enc
    await session.commit()


async def delete_value(session: AsyncSession, key: str) -> None:
    row = await session.get(AppConfig, key)
    if row is not None:
        await session.delete(row)
        await session.commit()


# ---------- GitHub OAuth creds — DB first, then env fallback ----------
GH_CID = "github_client_id"
GH_CSEC = "github_client_secret"


async def github_creds(session: AsyncSession) -> tuple[str, str]:
    """(client_id, client_secret) — empty strings if neither DB nor env has them."""
    cid = await get_value(session, GH_CID) or env_settings.github_client_id
    csec = await get_value(session, GH_CSEC) or env_settings.github_client_secret
    return cid or "", csec or ""


async def github_configured(session: AsyncSession) -> bool:
    cid, csec = await github_creds(session)
    return bool(cid and csec)


# ---------- Strava OAuth creds — same pattern ----------
SV_CID = "strava_client_id"
SV_CSEC = "strava_client_secret"


async def strava_creds(session: AsyncSession) -> tuple[str, str]:
    cid = await get_value(session, SV_CID) or ""
    csec = await get_value(session, SV_CSEC) or ""
    return cid or "", csec or ""


async def strava_configured(session: AsyncSession) -> bool:
    cid, csec = await strava_creds(session)
    return bool(cid and csec)


# ---------- Google OAuth creds — same pattern ----------
GG_CID = "google_client_id"
GG_CSEC = "google_client_secret"


async def google_creds(session: AsyncSession) -> tuple[str, str]:
    cid = await get_value(session, GG_CID) or env_settings.google_client_id
    csec = await get_value(session, GG_CSEC) or env_settings.google_client_secret
    return cid or "", csec or ""


async def google_configured(session: AsyncSession) -> bool:
    cid, csec = await google_creds(session)
    return bool(cid and csec)
