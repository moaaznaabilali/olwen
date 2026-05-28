"""What Olwen remembers about the user — CRUD."""
import uuid

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select

from app.api.deps import CurrentUser, SessionDep
from app.models.memory import Memory
from app.schemas.memory import MemoryCreate, MemoryRead

router = APIRouter()


@router.get("", response_model=list[MemoryRead])
async def list_memories(user: CurrentUser, session: SessionDep) -> list[Memory]:
    rows = await session.scalars(
        select(Memory).where(Memory.user_id == user.id).order_by(Memory.created_at.desc())
    )
    return list(rows)


@router.post("", response_model=MemoryRead, status_code=status.HTTP_201_CREATED)
async def add_memory(data: MemoryCreate, user: CurrentUser, session: SessionDep) -> Memory:
    m = Memory(user_id=user.id, content=data.content.strip())
    session.add(m)
    await session.commit()
    await session.refresh(m)
    return m


@router.delete("/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_memory(memory_id: uuid.UUID, user: CurrentUser, session: SessionDep) -> None:
    m = await session.get(Memory, memory_id)
    if m is None or m.user_id != user.id:
        raise HTTPException(status_code=404, detail="Memory not found")
    await session.delete(m)
    await session.commit()
