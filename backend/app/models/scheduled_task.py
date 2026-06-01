"""User-configurable scheduled automations ("workflows").

One row = one recurring job the user defined from the UI. The scheduler loop
reads these rows directly (single source of truth) — no separate jobstore.
`next_run` (UTC) is the durable cursor: a restart loses nothing, the next tick
picks up whatever is due.
"""
import datetime as dt
import uuid

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class ScheduledTask(Base):
    __tablename__ = "scheduled_tasks"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)

    # discriminated action: {type: 'morning_brief'|'read_news'|'send_email'|'agent_goal'|'reminder', ...}
    action: Mapped[dict] = mapped_column(JSONB, nullable=False)

    schedule_kind: Mapped[str] = mapped_column(String(8), default="daily", nullable=False)  # 'daily'|'cron'
    cron_expr: Mapped[str] = mapped_column(String(120), nullable=False)  # always compiled (daily HH:MM -> cron)
    daily_time: Mapped[str | None] = mapped_column(String(5), nullable=True)  # "07:00" when schedule_kind='daily'
    tz: Mapped[str] = mapped_column(String(64), default="UTC", nullable=False)  # IANA, e.g. "Asia/Riyadh"

    notify_channel: Mapped[str] = mapped_column(String(10), default="inapp", nullable=False)  # email|telegram|both|inapp
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    next_run: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), index=True, nullable=True)
    last_run: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_status: Mapped[str | None] = mapped_column(String(10), nullable=True)  # ok|error|skipped|running
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_output: Mapped[str | None] = mapped_column(Text, nullable=True)  # delivered text (for inapp/history)
    last_duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
