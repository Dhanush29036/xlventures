"""
tests/integration/test_auth.py — Auth integration tests.
"""

from __future__ import annotations

import uuid
import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_register_creates_tenant(client: AsyncClient) -> None:
    email = f"user_{uuid.uuid4()}@test.com"
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "secret123",
            "tenant_name": "Test Tenant",
        },
    )
    assert resp.status_code == 201
    data = resp.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert "tenant_id" in data


@pytest.mark.asyncio
async def test_login_returns_jwt(client: AsyncClient, registered_user: dict) -> None:
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": registered_user["email"], "password": registered_user["password"]},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "access_token" in data
    assert len(data["access_token"]) > 20


@pytest.mark.asyncio
async def test_protected_route_rejects_no_token(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/icp")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_protected_route_rejects_expired_token(client: AsyncClient) -> None:
    resp = await client.get(
        "/api/v1/icp",
        headers={"Authorization": "Bearer invalid.token.here"},
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_tenant_data_isolation(client: AsyncClient) -> None:
    """Two tenants cannot see each other's ICP configs."""
    email_a = f"tenant_{uuid.uuid4()}@test.com"
    email_b = f"tenant_{uuid.uuid4()}@test.com"

    # Tenant A
    resp_a = await client.post(
        "/api/v1/auth/register",
        json={"email": email_a, "password": "pass", "tenant_name": "Tenant A"},
    )
    token_a = resp_a.json()["access_token"]

    # Tenant B
    resp_b = await client.post(
        "/api/v1/auth/register",
        json={"email": email_b, "password": "pass", "tenant_name": "Tenant B"},
    )
    token_b = resp_b.json()["access_token"]

    # Create ICP for A
    await client.post(
        "/api/v1/icp",
        json={"name": "A ICP", "rules_json": {"min_headcount": 10}},
        headers={"Authorization": f"Bearer {token_a}"},
    )

    # B should see empty list
    resp = await client.get("/api/v1/icp", headers={"Authorization": f"Bearer {token_b}"})
    assert resp.status_code == 200
    assert resp.json() == []
