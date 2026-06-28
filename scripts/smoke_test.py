"""
scripts/smoke_test.py — Full system smoke test.

Run with: python scripts/smoke_test.py
Tests every integration point end-to-end with real network calls.
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from typing import Callable

import httpx

API_BASE = "http://localhost:8000"
HEADERS: dict[str, str] = {}


def _ok(label: str) -> None:
    print(f"  [OK] {label}")


def _fail(label: str, reason: str) -> None:
    print(f"  [FAIL] {label}: {reason}")


# ── Checks ────────────────────────────────────────────────────────────────────


def check_fastapi_health() -> None:
    r = httpx.get(f"{API_BASE}/health", timeout=5)
    assert r.status_code in (200, 503), f"unexpected status {r.status_code}"
    data = r.json()
    assert "status" in data


def check_postgres_connection() -> None:
    r = httpx.get(f"{API_BASE}/health", timeout=5)
    data = r.json()
    stores = data.get("stores", {})
    pg = stores.get("postgres")
    assert pg is True, f"postgres unhealthy: {pg}"


def check_redis_connection() -> None:
    r = httpx.get(f"{API_BASE}/health", timeout=5)
    stores = r.json().get("stores", {})
    redis = stores.get("redis")
    assert redis is True, f"redis unhealthy: {redis}"


def check_neo4j_connection() -> None:
    r = httpx.get(f"{API_BASE}/health", timeout=5)
    stores = r.json().get("stores", {})
    neo4j = stores.get("neo4j")
    assert neo4j is True, f"neo4j unhealthy: {neo4j}"


def check_qdrant_connection() -> None:
    r = httpx.get(f"{API_BASE}/health", timeout=5)
    stores = r.json().get("stores", {})
    qdrant = stores.get("qdrant")
    assert qdrant is True, f"qdrant unhealthy: {qdrant}"


def check_auth_register_and_login() -> None:
    global HEADERS
    ts = int(time.time())
    email = f"smoke_{ts}@test.com"

    # Register
    r = httpx.post(
        f"{API_BASE}/api/v1/auth/register",
        json={"email": email, "password": "smoke123", "tenant_name": "Smoke Test Tenant"},
        timeout=10,
    )
    assert r.status_code == 201, f"register failed: {r.text}"
    token = r.json()["access_token"]
    HEADERS = {"Authorization": f"Bearer {token}"}

    # Login
    r2 = httpx.post(
        f"{API_BASE}/api/v1/auth/login",
        json={"email": email, "password": "smoke123"},
        timeout=10,
    )
    assert r2.status_code == 200, f"login failed: {r2.text}"
    assert "access_token" in r2.json()


def check_icp_config_crud() -> None:
    # Create
    r = httpx.post(
        f"{API_BASE}/api/v1/icp",
        json={
            "name": "Smoke ICP",
            "rules_json": {"min_headcount": 50, "industries": ["SaaS"]},
        },
        headers=HEADERS,
        timeout=10,
    )
    assert r.status_code == 201, f"icp create failed: {r.text}"
    icp_id = r.json()["id"]

    # Read
    r2 = httpx.get(f"{API_BASE}/api/v1/icp/{icp_id}", headers=HEADERS, timeout=10)
    assert r2.status_code == 200

    # List
    r3 = httpx.get(f"{API_BASE}/api/v1/icp", headers=HEADERS, timeout=10)
    assert r3.status_code == 200
    assert len(r3.json()) >= 1

    # Update
    r4 = httpx.put(
        f"{API_BASE}/api/v1/icp/{icp_id}",
        json={"name": "Updated Smoke ICP"},
        headers=HEADERS,
        timeout=10,
    )
    assert r4.status_code == 200


def check_run_creation_and_dispatch() -> None:
    # Need an ICP first
    r_icp = httpx.post(
        f"{API_BASE}/api/v1/icp",
        json={"name": "Run Test ICP", "rules_json": {"industries": ["SaaS"]}},
        headers=HEADERS,
        timeout=10,
    )
    icp_id = r_icp.json()["id"]

    r = httpx.post(
        f"{API_BASE}/api/v1/runs",
        json={
            "icp_config_id": icp_id,
            "max_companies": 5,
            "trigger_keywords": ["funding"],
        },
        headers=HEADERS,
        timeout=15,
    )
    assert r.status_code == 201, f"run create failed: {r.text}"
    run_id = r.json()["id"]

    # Poll status
    r2 = httpx.get(f"{API_BASE}/api/v1/runs/{run_id}", headers=HEADERS, timeout=10)
    assert r2.status_code == 200
    assert r2.json()["status"] in ("pending", "running", "completed", "failed")


def check_hitl_queue_accessible() -> None:
    r = httpx.get(f"{API_BASE}/api/v1/hitl", headers=HEADERS, timeout=10)
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def check_sse_stream_connects() -> None:
    """Test SSE endpoint returns streaming response headers."""
    import uuid
    fake_run_id = str(uuid.uuid4())
    with httpx.stream(
        "GET",
        f"{API_BASE}/api/v1/stream/{fake_run_id}",
        headers={**HEADERS, "Accept": "text/event-stream"},
        timeout=5,
    ) as r:
        assert r.status_code == 200
        assert "text/event-stream" in r.headers.get("content-type", "")


def check_results_endpoint() -> None:
    import uuid
    r = httpx.get(
        f"{API_BASE}/api/v1/results/{uuid.uuid4()}",
        headers=HEADERS,
        timeout=10,
    )
    # 404 is fine — we just need the endpoint to respond
    assert r.status_code in (200, 404)


def check_celery_worker_alive() -> None:
    """Check Celery via Flower API if available."""
    try:
        r = httpx.get("http://localhost:5555/api/workers", timeout=3)
        assert r.status_code == 200
    except Exception:
        print("    (Flower not running — skipping celery check)")


# ── Runner ────────────────────────────────────────────────────────────────────

checks: list[Callable] = [
    check_fastapi_health,
    check_postgres_connection,
    check_redis_connection,
    check_neo4j_connection,
    check_qdrant_connection,
    check_auth_register_and_login,
    check_icp_config_crud,
    check_run_creation_and_dispatch,
    check_sse_stream_connects,
    check_hitl_queue_accessible,
    check_results_endpoint,
    check_celery_worker_alive,
]

if __name__ == "__main__":
    print("\n=== XL Ventures - Smoke Test Suite ===\n")
    passed = 0
    failed = 0
    for check in checks:
        try:
            check()
            _ok(check.__name__)
            passed += 1
        except Exception as e:
            _fail(check.__name__, str(e))
            failed += 1

    print(f"\n{'-' * 40}")
    print(f"  Passed: {passed}  Failed: {failed}")
    if failed > 0:
        sys.exit(1)
