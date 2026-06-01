"""Task lists and tasks — Olwen's native task management."""
import datetime as dt
import uuid

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class TaskList(Base):
    __tablename__ = "task_lists"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # free-canvas position (pixels). NULL = not placed yet → frontend lays out a default.
    pos_x: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pos_y: Mapped[int | None] = mapped_column(Integer, nullable=True)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)  # resizable list width (px)
    collapsed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)  # minimized to header
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    list_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("task_lists.id", ondelete="CASCADE"), index=True, nullable=False
    )
    text: Mapped[str] = mapped_column(String(400), nullable=False)
    priority: Mapped[str] = mapped_column(String(8), default="med", nullable=False)  # high|med|low
    done: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    due_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    tags: Mapped[list | None] = mapped_column(JSONB, nullable=True)  # list[str]
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
