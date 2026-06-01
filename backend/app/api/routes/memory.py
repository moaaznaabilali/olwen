"""What Olwen remembers about the user — CRUD + search.

Active (current) memories are returned by default; superseded ones are kept
forever and surfaced via ?include_archived=true or the /search endpoint.
"""
import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import CurrentUser, SessionDep
from app.models.memory import Memory
from app.schemas.memory import MemoryCreate, MemoryRead
from app.services.memory import add_memory, gemini_key_for, recall

router = APIRouter()


@router.get("", response_model=list[MemoryRead])
async def list_memories(
    user: CurrentUser, session: SessionDep, include_archived: bool = False
) -> list[Memory]:
    stmt = select(Memory).where(Memory.user_id == user.id)
    if not include_archived:
        stmt = stmt.where(Memory.superseded_by.is_(None))
    stmt = stmt.order_by(Memory.importance.desc(), Memory.created_at.desc())
    rows = await session.scalars(stmt)
    return list(rows)


@router.get("/search", response_model=list[MemoryRead])
async def search_memories(
    q: str, user: CurrentUser, session: SessionDep, include_archived: bool = True
) -> list[Memory]:
    """Semantic search across all memory (including archived facts)."""
    return await recall(session, user.id, q, gemini_key_for(user), include_archived, limit=12)


@router.post("", response_model=MemoryRead, status_code=status.HTTP_201_CREATED)
async def create_memory(data: MemoryCreate, user: CurrentUser, session: SessionDep) -> Memory:
    m = await add_memory(
        session, user.id, data.content,
        mem_type=data.mem_type, subject=data.subject, importance=data.importance,
        source="user_explicit", gemini_key=gemini_key_for(user),
    )
    if m is None:
        raise HTTPException(status_code=400, detail="Empty memory.")
    return m


@router.delete("/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_memory(memory_id: uuid.UUID, user: CurrentUser, session: SessionDep) -> None:
    m = await session.get(Memory, memory_id)
    if m is None or m.user_id != user.id:
        raise HTTPException(status_code=404, detail="Memory not found")
    await session.delete(m)
    await session.commit()
