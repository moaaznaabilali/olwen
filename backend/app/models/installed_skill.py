"""Per-user installed skills (which abilities the user has added)."""
import datetime as dt
import uuid

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class InstalledSkill(Base):
    __tablename__ = "installed_skills"
    __table_args__ = (UniqueConstraint("user_id", "skill_key", name="uq_user_skill"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    skill_key: Mapped[str] = mapped_column(String(40), nullable=False)
    installed_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
