"""User account model."""
import datetime as dt
import uuid

from sqlalchemy import Boolean, DateTime, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(
        String(320), unique=True, index=True, nullable=False
    )
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Bring-your-own-AI: per-user keys (encrypted at rest) + chosen provider.
    llm_api_key_enc: Mapped[str | None] = mapped_column(Text, nullable=True)  # Anthropic/Claude
    gemini_key_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    groq_key_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    llm_provider: Mapped[str | None] = mapped_column(String(16), nullable=True)  # 'claude'|'gemini'|'groq'

    # Voice preferences
    voice_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    voice_lang: Mapped[str] = mapped_column(String(8), default="en-US", nullable=False)
    # When ON, opening/summarising an email also marks it as read in the mailbox.
    auto_mark_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Which dashboard widgets are visible (list of widget keys).
    # None = show defaults; explicit empty list = show none.
    dashboard_widgets: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # Which news topics the user follows (e.g. ['ai', 'tech', 'finance']).
    news_topics: Mapped[list | None] = mapped_column(JSON, nullable=True)

    # Morning brief: when Olwen wakes you up with the day ahead.
    brief_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    brief_time: Mapped[str] = mapped_column(String(5), default="08:00", nullable=False)  # 24h "HH:MM"
    brief_last_shown: Mapped[dt.date | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
