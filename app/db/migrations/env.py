"""
Alembic environment — configured for SQLAlchemy 2.0 async (asyncpg).

Key points
──────────
• ``run_migrations_online`` uses ``AsyncEngine`` via
  ``AsyncEngine.sync_engine`` so Alembic's synchronous internals work
  transparently with an async driver.
• ``target_metadata`` imports all ORM models so auto-generate detects changes.
• Connection string is pulled from ``POSTGRES_URL`` env var (via Settings).
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

# ── Import ALL models so their metadata is registered ─────────────────────
from app.memory.operational import Base  # noqa: F401 — registers all models
from app.core.config import get_settings

# Alembic Config object (gives access to alembic.ini values)
config = context.config

# Set up Python logging from alembic.ini if present
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

settings = get_settings()


def get_url() -> str:
    """Return the async DSN from Settings (overrides alembic.ini sqlalchemy.url)."""
    return settings.POSTGRES_URL


# ---------------------------------------------------------------------------
# Offline migrations (no live DB connection — generates SQL scripts)
# ---------------------------------------------------------------------------


def run_migrations_offline() -> None:
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


# ---------------------------------------------------------------------------
# Online migrations (async engine → sync_engine for Alembic)
# ---------------------------------------------------------------------------


def do_run_migrations(connection):  # type: ignore[no-untyped-def]
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    engine: AsyncEngine = create_async_engine(
        get_url(),
        poolclass=pool.NullPool,  # Alembic creates its own connections
    )
    async with engine.connect() as conn:
        await conn.run_sync(do_run_migrations)
    await engine.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
