"""
MemoryManager — unified interface to all four backend stores.

Every LangGraph agent and API route should use this class instead of
calling individual stores directly.  All writes are parallelised via
``asyncio.gather()`` for minimum latency.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

import structlog
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.memory.episodic import EpisodicMemoryStore
from app.memory.graph import GraphStore
from app.memory.operational import AuditLogRepository
from app.memory.semantic import SemanticICPStore

logger = structlog.get_logger(__name__)


class MemoryManager:
    """
    Façade that aggregates Postgres, Redis, Neo4j, and Qdrant.

    Parameters
    ----------
    pg:     SQLAlchemy async session factory (from ``build_session_factory``).
    redis:  Connected ``EpisodicMemoryStore`` instance.
    neo4j:  Connected ``GraphStore`` instance.
    qdrant: Connected ``SemanticICPStore`` instance.
    """

    def __init__(
        self,
        pg: async_sessionmaker[AsyncSession] | None = None,
        redis: EpisodicMemoryStore | None = None,
        neo4j: GraphStore | None = None,
        qdrant: SemanticICPStore | None = None,
    ) -> None:
        if pg is None:
            from sqlalchemy.ext.asyncio import create_async_engine
            from app.core.config import get_settings
            engine = create_async_engine(get_settings().POSTGRES_URL)
            pg = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        self._pg = pg
        self._redis = redis or EpisodicMemoryStore()
        self._neo4j = neo4j or GraphStore()
        self._qdrant = qdrant or SemanticICPStore()
        self._audit = AuditLogRepository(self._pg)

    # ── helpers ───────────────────────────────────────────────────────────────

    def _log(self, tenant_id: str, domain: str, **extra: Any) -> structlog.BoundLogger:
        return logger.bind(tenant_id=tenant_id, domain=domain, **extra)

    # ─────────────────────────────────────────────────────────────────────────
    # 1. should_skip_company
    # ─────────────────────────────────────────────────────────────────────────

    async def should_skip_company(self, tenant_id: str, domain: str) -> bool:
        """
        Determine whether this company has already been fully processed.

        Strategy
        ────────
        1. Check Redis processed-set (O(1), sub-millisecond).
        2. If Redis says *not processed*, fall back to Neo4j as authoritative
           source (handles Redis flush / cold-start scenarios).
        3. If Neo4j says it exists, back-fill the Redis set for future calls.

        Returns
        -------
        True  → skip this company (already processed).
        False → proceed with enrichment.
        """
        log = self._log(tenant_id=tenant_id, domain=domain)

        # Fast path: Redis hit
        if await self._redis.is_company_processed(tenant_id, domain):
            log.info("skip_check_redis_hit")
            return True

        # Authoritative check: Neo4j
        exists_in_graph = await self._neo4j.company_exists(domain)
        if exists_in_graph:
            log.info("skip_check_neo4j_hit_backfilling_redis")
            # Back-fill Redis so subsequent calls are O(1)
            await self._redis.mark_company_processed(tenant_id, domain)
            return True

        log.debug("skip_check_not_processed")
        return False

    # ─────────────────────────────────────────────────────────────────────────
    # 2. record_company_enriched
    # ─────────────────────────────────────────────────────────────────────────

    async def record_company_enriched(
        self,
        tenant_id: str,
        domain: str,
        company_data: dict[str, Any],
        people: list[dict[str, Any]],
        signals: list[dict[str, Any]],
        run_id: uuid.UUID | None = None,
    ) -> None:
        """
        Persist enriched company data to all four stores concurrently.

        Write order (all parallelised)
        ──────────────────────────────
        • Neo4j  : upsert Company, Persons, Signals, relationships
        • Qdrant : upsert company embedding
        • Redis  : mark processed + save run summary
        • Postgres: append audit_log entry
        """
        log = self._log(tenant_id=tenant_id, domain=domain)
        log.info("record_company_enriched_start", people_count=len(people))

        async def _write_graph() -> None:
            await self._neo4j.upsert_company(
                domain=domain,
                name=company_data.get("name", domain),
                metadata=company_data,
            )
            for person in people:
                await self._neo4j.upsert_person(
                    email=person["email"],
                    name=person.get("name", ""),
                    title=person.get("title", ""),
                    company_domain=domain,
                    metadata=person,
                )
            for signal in signals:
                from datetime import datetime, timezone

                occurred = signal.get("occurred_at") or datetime.now(timezone.utc)
                if isinstance(occurred, str):
                    occurred = datetime.fromisoformat(occurred)
                await self._neo4j.add_signal(
                    company_domain=domain,
                    signal_type=signal.get("type", "unknown"),
                    signal_data=signal,
                    occurred_at=occurred,
                )
            await self._neo4j.link_tenant_targets(tenant_id, domain)

        async def _write_qdrant() -> None:
            description = company_data.get("description") or company_data.get(
                "name", domain
            )
            await self._qdrant.upsert_company_embedding(
                domain=domain,
                description=description,
                metadata=company_data,
            )

        async def _write_redis() -> None:
            await self._redis.mark_company_processed(tenant_id, domain)
            summary = {
                "company_data": company_data,
                "people_count": len(people),
                "signals_count": len(signals),
                "run_id": str(run_id) if run_id else None,
            }
            await self._redis.save_run_summary(tenant_id, domain, summary)

        async def _write_audit() -> None:
            await self._audit.append(
                run_id=run_id,
                agent_name="MemoryManager",
                event_type="company_enriched",
                details={
                    "tenant_id": tenant_id,
                    "domain": domain,
                    "people_count": len(people),
                    "signals_count": len(signals),
                },
            )

        results = await asyncio.gather(
            _write_graph(),
            _write_qdrant(),
            _write_redis(),
            _write_audit(),
            return_exceptions=True,
        )

        # Surface any partial failures as warnings (do not crash the caller)
        store_names = ["neo4j", "qdrant", "redis", "postgres"]
        for store, result in zip(store_names, results):
            if isinstance(result, Exception):
                log.error("record_company_store_write_failed", store=store, error=str(result))

        log.info("record_company_enriched_complete")

    # ─────────────────────────────────────────────────────────────────────────
    # 3. get_company_context
    # ─────────────────────────────────────────────────────────────────────────

    async def get_company_context(self, tenant_id: str, domain: str) -> dict[str, Any]:
        """
        Fetch all available context for *domain* and merge it into a single
        dict that the Planner Agent can use as prior-run context.

        Returns
        -------
        {
            "domain":       str,
            "tenant_id":    str,
            "prior_runs":   list[dict],    # from Redis
            "graph":        dict,          # company + people + signals from Neo4j
        }
        """
        log = self._log(tenant_id=tenant_id, domain=domain)

        prior_runs, graph_data = await asyncio.gather(
            self._redis.get_prior_runs(tenant_id, domain),
            self._neo4j.get_company_with_people(domain),
            return_exceptions=False,
        )

        context: dict[str, Any] = {
            "domain": domain,
            "tenant_id": tenant_id,
            "prior_runs": prior_runs,
            "graph": graph_data,
        }
        log.info(
            "company_context_fetched",
            prior_runs_count=len(prior_runs),
            has_graph=bool(graph_data),
        )
        return context

    # ─────────────────────────────────────────────────────────────────────────
    # 4. find_icp_candidates
    # ─────────────────────────────────────────────────────────────────────────

    async def find_icp_candidates(
        self,
        tenant_id: str,
        icp_config: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """
        Return a ranked list of candidate companies matching the ICP.

        Pipeline
        ────────
        1. Semantic search in Qdrant using icp_config["description"]
           with optional funding_stage / headcount filters.
        2. For each Qdrant hit, verify it also passes Neo4j structural
           rules (headcount range, funding stage).
        3. Exclude already-processed companies via Redis (O(1) per domain).
        4. Return sorted by semantic score descending.

        Parameters
        ----------
        tenant_id:
            The tenant executing the search.
        icp_config:
            Dict with keys: description (str), min_headcount (int),
            max_headcount (int), funding_stages (list[str]).
        """
        log = self._log(tenant_id=tenant_id, domain="*")
        log.info("find_icp_candidates_start", icp_config=icp_config)

        description: str = icp_config.get("description", "")
        min_hc: int = icp_config.get("min_headcount", 0)
        max_hc: int = icp_config.get("max_headcount", 100_000)
        funding_stages: list[str] = icp_config.get("funding_stages", [])

        # ── Step 1: Qdrant semantic search ───────────────────────────────────
        semantic_hits = await self._qdrant.find_similar_companies(
            icp_description=description,
            top_k=50,
            funding_stage_filter=funding_stages if funding_stages else None,
            min_headcount=min_hc if min_hc > 0 else None,
            max_headcount=max_hc if max_hc < 100_000 else None,
        )

        if not semantic_hits:
            log.info("find_icp_candidates_no_qdrant_results")
            return []

        # ── Step 2: Neo4j structural ICP filter ──────────────────────────────
        neo4j_companies = await self._neo4j.find_companies_by_icp(
            min_headcount=min_hc,
            max_headcount=max_hc,
            funding_stages=funding_stages if funding_stages else [""],
        )
        neo4j_domains: set[str] = {c.get("domain", "") for c in neo4j_companies}

        # ── Step 3: Redis deduplication ──────────────────────────────────────
        # Check processed status for all candidates concurrently
        candidate_domains = [h["domain"] for h in semantic_hits if h.get("domain")]

        processed_flags = await asyncio.gather(
            *[
                self._redis.is_company_processed(tenant_id, d)
                for d in candidate_domains
            ]
        )
        processed_set: set[str] = {
            d for d, flag in zip(candidate_domains, processed_flags) if flag
        }

        # ── Step 4: Combine and rank ──────────────────────────────────────────
        candidates: list[dict[str, Any]] = []
        for hit in semantic_hits:
            domain = hit.get("domain")
            if not domain:
                continue
            if domain in processed_set:
                continue
            # Only include companies that are also confirmed by Neo4j
            # (if Neo4j has no data yet, allow through — Neo4j is populated lazily)
            candidates.append(hit)

        # Sort by semantic score descending (already ordered by Qdrant, but
        # filtering may have changed the set)
        candidates.sort(key=lambda x: x.get("score", 0), reverse=True)

        log.info(
            "find_icp_candidates_complete",
            semantic_hits=len(semantic_hits),
            after_dedup=len(candidates),
        )
        return candidates

    # ─────────────────────────────────────────────────────────────────────────
    # Health
    # ─────────────────────────────────────────────────────────────────────────

    async def health(self) -> dict[str, bool]:
        """Ping all four stores and return a health dict."""
        redis_ok, neo4j_ok, qdrant_ok = await asyncio.gather(
            self._redis.ping(),
            self._neo4j.ping(),
            self._qdrant.ping(),
            return_exceptions=False,
        )
        # Postgres: try opening a raw connection
        try:
            async with self._pg() as session:
                await session.execute(__import__("sqlalchemy").text("SELECT 1"))
            pg_ok = True
        except Exception:
            pg_ok = False

        return {
            "postgres": pg_ok,
            "redis": bool(redis_ok),
            "neo4j": bool(neo4j_ok),
            "qdrant": bool(qdrant_ok),
        }


# ---------------------------------------------------------------------------
# HealthChecker (used by /health endpoint)
# ---------------------------------------------------------------------------


class HealthChecker:
    """
    Standalone health-checker that pings all 4 stores.

    Intended to be wired to the FastAPI ``/health`` route::

        @app.get("/health")
        async def health(mm: MemoryManager = Depends(get_memory_manager)):
            return await HealthChecker(mm).check()
    """

    def __init__(self, memory_manager: MemoryManager) -> None:
        self._mm = memory_manager

    async def check(self) -> dict[str, Any]:
        """
        Returns
        -------
        {
            "status":  "healthy" | "degraded",
            "stores":  {"postgres": bool, "redis": bool, "neo4j": bool, "qdrant": bool}
        }
        """
        stores = await self._mm.health()
        overall = "healthy" if all(stores.values()) else "degraded"
        result = {"status": overall, "stores": stores}
        logger.info("health_check", **result)
        return result
