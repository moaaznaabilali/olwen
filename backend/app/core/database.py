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
        notification,
        scheduled_task,
        strava_account,
        task,
        user,
    )

    async with engine.begin() as conn:
        from sqlalchemy import text
        # pgvector type must exist before any table using a Vector column is created.
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)
        # Lightweight additive migrations for columns added to existing tables
        # (create_all won't alter an existing table). Idempotent.
        for stmt in (
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS telegram_token_enc TEXT",
            "ALTER TABLE users ADD COLUMN IF NOT EXISTS telegram_chat_id VARCHAR(32)",
            "ALTER TABLE task_lists ADD COLUMN IF NOT EXISTS position INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE task_lists ADD COLUMN IF NOT EXISTS pos_x INTEGER",
            "ALTER TABLE task_lists ADD COLUMN IF NOT EXISTS pos_y INTEGER",
            "ALTER TABLE task_lists ADD COLUMN IF NOT EXISTS width INTEGER",
            "ALTER TABLE task_lists ADD COLUMN IF NOT EXISTS collapsed BOOLEAN NOT NULL DEFAULT FALSE",
            "ALTER TABLE tasks ADD COLUMN IF NOT EXISTS due_date DATE",
            "ALTER TABLE tasks ADD COLUMN IF NOT EXISTS tags JSONB",
            # Long-term memory: typed, weighted, supersede-not-delete, embeddable.
            "ALTER TABLE memories ALTER COLUMN content TYPE TEXT",
            "ALTER TABLE memories ADD COLUMN IF NOT EXISTS mem_type VARCHAR(16) NOT NULL DEFAULT 'semantic'",
            "ALTER TABLE memories ADD COLUMN IF NOT EXISTS importance INTEGER NOT NULL DEFAULT 5",
            "ALTER TABLE memories ADD COLUMN IF NOT EXISTS subject VARCHAR(120)",
            "ALTER TABLE memories ADD COLUMN IF NOT EXISTS source VARCHAR(16) NOT NULL DEFAULT 'extracted'",
            "ALTER TABLE memories ADD COLUMN IF NOT EXISTS superseded_by UUID",
            "ALTER TABLE memories ADD COLUMN IF NOT EXISTS last_accessed TIMESTAMPTZ",
            "ALTER TABLE memories ADD COLUMN IF NOT EXISTS access_count INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE memories ADD COLUMN IF NOT EXISTS embedding vector(768)",
            "ALTER TABLE memories ADD COLUMN IF NOT EXISTS embed_model VARCHAR(40)",
        ):
            await conn.execute(text(stmt))
