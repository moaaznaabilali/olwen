"""Google OAuth flow + Gmail REST read.

Lets users connect Gmail with one click instead of fiddling with app passwords.
Uses the standard authorization-code flow; tokens are stored encrypted per user.
"""
import datetime as dt
import secrets
from urllib.parse import urlencode

import httpx

from app.core.config import settings

# Read-only Gmail scope. Restricted scope — works for "Testing" users without
# verification; needs Google verification for general public use.
SCOPES = [
    "openid",
    "email",
    # `gmail.modify` covers read + flag changes (mark-as-read). Existing tokens
    # granted only readonly still read fine; modify actions fail until re-consent.
    "https://www.googleapis.com/auth/gmail.modify",
    # Calendar read-only — list upcoming events for the Today widget.
    "https://www.googleapis.com/auth/calendar.readonly",
]

_AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
_TOKEN = "https://oauth2.googleapis.com/token"
_USERINFO = "https://www.googleapis.com/oauth2/v3/userinfo"
_GMAIL = "https://gmail.googleapis.com/gmail/v1/users/me"
_CAL = "https://www.googleapis.com/calendar/v3"


def is_configured() -> bool:
    """Legacy env-only check. Prefer services.app_config.google_configured()."""
    return bool(settings.google_client_id and settings.google_client_secret)


def build_auth_url(state: str, client_id: str | None = None) -> str:
    params = {
        "client_id": client_id or settings.google_client_id,
        "redirect_uri": settings.google_redirect_uri,
        "response_type": "code",
        "scope": " ".join(SCOPES),
        "access_type": "offline",
        "prompt": "consent",
        "include_granted_scopes": "true",
        "state": state,
    }
    return f"{_AUTH}?{urlencode(params)}"


def make_state(user_id: str) -> str:
    # Sign with the JWT secret so we can verify it back on callback.
    import jwt
    payload = {"sub": str(user_id), "nonce": secrets.token_urlsafe(8),
               "exp": dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=15)}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def verify_state(state: str) -> str | None:
    import jwt
    try:
        payload = jwt.decode(state, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        return payload.get("sub")
    except Exception:
        return None


async def exchange_code(code: str, client_id: str | None = None, client_secret: str | None = None) -> dict:
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(_TOKEN, data={
            "code": code,
            "client_id": client_id or settings.google_client_id,
            "client_secret": client_secret or settings.google_client_secret,
            "redirect_uri": settings.google_redirect_uri,
            "grant_type": "authorization_code",
        })
        resp.raise_for_status()
        return resp.json()


async def refresh_access(refresh_token: str, client_id: str | None = None, client_secret: str | None = None) -> dict:
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.post(_TOKEN, data={
            "refresh_token": refresh_token,
            "client_id": client_id or settings.google_client_id,
            "client_secret": client_secret or settings.google_client_secret,
            "grant_type": "refresh_token",
        })
        resp.raise_for_status()
        return resp.json()


async def get_email_address(access_token: str) -> str:
    async with httpx.AsyncClient(timeout=15) as client:
        resp = await client.get(_USERINFO, headers={"Authorization": f"Bearer {access_token}"})
        resp.raise_for_status()
        return resp.json().get("email", "")


def _b64url_decode(data: str) -> bytes:
    import base64
    pad = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode((data + pad).encode())


def _extract_body(payload: dict) -> str:
    """Walk a Gmail payload tree, prefer text/plain over text/html."""
    import re as _re
    plain: list[str] = []
    html: list[str] = []

    def walk(node: dict) -> None:
        mime = node.get("mimeType", "")
        data = (node.get("body") or {}).get("data")
        if data:
            try:
                txt = _b64url_decode(data).decode("utf-8", errors="replace")
            except Exception:
                txt = ""
            if mime == "text/plain":
                plain.append(txt)
            elif mime == "text/html":
                html.append(txt)
        for p in node.get("parts") or []:
            walk(p)

    walk(payload or {})
    if plain:
        return "\n\n".join(plain).strip()
    if html:
        stripped = _re.sub(r"<[^>]+>", " ", "\n\n".join(html))
        return _re.sub(r"[ \t]+", " ", stripped).strip()
    return ""


async def fetch_calendar_events(access_token: str, hours_ahead: int = 36, limit: int = 10) -> list[dict]:
    """List upcoming primary-calendar events. Raises HTTPStatusError on non-200
    so the route can translate it into a user-actionable message."""
    now = dt.datetime.now(dt.timezone.utc)
    later = now + dt.timedelta(hours=hours_ahead)
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(
            f"{_CAL}/calendars/primary/events",
            headers={"Authorization": f"Bearer {access_token}"},
            params={
                "timeMin": now.isoformat().replace("+00:00", "Z"),
                "timeMax": later.isoformat().replace("+00:00", "Z"),
                "singleEvents": "true",
                "orderBy": "startTime",
                "maxResults": max(1, min(limit, 20)),
            },
        )
        r.raise_for_status()
        items = r.json().get("items") or []
    out: list[dict] = []
    for ev in items:
        start = (ev.get("start") or {}).get("dateTime") or (ev.get("start") or {}).get("date") or ""
        end = (ev.get("end") or {}).get("dateTime") or (ev.get("end") or {}).get("date") or ""
        out.append({
            "id": ev.get("id", ""),
            "title": ev.get("summary") or "(no title)",
            "start": start,
            "end": end,
            "location": ev.get("location") or "",
            "url": ev.get("htmlLink") or "",
        })
    return out


async def send_email(
    access_token: str, *, to: list[str], subject: str, body: str,
    from_addr: str, thread_id: str | None = None,
    in_reply_to: str | None = None, references: str | None = None,
) -> str:
    """Send email via Gmail's REST API. Returns Gmail message id.

    `thread_id` keeps the reply in the same conversation.
    """
    import base64
    from email.message import EmailMessage as _Msg
    msg = _Msg()
    msg["From"] = from_addr
    msg["To"] = ", ".join(to)
    msg["Subject"] = subject
    if in_reply_to: msg["In-Reply-To"] = in_reply_to
    if references:  msg["References"] = references
    msg.set_content(body)
    raw = base64.urlsafe_b64encode(bytes(msg)).decode().rstrip("=")
    payload: dict = {"raw": raw}
    if thread_id: payload["threadId"] = thread_id
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.post(
            f"{_GMAIL}/messages/send",
            headers={"Authorization": f"Bearer {access_token}"},
            json=payload,
        )
        r.raise_for_status()
        return r.json().get("id", "")


async def get_message_headers(access_token: str, msg_id: str) -> dict:
    """Fetch just the headers of a Gmail message — used to build threaded replies."""
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(
            f"{_GMAIL}/messages/{msg_id}",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"format": "metadata", "metadataHeaders": ["From", "To", "Subject", "Message-ID", "References"]},
        )
        r.raise_for_status()
        md = r.json()
        return {
            "thread_id": md.get("threadId", ""),
            "headers": {h["name"]: h["value"] for h in (md.get("payload", {}).get("headers") or [])},
        }


async def mark_read(access_token: str, msg_id: str) -> bool:
    """Remove the UNREAD label from a Gmail message. Requires gmail.modify scope."""
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.post(
            f"{_GMAIL}/messages/{msg_id}/modify",
            headers={"Authorization": f"Bearer {access_token}"},
            json={"removeLabelIds": ["UNREAD"]},
        )
        return r.status_code == 200


async def fetch_message(access_token: str, msg_id: str) -> dict | None:
    """Return a full message: {uid, sender, subject, body, date, unread}."""
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(
            f"{_GMAIL}/messages/{msg_id}",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"format": "full"},
        )
        if r.status_code != 200:
            return None
        md = r.json()
        payload = md.get("payload") or {}
        headers = {h["name"]: h["value"] for h in (payload.get("headers") or [])}
        return {
            "uid": md.get("id", msg_id),
            "sender": headers.get("From", ""),
            "subject": headers.get("Subject", "(no subject)"),
            "body": _extract_body(payload),
            "date": headers.get("Date", ""),
            "unread": "UNREAD" in (md.get("labelIds") or []),
        }


async def fetch_inbox(access_token: str, limit: int = 12) -> list[dict]:
    """Return [{uid, sender, subject, snippet, date, unread}, ...] from Gmail."""
    async with httpx.AsyncClient(timeout=20) as client:
        # 1) list message ids
        r = await client.get(
            f"{_GMAIL}/messages",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"maxResults": max(1, min(limit, 25)), "labelIds": "INBOX"},
        )
        r.raise_for_status()
        ids = [m["id"] for m in (r.json().get("messages") or [])]

        out: list[dict] = []
        for mid in ids:
            mr = await client.get(
                f"{_GMAIL}/messages/{mid}",
                headers={"Authorization": f"Bearer {access_token}"},
                params={"format": "metadata", "metadataHeaders": ["From", "Subject", "Date"]},
            )
            if mr.status_code != 200:
                continue
            md = mr.json()
            headers = {h["name"]: h["value"] for h in (md.get("payload", {}).get("headers") or [])}
            label_ids = md.get("labelIds") or []
            out.append({
                "uid": md.get("id", mid),
                "sender": headers.get("From", ""),
                "subject": headers.get("Subject", "(no subject)"),
                "snippet": md.get("snippet", ""),
                "date": headers.get("Date", ""),
                "unread": "UNREAD" in label_ids,
            })
        return out
