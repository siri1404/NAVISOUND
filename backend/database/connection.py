"""Async PostgreSQL + PostGIS connection pool for NaviSound.

Uses asyncpg via SQLAlchemy 2.0 async engine. Falls back gracefully
if the database is unreachable so the app can still run without persistence.
"""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

logger = logging.getLogger("navisound.db")

_engine: Optional[AsyncEngine] = None
_session_factory: Optional[async_sessionmaker[AsyncSession]] = None


def _get_async_url() -> str:
    """Convert the sync POSTGRES_URL from .env to an asyncpg URL."""
    url = os.getenv(
        "POSTGRES_URL",
        "postgresql://postgres:localdev@localhost:5432/navisound",
    )
    # asyncpg requires the postgresql+asyncpg:// scheme
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)
    return url


async def init_db() -> None:
    """Create the async engine and run CREATE TABLE IF NOT EXISTS."""
    global _engine, _session_factory

    url = _get_async_url()
    _engine = create_async_engine(
        url,
        echo=False,
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,
    )
    _session_factory = async_sessionmaker(
        _engine, class_=AsyncSession, expire_on_commit=False
    )

    # Import the ORM Base and create tables
    from database.async_models import Base

    try:
        async with _engine.begin() as conn:
            # Enable PostGIS extension
            await conn.execute(
                __import__("sqlalchemy").text(
                    "CREATE EXTENSION IF NOT EXISTS postgis"
                )
            )
            await conn.run_sync(Base.metadata.create_all)
        logger.info("Database initialised (PostGIS enabled)")
    except Exception as exc:
        logger.warning("Could not initialise database: %s", exc)


async def close_db() -> None:
    """Dispose of the connection pool."""
    global _engine
    if _engine:
        await _engine.dispose()
        _engine = None
        logger.info("Database connection pool closed")


@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async session. Commits on success, rolls back on error."""
    if _session_factory is None:
        raise RuntimeError("Database not initialised — call init_db() first")
    async with _session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
