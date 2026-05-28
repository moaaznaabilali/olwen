"""Deployment-wide configuration stored in the DB.

Used for things like GitHub OAuth credentials so admins don't have to touch
env files / restart the server to enable a feature.
"""
from sqlalchemy import String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AppConfig(Base):
    __tablename__ = "app_config"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)  # encrypted with Fernet
