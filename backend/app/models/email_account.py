"""Per-user connected email account (Gmail / Outlook / Yahoo / iCloud / custom IMAP)."""
import datetime as dt
import uuid

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class EmailAccount(Base):
    __tablename__ = "email_accounts"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    provider: Mapped[str] = mapped_column(String(16), default="imap", nullable=False)  # imap | google
    # IMAP/SMTP path (nullable: not used for OAuth providers)
    imap_host: Mapped[str | None] = mapped_column(String(160), nullable=True)
    imap_port: Mapped[int] = mapped_column(Integer, default=993, nullable=False)
    smtp_host: Mapped[str | None] = mapped_column(String(160), nullable=True)
    smtp_port: Mapped[int] = mapped_column(Integer, default=587, nullable=False)
    password_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    # OAuth path (Google)
    access_token_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    refresh_token_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    token_expiry: Mapped["dt.datetime | None"] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
