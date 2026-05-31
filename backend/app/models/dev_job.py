"""Unattended dev job — Olwen runs Claude Code on a goal while you're away,
then commits to a branch + opens a PR and pings you."""
import datetime as dt
import uuid

from sqlalchemy import Boolean, DateTime, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class DevJob(Base):
    __tablename__ = "dev_jobs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(index=True, nullable=False)
    project_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    project_name: Mapped[str] = mapped_column(String(255), default="")
    goal: Mapped[str] = mapped_column(Text, nullable=False)
    # queued | running | done | needs_you | failed
    status: Mapped[str] = mapped_column(String(16), default="queued", nullable=False)
    branch: Mapped[str | None] = mapped_column(String(255), nullable=True)
    pr_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    note: Mapped[str] = mapped_column(Text, default="", nullable=False)
    output: Mapped[str] = mapped_column(Text, default="", nullable=False)  # tail of Claude Code's output
    notify: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Claude Code session id (so a "needs_you" job can be resumed with your reply)
    session_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    question: Mapped[str] = mapped_column(Text, default="", nullable=False)  # what Olwen is asking you
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
