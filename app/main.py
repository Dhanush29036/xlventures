"""
FastAPI application entry point — API Gateway Layer.

Run with:
    uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator, Any

import structlog
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.agents.planner import PlannerAgent
from app.api.auth import router as auth_router
from app.api.routes.hitl import router as hitl_router
from app.api.routes.icp import router as icp_router
from app.api.routes.results import router as results_router
from app.api.routes.runs import router as runs_router
from app.api.routes.stream import router as stream_router
from app.core.config import get_settings
from app.core.logging_config import configure_logging
from app.db.session import build_async_engine, build_session_factory
from app.memory.episodic import EpisodicMemoryStore
from app.memory.graph import GraphStore
from app.memory.manager import HealthChecker, MemoryManager
from app.memory.semantic import SemanticICPStore

configure_logging()
logger = structlog.get_logger(__name__)
settings = get_settings()


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    log = logger.bind(phase="startup")
    log.info("initialising_postgres")
    engine = build_async_engine(settings)
    session_factory = build_session_factory(engine)
    app.state.session_factory = session_factory

    log.info("initialising_redis")
    episodic_store = EpisodicMemoryStore(
        redis_url=settings.REDIS_URL,
        default_ttl=settings.EPISODIC_TTL_SECONDS,
        max_connections=settings.REDIS_MAX_CONNECTIONS,
    )
    await episodic_store.connect()

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

    memory_manager = MemoryManager(
        pg=session_factory,
        redis=episodic_store,
        neo4j=graph_store,
        qdrant=semantic_store,
    )
    planner_agent = PlannerAgent(memory_manager)

    app.state.memory_manager = memory_manager
    app.state.planner_agent = planner_agent
    app.state.engine = engine
    log.info("startup_complete")

    yield

    log.bind(phase="shutdown").info("shutdown_initiated")
    import asyncio
    await asyncio.gather(graph_store.close(), episodic_store.close(), return_exceptions=True)
    await engine.dispose()
    log.bind(phase="shutdown").info("shutdown_complete")


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------


app = FastAPI(
    title="XL Ventures — Agentic Prospect Intelligence Platform",
    description=(
        "B2B Prospect Intelligence Platform powered by LangGraph agents, "
        "Neo4j knowledge graph, Qdrant semantic search, and Redis episodic memory."
    ),
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/api/v1/docs",
    redoc_url="/api/v1/redoc",
    openapi_url="/api/v1/openapi.json",
)

# ── CORS ──────────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Global error handler ──────────────────────────────────────────────────────


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("unhandled_exception", path=request.url.path, error=str(exc))
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error", "error": str(exc)},
    )


# ── Routers ───────────────────────────────────────────────────────────────────

API_PREFIX = "/api/v1"

app.include_router(auth_router, prefix=API_PREFIX)
app.include_router(icp_router, prefix=API_PREFIX)
app.include_router(runs_router, prefix=API_PREFIX)
app.include_router(hitl_router, prefix=API_PREFIX)
app.include_router(results_router, prefix=API_PREFIX)
app.include_router(stream_router, prefix=API_PREFIX)


# ── Health ────────────────────────────────────────────────────────────────────


@app.get("/health", tags=["ops"])
async def health(request: Request) -> JSONResponse:
    """Ping all four backend stores and return aggregate health status."""
    mm: MemoryManager = request.app.state.memory_manager
    checker = HealthChecker(mm)
    result = await checker.check()
    status_code = 200 if result["status"] == "healthy" else 503
    return JSONResponse(content=result, status_code=status_code)


@app.get("/", tags=["ops"])
async def root() -> dict[str, str]:
    return {
        "service": "XL Ventures Prospect Intelligence API",
        "version": "1.0.0",
        "docs": "/api/v1/docs",
    }


# ── Pipeline trigger (convenience re-export) ──────────────────────────────────


class PipelineRunRequest(dict):
    pass


def get_planner_agent(request: Request) -> PlannerAgent:
    return request.app.state.planner_agent
