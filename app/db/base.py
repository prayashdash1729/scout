"""
Async SQLAlchemy engine + session factory.

We use asyncpg so DB calls never block the bot's event loop. `init_models()`
creates tables on startup (no Alembic — the schema is small and additive).
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.config import settings


class Base(DeclarativeBase):
    pass


engine = create_async_engine(
    settings.database_url,
    pool_pre_ping=True,   # survive Postgres connection drops across idle periods
    echo=False,
)

Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def init_models() -> None:
    """Create tables if they don't exist. Called once on bot startup."""
    # Import models so they're registered on Base.metadata before create_all.
    from app.db import models  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
