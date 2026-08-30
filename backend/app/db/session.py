"""Database session management.

Two engines by design:

- An async engine for FastAPI request handling, so HTTP concurrency is not
  limited by blocking database calls.
- A sync engine for the worker and Alembic, where the surrounding code is
  synchronous and async buys nothing.

Both point at the same database; only the driver differs.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, Generator
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


def _async_url(url: str) -> str:
    """psycopg3 serves both sync and async; the async engine needs the async flag."""
    return url


@lru_cache
def get_async_engine() -> AsyncEngine:
    # The loop policy must be right before the first connection is made. Setting
    # it here as well as in entrypoints means an embedder that constructs its
    # own loop (uvicorn, pytest-asyncio) still gets a working engine rather than
    # an InterfaceError on first query.
    from app.core.runtime import configure_event_loop

    configure_event_loop()

    settings = get_settings()
    return create_async_engine(
        _async_url(settings.database_url),
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_max_overflow,
        # Recycle before typical idle-connection reapers close sockets under us.
        pool_recycle=1800,
        pool_pre_ping=True,
        echo=False,
    )


@lru_cache
def get_sync_engine():  # type: ignore[no-untyped-def]
    settings = get_settings()
    return create_engine(
        settings.sync_database_url,
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_max_overflow,
        pool_recycle=1800,
        pool_pre_ping=True,
        echo=False,
    )


@lru_cache
def get_session_factory() -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        get_async_engine(),
        class_=AsyncSession,
        expire_on_commit=False,  # keep attributes usable after commit
        autoflush=False,
    )


@lru_cache
def get_sync_session_factory() -> sessionmaker[Session]:
    return sessionmaker(get_sync_engine(), expire_on_commit=False, autoflush=False)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency.

    Commits on success and rolls back on any exception, so a failed request can
    never leave a partially-written verification behind.
    """
    async with get_session_factory()() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def get_sync_db() -> Generator[Session, None, None]:
    """Worker-side session with the same commit/rollback contract."""
    with get_sync_session_factory()() as session:
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
