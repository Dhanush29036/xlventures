"""
pytest-asyncio tests for MemoryManager.

All external stores (Redis, Neo4j, Qdrant, Postgres) are replaced with
AsyncMock instances so these tests run without any running infrastructure.

Tests
─────
• test_should_skip_returns_true_when_redis_hit
• test_should_skip_returns_true_when_neo4j_hit_and_backfills_redis
• test_should_skip_returns_false_when_not_processed
• test_record_company_enriched_writes_to_all_stores
• test_record_company_enriched_partial_failure_does_not_raise
• test_find_icp_candidates_excludes_processed
• test_find_icp_candidates_returns_empty_when_no_semantic_hits
• test_get_company_context_merges_redis_and_neo4j
• test_health_returns_all_true_when_stores_healthy
• test_health_returns_degraded_when_store_down
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from app.memory.manager import HealthChecker, MemoryManager


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


def make_memory_manager(
    *,
    redis_processed: bool = False,
    neo4j_exists: bool = False,
    semantic_hits: list[dict[str, Any]] | None = None,
    neo4j_icp_companies: list[dict[str, Any]] | None = None,
    redis_prior_runs: list[dict[str, Any]] | None = None,
    neo4j_graph: dict[str, Any] | None = None,
) -> tuple[MemoryManager, MagicMock, MagicMock, MagicMock, MagicMock]:
    """
    Build a MemoryManager with fully mocked stores.

    Returns
    -------
    (manager, pg_mock, redis_mock, neo4j_mock, qdrant_mock)
    """
    pg_mock = MagicMock()
    # Simulate successful SELECT 1 for health check
    pg_session = AsyncMock()
    pg_session.__aenter__ = AsyncMock(return_value=pg_session)
    pg_session.__aexit__ = AsyncMock(return_value=False)
    pg_session.execute = AsyncMock()
    pg_mock.return_value = pg_session

    redis_mock = AsyncMock()
    redis_mock.is_company_processed = AsyncMock(return_value=redis_processed)
    redis_mock.mark_company_processed = AsyncMock()
    redis_mock.save_run_summary = AsyncMock()
    redis_mock.get_prior_runs = AsyncMock(return_value=redis_prior_runs or [])
    redis_mock.ping = AsyncMock(return_value=True)

    neo4j_mock = AsyncMock()
    neo4j_mock.company_exists = AsyncMock(return_value=neo4j_exists)
    neo4j_mock.upsert_company = AsyncMock()
    neo4j_mock.upsert_person = AsyncMock()
    neo4j_mock.add_signal = AsyncMock()
    neo4j_mock.link_tenant_targets = AsyncMock()
    neo4j_mock.get_company_with_people = AsyncMock(return_value=neo4j_graph or {})
    neo4j_mock.find_companies_by_icp = AsyncMock(
        return_value=neo4j_icp_companies or []
    )
    neo4j_mock.ping = AsyncMock(return_value=True)

    qdrant_mock = AsyncMock()
    qdrant_mock.upsert_company_embedding = AsyncMock()
    qdrant_mock.find_similar_companies = AsyncMock(
        return_value=semantic_hits if semantic_hits is not None else []
    )
    qdrant_mock.ping = AsyncMock(return_value=True)

    # Patch AuditLogRepository so we don't need a real DB
    with patch("app.memory.manager.AuditLogRepository") as audit_cls:
        audit_instance = AsyncMock()
        audit_instance.append = AsyncMock()
        audit_cls.return_value = audit_instance

        manager = MemoryManager(
            pg=pg_mock,
            redis=redis_mock,
            neo4j=neo4j_mock,
            qdrant=qdrant_mock,
        )
        # Patch the audit repo on the already-constructed instance
        manager._audit = audit_instance

    return manager, pg_mock, redis_mock, neo4j_mock, qdrant_mock


# ---------------------------------------------------------------------------
# should_skip_company
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_should_skip_returns_true_when_redis_hit() -> None:
    """Redis processed-set hit → should return True without calling Neo4j."""
    manager, _, redis_mock, neo4j_mock, _ = make_memory_manager(redis_processed=True)

    result = await manager.should_skip_company("tenant1", "example.com")

    assert result is True
    redis_mock.is_company_processed.assert_awaited_once_with("tenant1", "example.com")
    # Neo4j must NOT be called when Redis already has the answer
    neo4j_mock.company_exists.assert_not_awaited()


@pytest.mark.asyncio
async def test_should_skip_returns_true_when_neo4j_hit_and_backfills_redis() -> None:
    """Redis miss + Neo4j hit → returns True and back-fills Redis."""
    manager, _, redis_mock, neo4j_mock, _ = make_memory_manager(
        redis_processed=False, neo4j_exists=True
    )

    result = await manager.should_skip_company("tenant1", "example.com")

    assert result is True
    neo4j_mock.company_exists.assert_awaited_once_with("example.com")
    redis_mock.mark_company_processed.assert_awaited_once_with("tenant1", "example.com")


@pytest.mark.asyncio
async def test_should_skip_returns_false_when_not_processed() -> None:
    """Redis miss + Neo4j miss → returns False (proceed with enrichment)."""
    manager, _, _, _, _ = make_memory_manager(
        redis_processed=False, neo4j_exists=False
    )

    result = await manager.should_skip_company("tenant1", "new-company.com")

    assert result is False


# ---------------------------------------------------------------------------
# record_company_enriched
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_record_company_enriched_writes_to_all_stores() -> None:
    """All four stores must receive their respective write calls."""
    manager, pg_mock, redis_mock, neo4j_mock, qdrant_mock = make_memory_manager()

    company_data = {
        "name": "Acme Corp",
        "description": "Enterprise SaaS for logistics",
        "headcount": 250,
        "funding_stage": "Series B",
    }
    people = [
        {"email": "alice@acme.com", "name": "Alice", "title": "CTO"},
        {"email": "bob@acme.com", "name": "Bob", "title": "VP Sales"},
    ]
    signals = [
        {"type": "funding_round", "amount": 20_000_000, "occurred_at": "2024-01-15"},
    ]
    run_id = uuid.uuid4()

    await manager.record_company_enriched(
        tenant_id="tenant1",
        domain="acme.com",
        company_data=company_data,
        people=people,
        signals=signals,
        run_id=run_id,
    )

    # Neo4j writes
    neo4j_mock.upsert_company.assert_awaited_once()
    assert neo4j_mock.upsert_person.await_count == 2
    neo4j_mock.add_signal.assert_awaited_once()
    neo4j_mock.link_tenant_targets.assert_awaited_once_with("tenant1", "acme.com")

    # Qdrant write
    qdrant_mock.upsert_company_embedding.assert_awaited_once()

    # Redis writes
    redis_mock.mark_company_processed.assert_awaited_once_with("tenant1", "acme.com")
    redis_mock.save_run_summary.assert_awaited_once()

    # Audit log
    manager._audit.append.assert_awaited_once()


@pytest.mark.asyncio
async def test_record_company_enriched_partial_failure_does_not_raise() -> None:
    """
    Even if one store write fails, the method must complete without raising
    (partial failures are logged as warnings, not exceptions).
    """
    manager, _, _, neo4j_mock, qdrant_mock = make_memory_manager()
    neo4j_mock.upsert_company.side_effect = RuntimeError("Neo4j timeout")
    qdrant_mock.upsert_company_embedding.side_effect = RuntimeError("Qdrant error")

    # Must not raise
    await manager.record_company_enriched(
        tenant_id="tenant1",
        domain="fail.com",
        company_data={"name": "Fail Co"},
        people=[],
        signals=[],
    )


# ---------------------------------------------------------------------------
# find_icp_candidates
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_find_icp_candidates_excludes_processed() -> None:
    """
    Companies that are already in the Redis processed set must be filtered out
    even if Qdrant returns them as semantic matches.
    """
    semantic_hits = [
        {"domain": "processed.com", "score": 0.95, "funding_stage": "Series A"},
        {"domain": "new-lead.com",  "score": 0.88, "funding_stage": "Series A"},
    ]

    async def fake_is_processed(tenant_id: str, domain: str) -> bool:
        return domain == "processed.com"

    manager, _, redis_mock, _, _ = make_memory_manager(
        semantic_hits=semantic_hits,
        redis_processed=False,  # default, overridden below
    )
    redis_mock.is_company_processed = AsyncMock(side_effect=fake_is_processed)

    icp_config = {
        "description": "B2B SaaS Series A startup",
        "min_headcount": 50,
        "max_headcount": 500,
        "funding_stages": ["Series A"],
    }

    results = await manager.find_icp_candidates("tenant1", icp_config)

    domains = [r["domain"] for r in results]
    assert "processed.com" not in domains
    assert "new-lead.com" in domains


@pytest.mark.asyncio
async def test_find_icp_candidates_returns_empty_when_no_semantic_hits() -> None:
    """When Qdrant returns no hits, the method should return an empty list."""
    manager, _, _, _, _ = make_memory_manager(semantic_hits=[])

    results = await manager.find_icp_candidates(
        "tenant1",
        {"description": "unicorn startup", "funding_stages": ["Series C"]},
    )

    assert results == []


@pytest.mark.asyncio
async def test_find_icp_candidates_sorted_by_score() -> None:
    """Results must be sorted by semantic score descending."""
    hits = [
        {"domain": "a.com", "score": 0.70, "funding_stage": "Series A"},
        {"domain": "b.com", "score": 0.92, "funding_stage": "Series A"},
        {"domain": "c.com", "score": 0.85, "funding_stage": "Series A"},
    ]
    manager, _, redis_mock, _, _ = make_memory_manager(semantic_hits=hits)
    redis_mock.is_company_processed = AsyncMock(return_value=False)

    results = await manager.find_icp_candidates(
        "tenant1", {"description": "...", "funding_stages": ["Series A"]}
    )

    scores = [r["score"] for r in results]
    assert scores == sorted(scores, reverse=True)


# ---------------------------------------------------------------------------
# get_company_context
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_company_context_merges_redis_and_neo4j() -> None:
    """Context must contain both prior_runs from Redis and graph from Neo4j."""
    prior_runs = [{"summary": "run 1"}, {"summary": "run 2"}]
    graph_data = {"company": {"domain": "acme.com"}, "people": [], "signals": []}

    manager, _, redis_mock, neo4j_mock, _ = make_memory_manager(
        redis_prior_runs=prior_runs,
        neo4j_graph=graph_data,
    )

    context = await manager.get_company_context("tenant1", "acme.com")

    assert context["domain"] == "acme.com"
    assert context["tenant_id"] == "tenant1"
    assert context["prior_runs"] == prior_runs
    assert context["graph"] == graph_data


# ---------------------------------------------------------------------------
# HealthChecker
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_health_returns_all_true_when_stores_healthy() -> None:
    manager, _, _, _, _ = make_memory_manager()
    checker = HealthChecker(manager)

    result = await checker.check()

    assert result["status"] == "healthy"
    assert all(result["stores"].values())


@pytest.mark.asyncio
async def test_health_returns_degraded_when_store_down() -> None:
    manager, _, redis_mock, _, _ = make_memory_manager()
    redis_mock.ping = AsyncMock(return_value=False)

    checker = HealthChecker(manager)
    result = await checker.check()

    assert result["status"] == "degraded"
    assert result["stores"]["redis"] is False
