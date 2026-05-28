"""GitHub OAuth + recent activity for the dashboard widget."""
import uuid

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import CurrentUser, SessionDep
from app.core.config import settings
from app.core.database import SessionLocal
from app.core.database import SessionLocal as _SessionLocal  # noqa: F401  (alias for clarity)
from app.core.security import decrypt_secret, encrypt_secret
from app.models.github_account import GithubAccount
from app.services import app_config as app_cfg
from app.services import github_oauth

router = APIRouter()


class ConnectPatRequest(BaseModel):
    token: str = Field(min_length=20, max_length=255)


class OAuthSetupRequest(BaseModel):
    client_id: str = Field(min_length=10, max_length=80)
    client_secret: str = Field(min_length=10, max_length=80)


@router.get("/configured")
async def configured(session: SessionDep) -> dict:
    """Tells the UI which connect paths are available, checking DB first."""
    ok = await app_cfg.github_configured(session)
    return {
        "configured": ok,
        "oauth_configured": ok,
        "pat_supported": True,
        "redirect_uri": settings.github_redirect_uri,  # show this in the setup screen
    }


@router.post("/oauth/setup")
async def oauth_setup(data: OAuthSetupRequest, user: CurrentUser, session: SessionDep) -> dict:
    """Persist GitHub OAuth client credentials in the DB so Sign-in-with-GitHub
    starts working immediately — no env vars, no restart.

    Any authenticated user can do this since it's a deployment-wide setting and
    Olwen is currently single-team. (A future admin-role check goes here.)
    """
    await app_cfg.set_value(session, app_cfg.GH_CID, data.client_id.strip())
    await app_cfg.set_value(session, app_cfg.GH_CSEC, data.client_secret.strip())
    return {"ok": True}


@router.post("/pat")
async def connect_pat(data: ConnectPatRequest, user: CurrentUser, session: SessionDep) -> dict:
    """Connect via a Personal Access Token. The token is validated by calling
    GET /user — if that succeeds, the token is good and we store it the same
    way an OAuth access_token would be stored."""
    token = data.token.strip()
    try:
        viewer = await github_oauth.get_viewer(token)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="That token didn't work. Make sure it has read:user + repo scopes.",
        )

    existing = await session.scalar(select(GithubAccount).where(GithubAccount.user_id == user.id))
    if existing:
        existing.access_token_enc = encrypt_secret(token)
        existing.github_login = viewer.get("login", "")
        existing.github_user_id = str(viewer.get("id", ""))
        existing.scope = "pat"
        existing.avatar_url = viewer.get("avatar_url")
    else:
        session.add(GithubAccount(
            user_id=user.id,
            github_login=viewer.get("login", ""),
            github_user_id=str(viewer.get("id", "")),
            access_token_enc=encrypt_secret(token),
            scope="pat",
            avatar_url=viewer.get("avatar_url"),
        ))
    await session.commit()
    return {"ok": True, "login": viewer.get("login", "")}


@router.get("/oauth/start")
async def start(user: CurrentUser, session: SessionDep) -> dict:
    cid, _ = await app_cfg.github_creds(session)
    if not cid:
        raise HTTPException(
            status_code=503,
            detail="GitHub OAuth isn't set up yet. Add a Client ID and Secret first in Settings.",
        )
    state = github_oauth.make_state(str(user.id))
    return {"auth_url": github_oauth.build_auth_url(state, client_id=cid)}


@router.get("/oauth/callback")
async def callback(code: str | None = None, state: str | None = None, error: str | None = None) -> RedirectResponse:
    target = settings.github_post_oauth_redirect
    if error or not code or not state:
        return RedirectResponse(url=f"{target}&error={error or 'cancelled'}")
    user_id = github_oauth.verify_state(state)
    if user_id is None:
        return RedirectResponse(url=f"{target}&error=bad_state")
    # Look up creds (DB > env) using a fresh session
    async with SessionLocal() as session:
        cid, csec = await app_cfg.github_creds(session)
    try:
        tokens = await github_oauth.exchange_code(code, client_id=cid, client_secret=csec)
        access = tokens.get("access_token")
        if not access:
            raise RuntimeError("no access_token in response")
        viewer = await github_oauth.get_viewer(access)
    except Exception as exc:  # noqa: BLE001
        return RedirectResponse(url=f"{target}&error={str(exc)[:60]}")

    async with SessionLocal() as session:
        existing = await session.scalar(
            select(GithubAccount).where(GithubAccount.user_id == uuid.UUID(user_id))
        )
        if existing:
            existing.access_token_enc = encrypt_secret(access)
            existing.github_login = viewer.get("login", "")
            existing.github_user_id = str(viewer.get("id", ""))
            existing.scope = tokens.get("scope")
            existing.avatar_url = viewer.get("avatar_url")
        else:
            session.add(GithubAccount(
                user_id=uuid.UUID(user_id),
                github_login=viewer.get("login", ""),
                github_user_id=str(viewer.get("id", "")),
                access_token_enc=encrypt_secret(access),
                scope=tokens.get("scope"),
                avatar_url=viewer.get("avatar_url"),
            ))
        await session.commit()
    return RedirectResponse(url=target)


@router.get("/account")
async def get_account(user: CurrentUser, session: SessionDep) -> dict:
    acc = await session.scalar(select(GithubAccount).where(GithubAccount.user_id == user.id))
    if acc is None:
        return {"connected": False}
    return {
        "connected": True,
        "login": acc.github_login,
        "avatar_url": acc.avatar_url,
    }


@router.delete("/account", status_code=status.HTTP_204_NO_CONTENT)
async def disconnect(user: CurrentUser, session: SessionDep) -> None:
    acc = await session.scalar(select(GithubAccount).where(GithubAccount.user_id == user.id))
    if acc:
        await session.delete(acc)
        await session.commit()


@router.get("/events")
async def events(user: CurrentUser, session: SessionDep, limit: int = 8) -> dict:
    acc = await session.scalar(select(GithubAccount).where(GithubAccount.user_id == user.id))
    if acc is None:
        raise HTTPException(status_code=404, detail="GitHub not connected")
    token = decrypt_secret(acc.access_token_enc)
    rows = await github_oauth.recent_events(token, acc.github_login, limit)
    return {"login": acc.github_login, "events": rows}
