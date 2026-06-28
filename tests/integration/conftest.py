"""
tests/integration/conftest.py — Shared fixtures for integration tests.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest_asyncio.fixture
async def client() -> AsyncClient:
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            yield ac


import uuid

@pytest_asyncio.fixture
async def registered_user(client: AsyncClient) -> dict:
    email = f"fixture_user_{uuid.uuid4()}@test.com"
    resp = await client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": "testpass123",
            "tenant_name": "Fixture Tenant",
        },
    )
    data = resp.json()
    return {
        "email": email,
        "password": "testpass123",
        "token": data.get("access_token", ""),
        "tenant_id": data.get("tenant_id", ""),
    }


@pytest_asyncio.fixture
async def auth_headers(registered_user: dict) -> dict:
    return {"Authorization": f"Bearer {registered_user['token']}"}
