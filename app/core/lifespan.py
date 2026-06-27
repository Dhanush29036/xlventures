"""
FastAPI lifespan context manager — initialises every backend on startup,
injects the MemoryManager into app.state, and gracefully shuts everything
down on exit.
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncIterator

import structlog
from fastapi import FastAPI, Request

from app.core.config import get_settings
from app.db.session import build_async_engine, build_session_factory
from app.memory.episodic import EpisodicMemoryStore
from app.memory.graph import GraphStore
from app.memory.manager import MemoryManager
from app.memory.semantic import SemanticICPStore

logger = structlog.get_logger(__name__)
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:  # noqa: C901
    """
    Application lifespan handler.

    Startup order
    ─────────────
    1. PostgreSQL (SQLAlchemy async engine + session factory)
    2. Redis      (EpisodicMemoryStore connection pool)
    3. Neo4j      (GraphStore driver + index creation)
    4. Qdrant     (SemanticICPStore client + collection ensure)
    5. MemoryManager aggregated from all four stores
    6. Inject MemoryManager into app.state

    Shutdown order (reverse)
    ─────────────────────────
    Neo4j driver, Redis connection pool, SQLAlchemy engine dispose.
    """
    log = logger.bind(phase="startup")

    # ── 1. PostgreSQL ──────────────────────────────────────────────────────
    log.info("initialising_postgres")
    engine = build_async_engine(settings)
    session_factory = build_session_factory(engine)
    log.info("postgres_ready")

    # ── 2. Redis ───────────────────────────────────────────────────────────
    log.info("initialising_redis")
    episodic_store = EpisodicMemoryStore(
        redis_url=settings.REDIS_URL,
        default_ttl=settings.EPISODIC_TTL_SECONDS,
        max_connections=settings.REDIS_MAX_CONNECTIONS,
    )
    await episodic_store.connect()
    log.info("redis_ready")

    # ── 3. Neo4j ───────────────────────────────────────────────────────────
    log.info("initialising_neo4j")
    graph_store = GraphStore(
        uri=settings.NEO4J_URI,
        user=settings.NEO4J_USER,
        password=settings.NEO4J_PASSWORD,
        database=settings.NEO4J_DATABASE,
        max_connection_pool_size=settings.NEO4J_MAX_CONNECTION_POOL_SIZE,
    )
    await graph_store.connect()
    await graph_store.create_indexes()
    log.info("neo4j_ready")

    # ── 4. Qdrant ──────────────────────────────────────────────────────────
    log.info("initialising_qdrant")
    semantic_store = SemanticICPStore(
        host=settings.QDRANT_HOST,
        port=settings.QDRANT_PORT,
        grpc_port=settings.QDRANT_GRPC_PORT,
        api_key=settings.QDRANT_API_KEY,
        collection_name=settings.QDRANT_COLLECTION_NAME,
        vector_size=settings.QDRANT_VECTOR_SIZE,
        openai_api_key=settings.OPENAI_API_KEY,
        embedding_model=settings.OPENAI_EMBEDDING_MODEL,
    )
    await semantic_store.connect()
    log.info("qdrant_ready")

    # ── 5. MemoryManager ───────────────────────────────────────────────────
    memory_manager = MemoryManager(
        pg=session_factory,
        redis=episodic_store,
        neo4j=graph_store,
        qdrant=semantic_store,
    )

    # ── 6. Inject into app.state ───────────────────────────────────────────
    app.state.memory_manager = memory_manager
    app.state.engine = engine
    log.info("memory_manager_ready", stores=["postgres", "redis", "neo4j", "qdrant"])

    yield  # ─── application runs ───────────────────────────────────────────

    # ── Shutdown ───────────────────────────────────────────────────────────
    shutdown_log = logger.bind(phase="shutdown")
    shutdown_log.info("shutdown_initiated")

    # Run independent cleanup concurrently
    await asyncio.gather(
        graph_store.close(),
        episodic_store.close(),
        return_exceptions=True,
    )
    await engine.dispose()
    shutdown_log.info("shutdown_complete")


# ---------------------------------------------------------------------------
# FastAPI Dependency
# ---------------------------------------------------------------------------


def get_memory_manager(request: Request) -> MemoryManager:
    """
    FastAPI dependency — inject via ``Depends(get_memory_manager)``.

    Example::

        @router.get("/companies/{domain}/context")
        async def company_context(
            domain: str,
            mm: MemoryManager = Depends(get_memory_manager),
        ):
            return await mm.get_company_context(tenant_id="t1", domain=domain)
    """
    return request.app.state.memory_manager
