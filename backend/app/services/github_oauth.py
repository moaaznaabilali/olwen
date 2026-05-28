"""GitHub OAuth + thin client for the data Olwen surfaces."""
import datetime as dt
import secrets
from urllib.parse import urlencode

import httpx

from app.core.config import settings

SCOPES = ["read:user", "repo"]                 # minimal: read user + their repos / events

_AUTH = "https://github.com/login/oauth/authorize"
_TOKEN = "https://github.com/login/oauth/access_token"
_API = "https://api.github.com"


def is_configured() -> bool:
    """Legacy env-only check. Prefer services.app_config.github_configured()."""
    return bool(settings.github_client_id and settings.github_client_secret)


def build_auth_url(state: str, client_id: str | None = None) -> str:
    params = {
        "client_id": client_id or settings.github_client_id,
        "redirect_uri": settings.github_redirect_uri,
        "scope": " ".join(SCOPES),
        "state": state,
        "allow_signup": "false",
    }
    return f"{_AUTH}?{urlencode(params)}"


def make_state(user_id: str) -> str:
    import jwt
    payload = {
        "sub": str(user_id),
        "nonce": secrets.token_urlsafe(8),
        "exp": dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=15),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def verify_state(state: str) -> str | None:
    import jwt
    try:
        return jwt.decode(state, settings.jwt_secret, algorithms=[settings.jwt_algorithm]).get("sub")
    except Exception:
        return None


async def exchange_code(code: str, client_id: str | None = None, client_secret: str | None = None) -> dict:
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(
            _TOKEN,
            data={
                "client_id": client_id or settings.github_client_id,
                "client_secret": client_secret or settings.github_client_secret,
                "code": code,
                "redirect_uri": settings.github_redirect_uri,
            },
            headers={"Accept": "application/json"},
        )
        r.raise_for_status()
        return r.json()


def _hdrs(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


async def get_viewer(token: str) -> dict:
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(f"{_API}/user", headers=_hdrs(token))
        r.raise_for_status()
        return r.json()


async def recent_events(token: str, login: str, limit: int = 8) -> list[dict]:
    """Return a normalised list of recent push/PR/issue events for the user."""
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(
            f"{_API}/users/{login}/events",
            headers=_hdrs(token),
            params={"per_page": max(1, min(limit, 30))},
        )
        if r.status_code != 200:
            return []
        events = r.json()
    out: list[dict] = []
    for ev in events:
        kind = ev.get("type") or ""
        repo = (ev.get("repo") or {}).get("name") or ""
        when = ev.get("created_at") or ""
        if kind == "PushEvent":
            commits = (ev.get("payload") or {}).get("commits") or []
            msg = commits[-1].get("message", "").splitlines()[0] if commits else "Push"
            out.append({"kind": "push", "repo": repo, "msg": msg, "when": when})
        elif kind == "PullRequestEvent":
            pr = (ev.get("payload") or {}).get("pull_request") or {}
            action = (ev.get("payload") or {}).get("action") or "updated"
            out.append({"kind": "pr", "repo": repo, "msg": f"PR {action}: {pr.get('title','')}", "when": when})
        elif kind == "IssuesEvent":
            iss = (ev.get("payload") or {}).get("issue") or {}
            action = (ev.get("payload") or {}).get("action") or "updated"
            out.append({"kind": "issue", "repo": repo, "msg": f"Issue {action}: {iss.get('title','')}", "when": when})
        elif kind == "CreateEvent":
            ref_type = (ev.get("payload") or {}).get("ref_type") or "branch"
            ref = (ev.get("payload") or {}).get("ref") or ""
            out.append({"kind": "create", "repo": repo, "msg": f"Created {ref_type} {ref}".strip(), "when": when})
        if len(out) >= limit:
            break
    return out
