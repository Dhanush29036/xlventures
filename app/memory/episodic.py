"""
Redis EpisodicMemoryStore — short-term + deduplication memory.

Key schema
──────────
  episodic:{tenant_id}:{company_domain}:runs   → Redis List  (JSON-encoded dicts)
  processed:{tenant_id}                        → Redis Set   (member: company_domain)

The ``processed`` membership check is O(1) and intentionally done on a *per-tenant*
set so a single SISMEMBER call covers all domains without needing a per-domain key.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import structlog
from redis.asyncio import ConnectionPool, Redis
from redis.asyncio.retry import Retry
from redis.backoff import ExponentialBackoff
from redis.exceptions import RedisError

logger = structlog.get_logger(__name__)


class EpisodicMemoryStore:
    """
    Async Redis store for episodic (per-run) memory and duplicate prevention.

    Parameters
    ----------
    redis_url:
        Full Redis URL, e.g. ``redis://localhost:6379/0``.
    default_ttl:
        Seconds until episodic run lists expire (default 30 days).
    max_connections:
        Connection pool size.
    """

    def __init__(
        self,
        redis_url: str,
        default_ttl: int = 2_592_000,
        max_connections: int = 50,
    ) -> None:
        self._url = redis_url
        self._default_ttl = default_ttl
        self._max_connections = max_connections
        self._pool: ConnectionPool | None = None
        self._redis: Redis | None = None

    # ── lifecycle ────────────────────────────────────────────────────────────

    async def connect(self) -> None:
        retry = Retry(ExponentialBackoff(), retries=3)
        self._pool = ConnectionPool.from_url(
            self._url,
            max_connections=self._max_connections,
            decode_responses=True,
            retry=retry,
            retry_on_error=[RedisError],
        )
        self._redis = Redis(connection_pool=self._pool)
        await self._redis.ping()
        logger.info("episodic_store_connected", url=self._url)

    async def close(self) -> None:
        if self._redis:
            await self._redis.aclose()
        if self._pool:
            await self._pool.aclose()
        logger.info("episodic_store_closed")

    @property
    def client(self) -> Redis:
        if self._redis is None:
            raise RuntimeError("EpisodicMemoryStore not connected — call connect() first")
        return self._redis

    # ── key builders ─────────────────────────────────────────────────────────

    @staticmethod
    def _runs_key(tenant_id: str, company_domain: str) -> str:
        return f"episodic:{tenant_id}:{company_domain}:runs"

    @staticmethod
    def _processed_key(tenant_id: str) -> str:
        return f"processed:{tenant_id}"

    # ── public API ────────────────────────────────────────────────────────────

    async def save_run_summary(
        self,
        tenant_id: str,
        company_domain: str,
        summary: dict[str, Any],
        ttl: int | None = None,
    ) -> None:
        """
        Append *summary* to the episodic runs list for this company.

        The list itself gets a sliding TTL refresh on every write.
        """
        log = logger.bind(tenant_id=tenant_id, domain=company_domain)
        effective_ttl = ttl if ttl is not None else self._default_ttl
        key = self._runs_key(tenant_id, company_domain)

        payload = {
            **summary,
            "_saved_at": datetime.now(timezone.utc).isoformat(),
        }
        serialised = json.dumps(payload, default=str)

        async with self.client.pipeline(transaction=True) as pipe:
            pipe.rpush(key, serialised)
            pipe.expire(key, effective_ttl)
            await pipe.execute()

        log.info("episodic_run_saved", ttl=effective_ttl)

    async def get_prior_runs(
        self, tenant_id: str, company_domain: str
    ) -> list[dict[str, Any]]:
        """Return all stored run summaries for this company (oldest first)."""
        log = logger.bind(tenant_id=tenant_id, domain=company_domain)
        key = self._runs_key(tenant_id, company_domain)
        raw_list: list[str] = await self.client.lrange(key, 0, -1)
        results = [json.loads(raw) for raw in raw_list]
        log.debug("episodic_prior_runs_fetched", count=len(results))
        return results

    async def mark_company_processed(
        self, tenant_id: str, company_domain: str
    ) -> None:
        """Add *company_domain* to the tenant-scoped processed set."""
        log = logger.bind(tenant_id=tenant_id, domain=company_domain)
        key = self._processed_key(tenant_id)
        await self.client.sadd(key, company_domain)
        log.info("company_marked_processed")

    async def is_company_processed(
        self, tenant_id: str, company_domain: str
    ) -> bool:
        """O(1) check — returns True if domain is in the processed set."""
        log = logger.bind(tenant_id=tenant_id, domain=company_domain)
        key = self._processed_key(tenant_id)
        result: bool = await self.client.sismember(key, company_domain)
        log.debug("company_processed_check", processed=result)
        return result

    async def unmark_company_processed(
        self, tenant_id: str, company_domain: str
    ) -> None:
        """Remove *company_domain* from the processed set (for re-processing)."""
        key = self._processed_key(tenant_id)
        await self.client.srem(key, company_domain)
        logger.info(
            "company_unmarked_processed",
            tenant_id=tenant_id,
            domain=company_domain,
        )

    # ── health ────────────────────────────────────────────────────────────────

    async def ping(self) -> bool:
        """Return True if Redis is reachable."""
        try:
            return await self.client.ping()
        except RedisError:
            return False
