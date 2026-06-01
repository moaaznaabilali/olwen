"""Notifications — recent list, mark-read, and a live SSE stream."""
import json
import uuid
from collections.abc import AsyncIterator

from fastapi import APIRouter, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select, update

from app.api.deps import CurrentUser, CurrentUserId, SessionDep
from app.models.notification import Notification
from app.services.notifications import subscribe

router = APIRouter()


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event)}\n\n"


@router.get("")
async def list_notifications(
    user: CurrentUser, session: SessionDep, limit: int = 30
) -> dict:
    rows = list(await session.scalars(
        select(Notification)
        .where(Notification.user_id == user.id)
        .order_by(Notification.created_at.desc())
        .limit(max(1, min(limit, 100)))
    ))
    unread = sum(1 for n in rows if not n.read)
    return {
        "unread": unread,
        "items": [
            {
                "id": str(n.id), "kind": n.kind, "title": n.title, "body": n.body,
                "meta": n.meta or {}, "read": n.read,
                "created_at": n.created_at.isoformat() if n.created_at else None,
            }
            for n in rows
        ],
    }


@router.post("/read-all", status_code=status.HTTP_204_NO_CONTENT)
async def mark_all_read(user: CurrentUser, session: SessionDep) -> None:
    await session.execute(
        update(Notification).where(
            Notification.user_id == user.id, Notification.read.is_(False)
        ).values(read=True)
    )
    await session.commit()


@router.post("/{notif_id}/read", status_code=status.HTTP_204_NO_CONTENT)
async def mark_read(notif_id: uuid.UUID, user: CurrentUser, session: SessionDep) -> None:
    await session.execute(
        update(Notification).where(
            Notification.id == notif_id, Notification.user_id == user.id
        ).values(read=True)
    )
    await session.commit()


@router.get("/stream")
async def stream(user_id: CurrentUserId) -> StreamingResponse:
    """Live notifications over SSE. Authenticated from the JWT only (no DB session
    held for the stream's lifetime — that would pin a transaction open). The
    frontend reads this with fetch-streaming so it can send the auth header."""
    async def event_source() -> AsyncIterator[str]:
        async for event in subscribe(user_id):
            yield _sse(event)

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no", "Connection": "keep-alive"},
    )
