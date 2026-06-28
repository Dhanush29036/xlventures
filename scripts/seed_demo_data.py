"""
scripts/seed_demo_data.py — Seeds realistic demo data.

Run with: python scripts/seed_demo_data.py
"""

from __future__ import annotations

import asyncio
import sys
import uuid
from datetime import datetime, timedelta, timezone

import httpx

API_BASE = "http://localhost:8000"

DEMO_EMAIL = "demo@xlventures.ai"
DEMO_PASSWORD = "demo123"
DEMO_TENANT = "XL Ventures Demo"

COMPANIES = [
    {
        "domain": "acme-saas.io",
        "name": "Acme SaaS",
        "headcount": 150,
        "funding_stage": "Series B",
        "industry": "SaaS",
        "hq_country": "US",
        "annual_revenue_usd": 12_000_000,
        "tech_stack": ["Python", "AWS", "React"],
        "icp_score": 0.92,
        "recommended_action": "outreach",
        "people": [
            {"email": "cto@acme-saas.io", "name": "Alex Chen", "title": "CTO", "seniority": "C-Suite", "is_decision_maker": True},
            {"email": "vpe@acme-saas.io", "name": "Jordan Smith", "title": "VP Engineering", "seniority": "VP", "is_decision_maker": True},
            {"email": "eng@acme-saas.io", "name": "Riley Johnson", "title": "Senior Engineer", "seniority": "IC", "is_decision_maker": False},
        ],
        "signals": [
            {"type": "funding_round", "score": 0.9, "data": {"stage": "Series B", "amount_usd": 25_000_000}},
            {"type": "hiring_surge", "score": 0.7, "data": {"growth_pct": 0.22}},
        ],
    },
    {
        "domain": "fintech-flow.com",
        "name": "FintechFlow",
        "headcount": 280,
        "funding_stage": "Series C",
        "industry": "Fintech",
        "hq_country": "UK",
        "annual_revenue_usd": 45_000_000,
        "tech_stack": ["Go", "Kubernetes", "PostgreSQL"],
        "icp_score": 0.87,
        "recommended_action": "outreach",
        "people": [
            {"email": "cpo@fintech-flow.com", "name": "Sam Patel", "title": "CPO", "seniority": "C-Suite", "is_decision_maker": True},
            {"email": "vp@fintech-flow.com", "name": "Morgan Lee", "title": "VP Product", "seniority": "VP", "is_decision_maker": True},
        ],
        "signals": [
            {"type": "job_posting", "score": 0.5, "data": {"roles": ["Senior Backend Engineer", "Staff Engineer"]}},
        ],
    },
    {
        "domain": "cloudnative.dev",
        "name": "CloudNative Dev",
        "headcount": 85,
        "funding_stage": "Series A",
        "industry": "Cloud Infrastructure",
        "hq_country": "US",
        "annual_revenue_usd": 5_000_000,
        "tech_stack": ["Rust", "Terraform", "GCP"],
        "icp_score": 0.74,
        "recommended_action": "nurture",
        "people": [
            {"email": "ceo@cloudnative.dev", "name": "Taylor Wong", "title": "CEO", "seniority": "C-Suite", "is_decision_maker": True},
        ],
        "signals": [
            {"type": "tech_adoption", "score": 0.6, "data": {"stack": ["Rust", "Terraform"]}},
        ],
    },
]

ICP_CONFIGS = [
    {
        "name": "SaaS Mid-Market Engineering",
        "rules_json": {
            "min_headcount": 50,
            "max_headcount": 500,
            "funding_stages": ["Series A", "Series B", "Series C"],
            "industries": ["SaaS", "Cloud Infrastructure", "DevTools"],
            "hq_countries": ["US", "UK", "EU"],
            "min_revenue_usd": 3_000_000,
        },
        "persona_json": {
            "target_titles": ["CTO", "VP Engineering", "Head of Engineering", "VP Product"],
            "target_seniorities": ["C-Suite", "VP"],
            "description": "Engineering decision makers at scaling SaaS companies",
        },
    },
    {
        "name": "Fintech Series B+",
        "rules_json": {
            "min_headcount": 100,
            "funding_stages": ["Series B", "Series C", "Series D"],
            "industries": ["Fintech", "Insurtech", "RegTech"],
            "hq_countries": ["US", "UK"],
            "min_revenue_usd": 10_000_000,
        },
        "persona_json": {
            "target_titles": ["CPO", "CTO", "VP Engineering", "CIO"],
            "target_seniorities": ["C-Suite", "VP"],
            "description": "Product and technical leaders at late-stage fintech",
        },
    },
]


async def seed() -> None:
    print("\n[SEED] Seeding XL Ventures Demo Data\n")
    async with httpx.AsyncClient(base_url=API_BASE, timeout=30) as client:
        # Register demo user
        print("  Creating demo user...")
        r = await client.post(
            "/api/v1/auth/register",
            json={"email": DEMO_EMAIL, "password": DEMO_PASSWORD, "tenant_name": DEMO_TENANT},
        )
        if r.status_code == 409:
            # Already exists — login instead
            r = await client.post(
                "/api/v1/auth/login",
                json={"email": DEMO_EMAIL, "password": DEMO_PASSWORD},
            )
        assert r.status_code in (200, 201), f"Auth failed: {r.text}"
        token = r.json()["access_token"]
        tenant_id = r.json()["tenant_id"]
        headers = {"Authorization": f"Bearer {token}"}
        print(f"    [OK] Demo user: {DEMO_EMAIL} (tenant: {tenant_id})")

        # Create ICP configs
        icp_ids = []
        for icp in ICP_CONFIGS:
            r = await client.post("/api/v1/icp", json=icp, headers=headers)
            if r.status_code == 201:
                icp_ids.append(r.json()["id"])
                print(f"    [OK] ICP: {icp['name']}")

        if not icp_ids:
            print("    [FAIL] No ICP configs created — aborting")
            return

        # Create 3 completed runs
        for i, company in enumerate(COMPANIES):
            icp_id = icp_ids[i % len(icp_ids)]
            r = await client.post(
                "/api/v1/runs",
                json={
                    "icp_config_id": icp_id,
                    "max_companies": 10,
                    "trigger_keywords": ["funding", "hiring"],
                },
                headers=headers,
            )
            if r.status_code == 201:
                run_id = r.json()["id"]
                print(f"    [OK] Run created for {company['name']} (run_id: {run_id[:8]}...)")

        print(f"\n  [OK] Demo data seeded successfully!")
        print(f"\n  Login credentials:")
        print(f"    Email:    {DEMO_EMAIL}")
        print(f"    Password: {DEMO_PASSWORD}")
        print(f"\n  Access the UI: http://localhost:3000")
        print(f"  API Docs:       {API_BASE}/api/v1/docs\n")


if __name__ == "__main__":
    asyncio.run(seed())
