"""Strava — OAuth + recent activity for the Health widget."""
import datetime as dt
import uuid

import httpx
from fastapi import APIRouter, HTTPException, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import CurrentUser, SessionDep
from app.core.database import SessionLocal
from app.core.security import decrypt_secret, encrypt_secret
from app.models.strava_account import StravaAccount
from app.services import app_config as app_cfg
from app.services import strava_oauth

router = APIRouter()


class OAuthSetupRequest(BaseModel):
    client_id: str = Field(min_length=2, max_length=80)
    client_secret: str = Field(min_length=10, max_length=200)


@router.get("/configured")
async def configured(session: SessionDep) -> dict:
    ok = await app_cfg.strava_configured(session)
    return {"configured": ok, "redirect_uri": strava_oauth.REDIRECT_URI}


@router.post("/oauth/setup")
async def setup(data: OAuthSetupRequest, user: CurrentUser, session: SessionDep) -> dict:
    """Save Strava client credentials in DB — no env vars, no restart."""
    await app_cfg.set_value(session, app_cfg.SV_CID, data.client_id.strip())
    await app_cfg.set_value(session, app_cfg.SV_CSEC, data.client_secret.strip())
    return {"ok": True}


@router.get("/oauth/start")
async def start(user: CurrentUser, session: SessionDep) -> dict:
    cid, _ = await app_cfg.strava_creds(session)
    if not cid:
        raise HTTPException(status_code=503, detail="Strava OAuth not set up yet.")
    state = strava_oauth.make_state(str(user.id))
    return {"auth_url": strava_oauth.build_auth_url(state, client_id=cid)}


@router.get("/oauth/callback")
async def callback(code: str | None = None, state: str | None = None,
                   error: str | None = None) -> RedirectResponse:
    target = "http://localhost:3100/?settings=connections&strava=1"
    if error or not code or not state:
        return RedirectResponse(url=f"{target}&error={error or 'cancelled'}")
    user_id = strava_oauth.verify_state(state)
    if user_id is None:
        return RedirectResponse(url=f"{target}&error=bad_state")

    async with SessionLocal() as session:
        cid, csec = await app_cfg.strava_creds(session)
    try:
        tokens = await strava_oauth.exchange_code(code, client_id=cid, client_secret=csec)
        access = tokens["access_token"]
        refresh = tokens["refresh_token"]
        expires_at = dt.datetime.fromtimestamp(tokens["expires_at"], dt.timezone.utc)
        athlete = tokens.get("athlete") or await strava_oauth.get_athlete(access)
    except Exception as exc:  # noqa: BLE001
        return RedirectResponse(url=f"{target}&error={str(exc)[:60]}")

    name = f"{athlete.get('firstname', '')} {athlete.get('lastname', '')}".strip() or athlete.get("username", "")
    async with SessionLocal() as session:
        existing = await session.scalar(
            select(StravaAccount).where(StravaAccount.user_id == uuid.UUID(user_id))
        )
        if existing:
            existing.athlete_id = str(athlete.get("id", ""))
            existing.athlete_name = name
            existing.avatar_url = athlete.get("profile") or athlete.get("profile_medium")
            existing.access_token_enc = encrypt_secret(access)
            existing.refresh_token_enc = encrypt_secret(refresh)
            existing.token_expiry = expires_at
        else:
            session.add(StravaAccount(
                user_id=uuid.UUID(user_id),
                athlete_id=str(athlete.get("id", "")),
                athlete_name=name,
                avatar_url=athlete.get("profile") or athlete.get("profile_medium"),
                access_token_enc=encrypt_secret(access),
                refresh_token_enc=encrypt_secret(refresh),
                token_expiry=expires_at,
            ))
        await session.commit()

    return RedirectResponse(url=target)


@router.get("/account")
async def account(user: CurrentUser, session: SessionDep) -> dict:
    acc = await session.scalar(select(StravaAccount).where(StravaAccount.user_id == user.id))
    if acc is None:
        return {"connected": False}
    return {
        "connected": True,
        "athlete_name": acc.athlete_name,
        "avatar_url": acc.avatar_url,
    }


@router.delete("/account", status_code=status.HTTP_204_NO_CONTENT)
async def disconnect(user: CurrentUser, session: SessionDep) -> None:
    acc = await session.scalar(select(StravaAccount).where(StravaAccount.user_id == user.id))
    if acc:
        await session.delete(acc); await session.commit()


async def _fresh_access(acc: StravaAccount, session: SessionDep) -> str:
    if acc.token_expiry > dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=30):
        return decrypt_secret(acc.access_token_enc)
    cid, csec = await app_cfg.strava_creds(session)
    tokens = await strava_oauth.refresh_access(decrypt_secret(acc.refresh_token_enc), client_id=cid, client_secret=csec)
    acc.access_token_enc = encrypt_secret(tokens["access_token"])
    acc.refresh_token_enc = encrypt_secret(tokens["refresh_token"])
    acc.token_expiry = dt.datetime.fromtimestamp(tokens["expires_at"], dt.timezone.utc)
    await session.commit()
    return tokens["access_token"]


@router.get("/activities")
async def activities(user: CurrentUser, session: SessionDep, limit: int = 8) -> dict:
    acc = await session.scalar(select(StravaAccount).where(StravaAccount.user_id == user.id))
    if acc is None:
        raise HTTPException(status_code=404, detail="Strava not connected")
    access = await _fresh_access(acc, session)
    try:
        items = await strava_oauth.recent_activities(access, limit)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 401:
            raise HTTPException(status_code=401, detail="Strava session expired — reconnect.") from exc
        raise HTTPException(status_code=502, detail=f"Strava error {exc.response.status_code}") from exc
    return {"athlete": acc.athlete_name, "activities": items}
