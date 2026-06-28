"""
tests/load/locustfile.py — Locust load test.

Run with:
    locust -f tests/load/locustfile.py --host=http://localhost:8000 --users=50 --spawn-rate=10
"""

from __future__ import annotations

import random
import string
import uuid

from locust import HttpUser, between, task

BASE = "/api/v1"


def random_email() -> str:
    chars = "".join(random.choices(string.ascii_lowercase, k=6))
    return f"load_{chars}@test.com"


class PlatformUser(HttpUser):
    """Simulates a typical platform user session."""

    wait_time = between(1, 3)
    token: str = ""
    icp_id: str = ""
    run_id: str = ""

    def on_start(self) -> None:
        """Register + login once per simulated user."""
        email = random_email()
        self.client.post(
            f"{BASE}/auth/register",
            json={"email": email, "password": "loadtest", "tenant_name": "Load Test Tenant"},
        )
        r = self.client.post(
            f"{BASE}/auth/login",
            json={"email": email, "password": "loadtest"},
        )
        if r.status_code == 200:
            self.token = r.json()["access_token"]
        # Create one ICP config
        r2 = self.client.post(
            f"{BASE}/icp",
            json={"name": "Load ICP", "rules_json": {"min_headcount": 50}},
            headers=self._headers(),
        )
        if r2.status_code == 201:
            self.icp_id = r2.json()["id"]

    def _headers(self) -> dict:
        return {"Authorization": f"Bearer {self.token}"}

    @task(5)
    def list_runs(self) -> None:
        self.client.get(f"{BASE}/runs", headers=self._headers(), name="list_runs")

    @task(3)
    def list_icp(self) -> None:
        self.client.get(f"{BASE}/icp", headers=self._headers(), name="list_icp")

    @task(2)
    def health_check(self) -> None:
        self.client.get("/health", name="health")

    @task(2)
    def create_run(self) -> None:
        if not self.icp_id:
            return
        r = self.client.post(
            f"{BASE}/runs",
            json={"icp_config_id": self.icp_id, "max_companies": 5},
            headers=self._headers(),
            name="create_run",
        )
        if r.status_code == 201:
            self.run_id = r.json()["id"]

    @task(3)
    def get_run(self) -> None:
        if not self.run_id:
            return
        self.client.get(f"{BASE}/runs/{self.run_id}", headers=self._headers(), name="get_run")

    @task(1)
    def list_hitl(self) -> None:
        self.client.get(f"{BASE}/hitl", headers=self._headers(), name="list_hitl")
