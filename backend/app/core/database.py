"""Async SQLAlchemy engine, session factory, and Base model."""
from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncAttrs,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import settings


class Base(AsyncAttrs, DeclarativeBase):
    """Declarative base for all ORM models."""


engine = create_async_engine(settings.database_url, echo=False, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency that yields a database session."""
    async with SessionLocal() as session:
        yield session


async def init_models() -> None:
    """Create tables from the ORM metadata.

    Fine for early development. Once the schema stabilises, switch to Alembic
    migrations (this avoids destructive surprises and supports schema history).
    """
    # Import models so they register on Base.metadata before create_all.
    from app.models import (  # noqa: F401
        app_config,
        custom_skill,
        dev_job,
        email_account,
        email_otp,
        github_account,
        installed_skill,
        memory,
        strava_account,
        task,
        user,
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Lightweight additive migrations for columns added to existing tables
        # (create_all won't alter an existing table). Idempotent.
        from sqlalchemy import text
        for stmt in (
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS telegram_token_enc TEXT",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS telegram_chat_id VARCHAR(32)",
        ):
            await conn.execute(text(stmt))
