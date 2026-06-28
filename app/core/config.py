"""
Pydantic v2 Settings — single source of truth for all connection URLs
and runtime configuration.  Load from environment variables or a .env file.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── App ────────────────────────────────────────────────────────────────
    APP_ENV: Literal["development", "staging", "production"] = "development"
    APP_NAME: str = "xlventures-memory"
    LOG_LEVEL: str = "INFO"

    # ── PostgreSQL ─────────────────────────────────────────────────────────
    POSTGRES_URL: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/xlventures",
        description="Async SQLAlchemy PostgreSQL DSN",
    )
    POSTGRES_POOL_SIZE: int = 10
    POSTGRES_MAX_OVERFLOW: int = 20
    POSTGRES_POOL_TIMEOUT: int = 30

    # ── Redis ──────────────────────────────────────────────────────────────
    REDIS_URL: str = Field(
        default="redis://localhost:6379/0",
        description="Redis connection URL",
    )
    REDIS_EPISODIC_DB: int = 0
    REDIS_CELERY_DB: int = 1
    REDIS_MAX_CONNECTIONS: int = 50
    EPISODIC_TTL_SECONDS: int = 2_592_000  # 30 days

    # ── Neo4j ──────────────────────────────────────────────────────────────
    NEO4J_URI: str = Field(
        default="bolt://localhost:7687",
        description="Neo4j Bolt URI",
    )
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = "neo4j"
    NEO4J_DATABASE: str = "neo4j"
    NEO4J_MAX_CONNECTION_POOL_SIZE: int = 50

    # ── Qdrant ─────────────────────────────────────────────────────────────
    QDRANT_HOST: str = "localhost"
    QDRANT_PORT: int = 6333
    QDRANT_GRPC_PORT: int = 6334
    QDRANT_API_KEY: str | None = None
    QDRANT_COLLECTION_NAME: str = "companies"
    QDRANT_VECTOR_SIZE: int = 1536  # text-embedding-3-small

    # ── OpenAI ─────────────────────────────────────────────────────────────
    OPENAI_API_KEY: str = Field(default="", description="OpenAI API key for embeddings")
    OPENAI_EMBEDDING_MODEL: str = "text-embedding-3-small"

    # ── Celery ─────────────────────────────────────────────────────────────
    CELERY_BROKER_URL: str = Field(
        default="redis://localhost:6379/1",
        description="Celery broker URL (Redis DB 1)",
    )
    CELERY_RESULT_BACKEND: str = Field(
        default="redis://localhost:6379/1",
        description="Celery result backend URL (Redis DB 1)",
    )

    # ── JWT ────────────────────────────────────────────────────────────────────
    JWT_SECRET: str = Field(default="change-me-in-production", description="JWT signing secret")
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 1440  # 24 hours

    @field_validator("POSTGRES_URL")
    @classmethod
    def ensure_asyncpg_driver(cls, v: str) -> str:
        if v.startswith("postgresql://"):
            return v.replace("postgresql://", "postgresql+asyncpg://", 1)
        if v.startswith("postgres://"):
            return v.replace("postgres://", "postgresql+asyncpg://", 1)
        return v


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached settings singleton — call this everywhere."""
    return Settings()
