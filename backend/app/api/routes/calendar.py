"""Google Calendar — upcoming events for the Today widget.

Piggybacks on the Gmail OAuth tokens already stored in `email_accounts` for
provider='google'. If the user connected Gmail BEFORE we added the calendar
scope, they'll need to disconnect/reconnect to re-consent.
"""
import datetime as dt

import httpx
from fastapi import APIRouter, HTTPException
from sqlalchemy import select

from app.api.deps import CurrentUser, SessionDep
from app.core.security import decrypt_secret, encrypt_secret
from app.models.email_account import EmailAccount
from app.services import app_config as app_cfg
from app.services import google_oauth

router = APIRouter()


async def _google_account(user_id, session: SessionDep) -> EmailAccount | None:
    return await session.scalar(
        select(EmailAccount)
        .where(EmailAccount.user_id == user_id, EmailAccount.provider == "google")
        .order_by(EmailAccount.created_at)
    )


@router.get("/events")
async def upcoming(user: CurrentUser, session: SessionDep, hours: int = 36, limit: int = 10) -> dict:
    acc = await _google_account(user.id, session)
    if acc is None or not acc.access_token_enc:
        raise HTTPException(
            status_code=404,
            detail="Connect Google (via Email) to see your calendar.",
        )
    access = decrypt_secret(acc.access_token_enc)
    # refresh if expired
    if acc.token_expiry is None or acc.token_expiry <= dt.datetime.now(dt.timezone.utc):
        if not acc.refresh_token_enc:
            raise HTTPException(
                status_code=401,
                detail="Google session expired. Reconnect the account in Settings → Email.",
            )
        cid, csec = await app_cfg.google_creds(session)
        tokens = await google_oauth.refresh_access(decrypt_secret(acc.refresh_token_enc), client_id=cid, client_secret=csec)
        access = tokens["access_token"]
        acc.access_token_enc = encrypt_secret(access)
        acc.token_expiry = dt.datetime.now(dt.timezone.utc) + dt.timedelta(
            seconds=int(tokens.get("expires_in", 3600)) - 60
        )
        await session.commit()

    try:
        events = await google_oauth.fetch_calendar_events(access, hours_ahead=hours, limit=limit)
    except httpx.HTTPStatusError as exc:
        body = (exc.response.text or "")[:600]
        code = exc.response.status_code
        if code == 403 and ("Calendar API has not been used" in body or "accessNotConfigured" in body):
            raise HTTPException(
                status_code=409,
                detail="CALENDAR_API_DISABLED: The Calendar API isn't enabled on your Google Cloud project. Enable it and try again.",
            ) from exc
        if code == 403:
            raise HTTPException(status_code=409, detail=f"CALENDAR_FORBIDDEN: Google rejected the request. ({body[:200]})") from exc
        raise HTTPException(status_code=502, detail=f"Upstream calendar error {code}.") from exc
    return {"events": events}


@router.get("/configured")
async def configured(user: CurrentUser, session: SessionDep) -> dict:
    """Why calendar can or can't load — drives the empty-state copy in the widget."""
    rows = list(await session.scalars(select(EmailAccount).where(EmailAccount.user_id == user.id)))
    has_google = any(r.provider == "google" for r in rows)
    has_imap_gmail = any(
        r.provider == "imap" and (r.email or "").lower().endswith(("@gmail.com", "@googlemail.com"))
        for r in rows
    )
    server_oauth_ready = await app_cfg.google_configured(session)

    if has_google:
        need = "none"
    elif not server_oauth_ready:
        # Server has no Google OAuth client_id/secret — Sign-in-with-Google can't
        # even be shown in the email wizard. The fix is to set up OAuth first.
        need = "setup_server_oauth"
    elif has_imap_gmail:
        need = "switch_to_oauth"   # server is ready, user just needs to reconnect via OAuth
    else:
        need = "connect_google"

    return {
        "connected": has_google,
        "has_gmail_imap": has_imap_gmail,
        "server_oauth_ready": server_oauth_ready,
        "needs": need,
    }
