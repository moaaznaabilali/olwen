"""Things Olwen remembers about the user.

A professional-grade long-term memory: typed (semantic / episodic / procedural),
importance-weighted, supersede-not-delete (so nothing is ever truly forgotten),
and semantically retrievable via a pgvector embedding.
"""
import datetime as dt
import uuid

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

EMBED_DIM = 768  # gemini text-embedding-004


class Memory(Base):
    __tablename__ = "memories"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)

    # semantic (facts/preferences) | episodic (events) | procedural (how the user works)
    mem_type: Mapped[str] = mapped_column(String(16), default="semantic", nullable=False)
    importance: Mapped[int] = mapped_column(Integer, default=5, nullable=False)  # 1..10
    # entity/topic key used for conflict-detection & dedup, e.g. "employer", "diet"
    subject: Mapped[str | None] = mapped_column(String(120), nullable=True)
    # 'user_explicit' (the user told me) | 'extracted' (I inferred it from chat)
    source: Mapped[str] = mapped_column(String(16), default="extracted", nullable=False)

    # supersede-not-delete: when a fact changes, the old row points at the new one.
    # NULL = still active/current. The old row is kept forever (never forget).
    superseded_by: Mapped[uuid.UUID | None] = mapped_column(nullable=True)

    last_accessed: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    access_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # semantic vector + the model that produced it (to detect drift if we re-embed)
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBED_DIM), nullable=True)
    embed_model: Mapped[str | None] = mapped_column(String(40), nullable=True)

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
