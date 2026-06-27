"""
SQLAlchemy 2.0 async session factory and engine builder.

Usage
-----
engine = build_async_engine(settings)
SessionLocal = build_session_factory(engine)

async with SessionLocal() as session:
    ...
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import Settings


def build_async_engine(settings: Settings) -> AsyncEngine:
    """Create and return an async SQLAlchemy engine from settings."""
    return create_async_engine(
        settings.POSTGRES_URL,
        pool_size=settings.POSTGRES_POOL_SIZE,
        max_overflow=settings.POSTGRES_MAX_OVERFLOW,
        pool_timeout=settings.POSTGRES_POOL_TIMEOUT,
        pool_pre_ping=True,  # drop stale connections automatically
        echo=settings.APP_ENV == "development",
    )


def build_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Return a session factory bound to *engine*."""
    return async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
        autocommit=False,
    )
