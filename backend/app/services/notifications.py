"""Live notification hub.

`push()` stores a notification and fans it out to any connected dashboards over
an in-memory broker (per-user asyncio queues). The SSE route consumes
`subscribe()`. Single-process uvicorn → the broker is the whole story; on a
multi-worker deploy this would move to Redis pub/sub.

Sources wired today: incoming Telegram messages (telegram_bot poller) and new
inbox email (`email_notify_poller`). The model is channel-agnostic, so WhatsApp
or anything else just calls `push(...)`.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import uuid

from sqlalchemy import select

from app.core.database import SessionLocal
from app.models.notification import Notification

# user_id -> set of live subscriber queues
_subscribers: dict[uuid.UUID, set[asyncio.Queue]] = {}


def _serialize(n: Notification) -> dict:
    return {
        "id": str(n.id),
        "kind": n.kind,
        "title": n.title,
        "body": n.body,
        "meta": n.meta or {},
        "read": n.read,
        "created_at": n.created_at.isoformat() if n.created_at else None,
    }


async def push(user_id: uuid.UUID, kind: str, title: str, body: str | None = None,
               meta: dict | None = None) -> dict:
    """Persist a notification and fan it out to live dashboards. Never raises."""
    try:
        async with SessionLocal() as session:
            n = Notification(user_id=user_id, kind=kind, title=title[:200],
                             body=(body or None), meta=meta or None)
            session.add(n)
            await session.commit()
            await session.refresh(n)
            event = {"type": "notification", **_serialize(n)}
    except Exception:
        # fall back to a transient event so the live toast still fires
        event = {
            "type": "notification", "id": str(uuid.uuid4()), "kind": kind,
            "title": title[:200], "body": body, "meta": meta or {}, "read": False,
            "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        }
    for q in list(_subscribers.get(user_id, ())):
        try:
            q.put_nowait(event)
        except Exception:
            pass
    return event


async def subscribe(user_id: uuid.UUID):
    """Yield live notification events for a user (plus periodic pings so the
    connection and any proxies stay open)."""
    q: asyncio.Queue = asyncio.Queue()
    _subscribers.setdefault(user_id, set()).add(q)
    try:
        # greet so the client knows the stream is live
        yield {"type": "ready"}
        while True:
            try:
                event = await asyncio.wait_for(q.get(), timeout=15)
                yield event
            except asyncio.TimeoutError:
                yield {"type": "ping"}
    finally:
        subs = _subscribers.get(user_id)
        if subs:
            subs.discard(q)
            if not subs:
                _subscribers.pop(user_id, None)


# ───────────────────────── email watcher ───────────────────────────────────
# account_id -> set of message uids we've already seen. First sight of an
# account seeds the set WITHOUT notifying (so we don't blast the whole inbox at
# startup); only genuinely new arrivals after that fire a notification.
_seen_email: dict[uuid.UUID, set[str]] = {}


async def email_notify_poller() -> None:
    from app.models.email_account import EmailAccount

    while True:
        try:
            async with SessionLocal() as session:
                accounts = list(await session.scalars(select(EmailAccount)))
            # Each account gets its own short-lived session + a hard timeout, so
            # one slow/stuck mailbox can never stall the loop (or the whole app).
            for acc in accounts:
                try:
                    async with SessionLocal() as s2:
                        acc2 = await s2.get(EmailAccount, acc.id)
                        if acc2 is not None:
                            await asyncio.wait_for(_check_account(acc2, s2), timeout=25)
                except (asyncio.TimeoutError, Exception):
                    continue
        except asyncio.CancelledError:
            raise
        except Exception:
            pass
        await asyncio.sleep(60)


async def _check_account(acc, session) -> None:
    from app.api.routes.email import _fetch_for_account
    try:
        rows = await _fetch_for_account(acc, session, 10)
    except Exception:
        return
    uids = {str(r.get("uid")) for r in rows if r.get("uid") is not None}
    first_time = acc.id not in _seen_email
    seen = _seen_email.setdefault(acc.id, set())
    if first_time:
        seen.update(uids)  # seed silently
        return
    # newest first from the API; notify for arrivals we haven't seen
    for r in rows:
        uid = str(r.get("uid"))
        if uid in seen:
            continue
        seen.add(uid)
        if not r.get("unread", True):
            continue  # don't ping for mail that's already been read elsewhere
        sender = (r.get("sender") or "Someone").split("<")[0].strip().strip('"') or "New email"
        subject = (r.get("subject") or "(no subject)").strip()
        await push(
            acc.user_id, "email",
            title=f"New email from {sender}",
            body=subject,
            meta={"from": r.get("sender"), "subject": subject, "uid": uid},
        )
    # keep the seen-set from growing unbounded
    if len(seen) > 200:
        _seen_email[acc.id] = set(list(seen)[-100:])
