"""
app/agents/contact_enrichment.py

Contact Enrichment Agent
─────────────────────────
Responsibility: The core write agent — merges all collected data and
calls ``MemoryManager.record_company_enriched()`` which persists to all
four stores in parallel (Neo4j graph, Qdrant vectors, Redis episodic,
Postgres audit log).

Memory interactions
───────────────────
WRITE → MM.record_company_enriched()   — fan-out write to ALL 4 stores:
          • Neo4j  : upsert Company, Person nodes, signals, TARGETS link
          • Qdrant : upsert company embedding (OpenAI text-embedding-3-small)
          • Redis  : mark processed + save run summary
          • Postgres: append audit_log entry

READ  → state (all prior agent outputs)

Data quality scoring
─────────────────────
Computes a simple 0-1 quality score based on completeness of key fields
(name, domain, headcount, funding_stage, at least one contact with email).
"""

from __future__ import annotations

import uuid
from typing import Any

from app.agents.base import BaseAgent
from app.agents.state import EnrichmentResultModel, PersonModel, PlannerState

# Field completeness weights for data quality score
_QUALITY_FIELDS: list[tuple[str, float]] = [
    ("name", 0.20),
    ("description", 0.15),
    ("headcount", 0.15),
    ("funding_stage", 0.15),
    ("industry", 0.10),
    ("hq_country", 0.10),
    ("annual_revenue_usd", 0.10),
    ("tech_stack", 0.05),
]


def _compute_quality(company_data: dict[str, Any], contacts: list[dict]) -> float:
    score = 0.0
    for field, weight in _QUALITY_FIELDS:
        if company_data.get(field):
            score += weight
    # Bonus for having at least one contact with email
    if any(c.get("email") for c in contacts):
        score += 0.10
    return round(min(score, 1.0), 4)


class ContactEnrichmentAgent(BaseAgent):
    """
    Aggregates all pipeline data and triggers the unified MM write fan-out.
    Also computes a data quality score that Validation uses.
    """

    agent_name = "contact_enrichment"

    async def _execute(self, state: PlannerState) -> dict[str, Any]:
        log = self._log(state)
        tenant_id: str = state.get("tenant_id", "")
        domain: str = state.get("domain", "")
        run_id_str: str = state.get("run_id", str(uuid.uuid4()))

        try:
            run_id = uuid.UUID(run_id_str)
        except ValueError:
            run_id = uuid.uuid4()

        company_data: dict[str, Any] = state.get("company_data", {})
        people: list[dict[str, Any]] = state.get("people", [])
        signals: list[dict[str, Any]] = state.get("signals", [])

        # ── 1. Validate people have required fields ────────────────────────────
        enriched_contacts: list[dict[str, Any]] = []
        for raw in people:
            email = raw.get("email", "")
            if not email:
                log.warning("contact_missing_email", name=raw.get("name"))
                continue
            enriched_contacts.append(raw)

        # ── 2. Compute data quality score ──────────────────────────────────────
        quality_score = _compute_quality(company_data, enriched_contacts)
        log.info("data_quality_computed", score=quality_score, contacts=len(enriched_contacts))

        # ── 3. Fan-out write to all 4 stores via MemoryManager ─────────────────
        await self._mm.record_company_enriched(
            tenant_id=tenant_id,
            domain=domain,
            company_data=company_data,
            people=enriched_contacts,
            signals=signals,
            run_id=run_id,
        )

        result = EnrichmentResultModel(
            enriched_contacts=[PersonModel(**c) for c in enriched_contacts if c.get("email")],
            contacts_found=len(enriched_contacts),
            data_quality_score=quality_score,
        )

        log.info(
            "contact_enrichment_complete",
            contacts_found=result.contacts_found,
            quality_score=quality_score,
        )

        return {
            "enriched_contacts": [c.model_dump(mode="json") for c in result.enriched_contacts],
            "data_quality_score": result.data_quality_score,
            "status": "running",
        }
