"""Email — connect any IMAP/SMTP account; read & triage the inbox."""
import json
import uuid

import datetime as dt

import httpx

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import CurrentUser, SessionDep
from app.core.config import settings
from app.core.database import SessionLocal
from app.core.security import decrypt_secret, encrypt_secret
from app.models.email_account import EmailAccount
from app.models.installed_skill import InstalledSkill
from app.models.memory import Memory
from app.schemas.email import (
    ComposeRequest,
    DraftReplyResponse,
    EmailAccountCreate,
    EmailAccountRead,
    EmailAction,
    EmailFull,
    EmailMessage,
    EmailSummary,
    ReplyRequest,
    SendResponse,
    TriagedEmail,
    TriageResponse,
)
from app.services import app_config as app_cfg
from app.services import google_oauth
from app.services.mail import (
    detect_servers,
    fetch_inbox as imap_fetch,
    fetch_one as imap_fetch_one,
    login_ok,
    mark_read as imap_mark_read,
    send_smtp as imap_send,
)
from app.services.olwen_ai import _build_system, stream_reply

router = APIRouter()


def _resolve_servers(data: EmailAccountCreate) -> tuple[str, int, str, int]:
    if data.imap_host and data.smtp_host:
        return data.imap_host, data.imap_port, data.smtp_host, data.smtp_port
    auto = detect_servers(str(data.email))
    if auto is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unknown provider — please provide imap_host and smtp_host.",
        )
    return auto


async def _first_account(user_id, session: SessionDep) -> EmailAccount | None:
    return await session.scalar(
        select(EmailAccount).where(EmailAccount.user_id == user_id).order_by(EmailAccount.created_at)
    )


async def _ensure_email_skill(user_id, session: SessionDep) -> None:
    has = await session.scalar(
        select(InstalledSkill).where(InstalledSkill.user_id == user_id, InstalledSkill.skill_key == "email")
    )
    if not has:
        session.add(InstalledSkill(user_id=user_id, skill_key="email"))
        await session.commit()


async def _fetch_for_account(acc: EmailAccount, session: SessionDep, limit: int) -> list[dict]:
    """Read inbox for any account type. Refreshes the OAuth token if needed."""
    if acc.provider == "google" and acc.access_token_enc:
        access = decrypt_secret(acc.access_token_enc)
        # refresh if expired (or no expiry recorded)
        needs_refresh = acc.token_expiry is None or acc.token_expiry <= dt.datetime.now(dt.timezone.utc)
        if needs_refresh and acc.refresh_token_enc:
            tokens = await google_oauth.refresh_access(decrypt_secret(acc.refresh_token_enc))
            access = tokens["access_token"]
            acc.access_token_enc = encrypt_secret(access)
            acc.token_expiry = dt.datetime.now(dt.timezone.utc) + dt.timedelta(
                seconds=int(tokens.get("expires_in", 3600)) - 60
            )
            await session.commit()
        return await google_oauth.fetch_inbox(access, limit)

    # IMAP path
    msgs = await imap_fetch(
        acc.imap_host or "", acc.imap_port, acc.email,
        decrypt_secret(acc.password_enc or ""), limit,
    )
    return [{
        "uid": m.uid, "sender": m.sender, "subject": m.subject,
        "snippet": m.snippet, "date": m.date_iso, "unread": m.unread,
    } for m in msgs]


@router.get("/accounts", response_model=list[EmailAccountRead])
async def list_accounts(user: CurrentUser, session: SessionDep) -> list[EmailAccount]:
    rows = await session.scalars(
        select(EmailAccount).where(EmailAccount.user_id == user.id).order_by(EmailAccount.created_at)
    )
    return list(rows)


@router.post("/accounts", response_model=EmailAccountRead, status_code=status.HTTP_201_CREATED)
async def connect_account(data: EmailAccountCreate, user: CurrentUser, session: SessionDep) -> EmailAccount:
    imap_host, imap_port, smtp_host, smtp_port = _resolve_servers(data)
    ok, reason = await login_ok(imap_host, imap_port, str(data.email), data.password)
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Couldn't sign in. Check your email + app password. ({reason[:120]})",
        )
    acc = EmailAccount(
        user_id=user.id, email=str(data.email),
        imap_host=imap_host, imap_port=imap_port,
        smtp_host=smtp_host, smtp_port=smtp_port,
        password_enc=encrypt_secret(data.password),
    )
    session.add(acc); await session.commit(); await session.refresh(acc)
    await _ensure_email_skill(user.id, session)
    return acc


@router.delete("/accounts/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
async def disconnect(account_id: uuid.UUID, user: CurrentUser, session: SessionDep) -> None:
    acc = await session.get(EmailAccount, account_id)
    if acc is None or acc.user_id != user.id:
        raise HTTPException(status_code=404, detail="Account not found")
    await session.delete(acc); await session.commit()


@router.get("/inbox", response_model=list[EmailMessage])
async def inbox(user: CurrentUser, session: SessionDep, limit: int = 12) -> list[EmailMessage]:
    acc = await _first_account(user.id, session)
    if acc is None:
        raise HTTPException(status_code=404, detail="No email account connected")
    try:
        rows = await _fetch_for_account(acc, session, max(1, min(limit, 25)))
    except httpx.HTTPStatusError as exc:
        # Translate Google's opaque 403 into something the UI can act on.
        body = (exc.response.text or "")[:600]
        code = exc.response.status_code
        if code == 403 and ("Gmail API has not been used" in body or "accessNotConfigured" in body or "PERMISSION_DENIED" in body):
            raise HTTPException(
                status_code=409,                    # Conflict — server is reachable, config is wrong
                detail="GMAIL_API_DISABLED: The Gmail API isn't enabled on your Google Cloud project. Enable it and try again.",
            ) from exc
        if code == 403:
            raise HTTPException(
                status_code=409,
                detail=f"GMAIL_FORBIDDEN: Google rejected the request. Re-authenticate the account and make sure Gmail API is enabled. ({body[:200]})",
            ) from exc
        raise HTTPException(status_code=502, detail=f"Upstream Gmail error {code}.") from exc
    return [EmailMessage(**r) for r in rows]


@router.post("/triage", response_model=TriageResponse)
async def triage(user: CurrentUser, session: SessionDep, limit: int = 10) -> TriageResponse:
    """One AI call: priority + a short suggested action per unread email."""
    acc = await _first_account(user.id, session)
    if acc is None:
        raise HTTPException(status_code=404, detail="No email account connected")
    rows = await _fetch_for_account(acc, session, max(1, min(limit, 25)))
    unread = [r for r in rows if r["unread"]] or rows  # if no unread, triage recent
    if not unread:
        return TriageResponse(emails=[])

    listing = "\n".join(
        f"{i + 1}. From: {m['sender']}\n   Subject: {m['subject']}\n   Preview: {m['snippet'][:200]}"
        for i, m in enumerate(unread)
    )
    prompt = (
        "Here are recent emails from my inbox:\n" + listing
        + "\n\nFor EACH email, in the SAME order, judge how important it is and what to do.\n"
        'Return ONLY a JSON array, one object per email: '
        '[{"priority":"high|med|low","suggestion":"≤14 words imperative — e.g. Reply today / Skim later / Ignore"}].'
    )
    # Use the user's active provider to call the model.
    provider = user.llm_provider
    enc = {"claude": user.llm_api_key_enc, "gemini": user.gemini_key_enc, "groq": user.groq_key_enc}.get(provider or "")
    if not enc:
        raise HTTPException(status_code=400, detail="Connect an AI key first (Settings → Connections).")
    api_key = decrypt_secret(enc)

    # collect (non-stream) — reuse stream_reply which knows providers
    rows = await session.scalars(select(Memory).where(Memory.user_id == user.id).limit(40))
    memories = [r.content for r in rows]
    system = _build_system(memories, ["Email — triage and reply"])
    chunks: list[str] = []
    async for c in stream_reply(prompt, [], provider=provider, api_key=api_key, memory=memories):
        chunks.append(c)
    text = "".join(chunks)
    try:
        s, e = text.index("["), text.rindex("]") + 1
        arr = json.loads(text[s:e])
    except Exception:
        arr = []
    out: list[TriagedEmail] = []
    for i, m in enumerate(unread):
        info = arr[i] if i < len(arr) and isinstance(arr[i], dict) else {}
        out.append(TriagedEmail(
            uid=m["uid"], sender=m["sender"], subject=m["subject"], snippet=m["snippet"],
            date=m["date"], unread=m["unread"],
            priority=str(info.get("priority", "low")).lower(),
            suggestion=str(info.get("suggestion", "")).strip(),
        ))
    return TriageResponse(emails=out)


async def _user_accounts(user_id, session: SessionDep) -> list[EmailAccount]:
    rows = await session.scalars(
        select(EmailAccount).where(EmailAccount.user_id == user_id).order_by(EmailAccount.created_at)
    )
    return list(rows)


async def _fetch_one_any(user_id, session: SessionDep, uid: str) -> dict | None:
    """Try every connected account — the message UID might live in any of them."""
    for acc in await _user_accounts(user_id, session):
        try:
            msg = await _fetch_one_for_account(acc, session, uid)
            if msg is not None and (msg.get("body") or msg.get("subject")):
                return msg
        except Exception:
            continue
    return None


async def _fetch_one_for_account(acc: EmailAccount, session: SessionDep, uid: str) -> dict | None:
    """Return the full body of one message — dispatched by provider."""
    if acc.provider == "google" and acc.access_token_enc:
        access = decrypt_secret(acc.access_token_enc)
        needs_refresh = acc.token_expiry is None or acc.token_expiry <= dt.datetime.now(dt.timezone.utc)
        if needs_refresh and acc.refresh_token_enc:
            tokens = await google_oauth.refresh_access(decrypt_secret(acc.refresh_token_enc))
            access = tokens["access_token"]
            acc.access_token_enc = encrypt_secret(access)
            acc.token_expiry = dt.datetime.now(dt.timezone.utc) + dt.timedelta(
                seconds=int(tokens.get("expires_in", 3600)) - 60
            )
            await session.commit()
        return await google_oauth.fetch_message(access, uid)

    msg = await imap_fetch_one(
        acc.imap_host or "", acc.imap_port, acc.email,
        decrypt_secret(acc.password_enc or ""), uid,
    )
    if msg is None:
        return None
    return {
        "uid": msg.uid, "sender": msg.sender, "subject": msg.subject,
        "body": msg.body, "date": msg.date_iso, "unread": msg.unread,
    }


@router.get("/messages/{uid}", response_model=EmailFull)
async def get_message(uid: str, user: CurrentUser, session: SessionDep) -> EmailFull:
    accounts = await _user_accounts(user.id, session)
    if not accounts:
        raise HTTPException(status_code=404, detail="No email account connected")
    msg = await _fetch_one_any(user.id, session, uid)
    if msg is None:
        raise HTTPException(status_code=404, detail="Message not found")
    return EmailFull(**msg)


@router.post("/messages/{uid}/summarize", response_model=EmailSummary)
async def summarize_message(
    uid: str,
    user: CurrentUser,
    session: SessionDep,
    sender: str = "",
    subject: str = "",
    snippet: str = "",
) -> EmailSummary:
    """One AI call: 2 short sentences — what it's about + what to do.

    Falls back to the snippet/subject the client already has if the full body
    can't be fetched (e.g. message lives in a different account).
    """
    accounts = await _user_accounts(user.id, session)
    if not accounts:
        raise HTTPException(status_code=404, detail="No email account connected")
    msg = await _fetch_one_any(user.id, session, uid)
    if msg is None:
        # synthesize from the client-provided hints so Olwen can still summarize
        if not (sender or subject or snippet):
            raise HTTPException(status_code=404, detail="Message not found")
        msg = {
            "uid": uid, "sender": sender, "subject": subject or "(no subject)",
            "body": snippet, "date": "", "unread": False,
        }

    provider = user.llm_provider
    enc = {"claude": user.llm_api_key_enc, "gemini": user.gemini_key_enc, "groq": user.groq_key_enc}.get(provider or "")
    body = (msg.get("body") or "").strip()
    sender_name = msg.get("sender") or sender or "someone"
    subj = msg.get("subject") or subject or "(no subject)"

    # Deterministic fallback so Olwen always has something to say,
    # even with no AI key or an upstream LLM failure.
    def _local() -> EmailSummary:
        preview = body[:280].strip()
        text = (
            f"This is from {sender_name}, subject {subj}. It says: {preview}"
            if preview else
            f"This is from {sender_name}, subject {subj}. I couldn't load the body — open the email to read it."
        )
        return EmailSummary(uid=uid, summary=text, actions=[])

    if not enc:
        return _local()

    api_key = decrypt_secret(enc)
    prompt = (
        f"Email from {sender_name}\n"
        f"Subject: {subj}\n\n"
        f"{body[:4000]}\n\n"
        "Speak as Olwen, the user's assistant. Return ONLY a single JSON object, no prose:\n"
        '{"summary": "<2 short sentences: what it says + what they should do>", '
        '"actions": [{"label":"<2-4 words imperative>","kind":"open_url|reply|reminder|task",'
        '"payload":"<URL for open_url; ISO date for reminder; else empty>",'
        '"description":"<<=12 words, plain words for what this does>"}]}'
        "\nOnly include actions that are clearly worth doing (link to click, RSVP, "
        "follow-up reply, deadline). Max 3. Empty array if nothing actionable."
    )
    rows = await session.scalars(select(Memory).where(Memory.user_id == user.id).limit(20))
    memories = [r.content for r in rows]
    try:
        chunks: list[str] = []
        async for c in stream_reply(prompt, [], provider=provider, api_key=api_key, memory=memories):
            chunks.append(c)
        raw = "".join(chunks).strip()
    except Exception:
        return _local()
    if not raw:
        return _local()
    # Best-effort JSON extraction (LLMs sometimes wrap with prose/fences)
    try:
        s, e = raw.index("{"), raw.rindex("}") + 1
        obj = json.loads(raw[s:e])
    except Exception:
        return EmailSummary(uid=uid, summary=raw, actions=[])
    summary_text = str(obj.get("summary", "")).strip() or _local().summary
    actions: list[EmailAction] = []
    for a in (obj.get("actions") or [])[:3]:
        if not isinstance(a, dict):
            continue
        kind = str(a.get("kind", "task")).lower().strip()
        if kind not in {"open_url", "reply", "reminder", "task"}:
            kind = "task"
        actions.append(EmailAction(
            label=str(a.get("label", "Do this"))[:40].strip(),
            kind=kind,
            payload=str(a.get("payload", ""))[:500].strip(),
            description=str(a.get("description", ""))[:120].strip(),
        ))
    return EmailSummary(uid=uid, summary=summary_text, actions=actions)


async def _fresh_google_access(acc: EmailAccount, session: SessionDep) -> str:
    """Return a non-expired Google access token, refreshing if needed."""
    access = decrypt_secret(acc.access_token_enc) if acc.access_token_enc else ""
    if acc.token_expiry is None or acc.token_expiry <= dt.datetime.now(dt.timezone.utc):
        if not acc.refresh_token_enc:
            raise HTTPException(status_code=401, detail="Google session expired. Reconnect the account.")
        cid, csec = await app_cfg.google_creds(session)
        tokens = await google_oauth.refresh_access(
            decrypt_secret(acc.refresh_token_enc), client_id=cid, client_secret=csec,
        )
        access = tokens["access_token"]
        acc.access_token_enc = encrypt_secret(access)
        acc.token_expiry = dt.datetime.now(dt.timezone.utc) + dt.timedelta(
            seconds=int(tokens.get("expires_in", 3600)) - 60
        )
        await session.commit()
    return access


async def _send_for_account(
    acc: EmailAccount, session: SessionDep,
    *, to: list[str], subject: str, body: str,
    thread_id: str | None = None, in_reply_to: str | None = None, references: str | None = None,
) -> str:
    """Dispatch send via the account's provider. Returns provider message id."""
    if acc.provider == "google" and acc.access_token_enc:
        access = await _fresh_google_access(acc, session)
        return await google_oauth.send_email(
            access, to=to, subject=subject, body=body,
            from_addr=acc.email, thread_id=thread_id,
            in_reply_to=in_reply_to, references=references,
        )
    # IMAP / SMTP path
    if not (acc.smtp_host and acc.password_enc):
        raise HTTPException(status_code=400, detail="This account isn't configured to send (no SMTP host/password).")
    await imap_send(
        acc.smtp_host, acc.smtp_port, acc.email, decrypt_secret(acc.password_enc),
        to=to, subject=subject, body=body,
        in_reply_to=in_reply_to, references=references,
    )
    return ""


@router.post("/compose", response_model=SendResponse)
async def compose(data: ComposeRequest, user: CurrentUser, session: SessionDep) -> SendResponse:
    """Send a brand-new email from the user's primary account."""
    acc = await _first_account(user.id, session)
    if acc is None:
        raise HTTPException(status_code=404, detail="No email account connected")
    try:
        msg_id = await _send_for_account(acc, session, to=[str(t) for t in data.to], subject=data.subject, body=data.body)
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=502, detail=f"Gmail send rejected: {exc.response.text[:200]}") from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Send failed: {exc}") from exc
    return SendResponse(ok=True, message_id=msg_id)


@router.post("/messages/{uid}/reply", response_model=SendResponse)
async def reply(uid: str, data: ReplyRequest, user: CurrentUser, session: SessionDep) -> SendResponse:
    """Send a reply on the original thread. Auto-pulls Subject, From, and the
    Message-ID / References headers from the source message so the reply
    threads correctly in the recipient's mail client."""
    msg = await _fetch_one_any(user.id, session, uid)
    if msg is None:
        raise HTTPException(status_code=404, detail="Original message not found")

    # Resolve the threading + recipient based on the account that holds it.
    to_addr = _extract_address(msg.get("sender", ""))
    subject = msg.get("subject", "(no subject)")
    if not subject.lower().startswith("re:"):
        subject = f"Re: {subject}"

    in_reply_to = ""
    references = ""
    thread_id: str | None = None
    # If the account is Google, grab the proper Message-ID + threadId
    target_acc: EmailAccount | None = None
    for acc in await _user_accounts(user.id, session):
        if acc.provider == "google" and acc.access_token_enc:
            try:
                access = await _fresh_google_access(acc, session)
                meta = await google_oauth.get_message_headers(access, uid)
                if meta:
                    hdrs = meta.get("headers", {})
                    in_reply_to = hdrs.get("Message-ID", "")
                    references = hdrs.get("References", in_reply_to)
                    thread_id = meta.get("thread_id")
                    target_acc = acc
                    break
            except Exception:
                continue
    if target_acc is None:
        target_acc = await _first_account(user.id, session)
    if target_acc is None:
        raise HTTPException(status_code=404, detail="No sendable account")

    try:
        sent_id = await _send_for_account(
            target_acc, session,
            to=[to_addr], subject=subject, body=data.body,
            thread_id=thread_id, in_reply_to=in_reply_to or None, references=references or None,
        )
    except httpx.HTTPStatusError as exc:
        raise HTTPException(status_code=502, detail=f"Send rejected: {exc.response.text[:200]}") from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"Send failed: {exc}") from exc
    return SendResponse(ok=True, message_id=sent_id)


@router.post("/messages/{uid}/draft-reply", response_model=DraftReplyResponse)
async def draft_reply(uid: str, user: CurrentUser, session: SessionDep) -> DraftReplyResponse:
    """One AI call: produce a polite, contextual reply body. User reviews before send."""
    msg = await _fetch_one_any(user.id, session, uid)
    if msg is None:
        raise HTTPException(status_code=404, detail="Message not found")
    subject = msg.get("subject", "")
    if not subject.lower().startswith("re:"):
        subject = f"Re: {subject}"

    provider = user.llm_provider
    enc = {"claude": user.llm_api_key_enc, "gemini": user.gemini_key_enc, "groq": user.groq_key_enc}.get(provider or "")
    sender = _short_name(msg.get("sender", "there"))
    body_in = (msg.get("body") or "")[:3500]

    def _local() -> str:
        return (
            f"Hi {sender},\n\nThanks for the message — I've seen it and will get back to you shortly.\n\n"
            f"Best,\n{user.display_name or user.email.split('@')[0]}"
        )

    if not enc:
        return DraftReplyResponse(draft=_local(), subject=subject)

    api_key = decrypt_secret(enc)
    name = user.display_name or user.email.split("@")[0]
    prompt = (
        f"Email from {msg.get('sender', '')}\n"
        f"Subject: {msg.get('subject', '')}\n\n{body_in}\n\n"
        f"Write a concise, warm reply on behalf of {name}. 2–4 short paragraphs max. "
        "Acknowledge the key point, respond directly to what was asked, end with a friendly close. "
        "Plain text only — no signature block, no subject line, no 'Hi' if the email is purely transactional. "
        f"Use the recipient's first name ({sender}) if a greeting fits."
    )
    try:
        chunks: list[str] = []
        async for c in stream_reply(prompt, [], provider=provider, api_key=api_key, memory=[]):
            chunks.append(c)
        text = "".join(chunks).strip() or _local()
    except Exception:
        text = _local()
    return DraftReplyResponse(draft=text, subject=subject)


def _extract_address(s: str) -> str:
    """'Sarah <sarah@x.com>' → 'sarah@x.com'."""
    import re as _re
    m = _re.search(r"<([^>]+)>", s)
    return m.group(1) if m else s.strip()


def _short_name(s: str) -> str:
    """'Sarah Chen <…>' → 'Sarah'."""
    import re as _re
    m = _re.match(r"\s*\"?([^\"<]+?)\"?\s*<", s)
    name = (m.group(1) if m else s).strip().split()[0] if s else "there"
    return name or "there"


async def _mark_read_for_account(acc: EmailAccount, session: SessionDep, uid: str) -> bool:
    """Mark a message as read on the underlying provider."""
    if acc.provider == "google" and acc.access_token_enc:
        access = decrypt_secret(acc.access_token_enc)
        # refresh token if expired
        if acc.token_expiry is None or acc.token_expiry <= dt.datetime.now(dt.timezone.utc):
            if not acc.refresh_token_enc:
                return False
            tokens = await google_oauth.refresh_access(decrypt_secret(acc.refresh_token_enc))
            access = tokens["access_token"]
            acc.access_token_enc = encrypt_secret(access)
            acc.token_expiry = dt.datetime.now(dt.timezone.utc) + dt.timedelta(
                seconds=int(tokens.get("expires_in", 3600)) - 60
            )
            await session.commit()
        return await google_oauth.mark_read(access, uid)
    # IMAP
    return await imap_mark_read(
        acc.imap_host or "", acc.imap_port, acc.email,
        decrypt_secret(acc.password_enc or ""), uid,
    )


@router.post("/messages/{uid}/mark-read")
async def mark_message_read(uid: str, user: CurrentUser, session: SessionDep) -> dict:
    """Flag the email as Seen / remove UNREAD label on the provider."""
    for acc in await _user_accounts(user.id, session):
        try:
            if await _mark_read_for_account(acc, session, uid):
                return {"ok": True}
        except Exception:
            continue
    return {"ok": False, "detail": "Could not mark as read. (For Gmail OAuth, re-connect the account to grant modify permission.)"}


# ---------- Google OAuth ----------
class GoogleOAuthSetupRequest(BaseModel):
    client_id: str = Field(min_length=10, max_length=200)
    client_secret: str = Field(min_length=10, max_length=200)


@router.post("/oauth/google/setup")
async def google_oauth_setup(data: GoogleOAuthSetupRequest, user: CurrentUser, session: SessionDep) -> dict:
    """Persist Google OAuth client credentials in the DB — no env vars, no restart."""
    await app_cfg.set_value(session, app_cfg.GG_CID, data.client_id.strip())
    await app_cfg.set_value(session, app_cfg.GG_CSEC, data.client_secret.strip())
    return {"ok": True}


@router.get("/oauth/google/start")
async def oauth_start(user: CurrentUser, session: SessionDep) -> dict:
    cid, _ = await app_cfg.google_creds(session)
    if not cid:
        raise HTTPException(
            status_code=503,
            detail="Google OAuth isn't set up yet. Save credentials first in Settings.",
        )
    state = google_oauth.make_state(str(user.id))
    return {"auth_url": google_oauth.build_auth_url(state, client_id=cid), "configured": True}


@router.get("/oauth/google/configured")
async def oauth_configured(session: SessionDep) -> dict:
    ok = await app_cfg.google_configured(session)
    return {"configured": ok, "redirect_uri": settings.google_redirect_uri}


@router.get("/oauth/google/callback")
async def oauth_callback(code: str | None = None, state: str | None = None,
                         error: str | None = None) -> RedirectResponse:
    """Google redirects here after the user grants access."""
    target = settings.google_post_oauth_redirect
    if error or not code or not state:
        return RedirectResponse(url=f"{target}&error={error or 'cancelled'}")
    user_id = google_oauth.verify_state(state)
    if user_id is None:
        return RedirectResponse(url=f"{target}&error=bad_state")
    # look up live creds
    async with SessionLocal() as _s:
        cid, csec = await app_cfg.google_creds(_s)
    try:
        tokens = await google_oauth.exchange_code(code, client_id=cid, client_secret=csec)
        access = tokens["access_token"]
        refresh = tokens.get("refresh_token")
        expiry = dt.datetime.now(dt.timezone.utc) + dt.timedelta(
            seconds=int(tokens.get("expires_in", 3600)) - 60
        )
        email_addr = await google_oauth.get_email_address(access)
    except Exception as exc:
        return RedirectResponse(url=f"{target}&error={str(exc)[:60]}")

    # Persist (use a fresh session — we're outside the normal dep flow here).
    import uuid as _uuid
    async with SessionLocal() as session:
        existing = await session.scalar(
            select(EmailAccount).where(
                EmailAccount.user_id == _uuid.UUID(user_id),
                EmailAccount.email == email_addr,
            )
        )
        if existing:
            existing.provider = "google"
            existing.access_token_enc = encrypt_secret(access)
            if refresh:
                existing.refresh_token_enc = encrypt_secret(refresh)
            existing.token_expiry = expiry
        else:
            session.add(EmailAccount(
                user_id=_uuid.UUID(user_id),
                email=email_addr,
                provider="google",
                access_token_enc=encrypt_secret(access),
                refresh_token_enc=encrypt_secret(refresh) if refresh else None,
                token_expiry=expiry,
            ))
        await session.commit()
        await _ensure_email_skill(_uuid.UUID(user_id), session)

    return RedirectResponse(url=target)
