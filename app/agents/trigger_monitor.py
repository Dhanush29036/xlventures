"""
app/agents/trigger_monitor.py

Trigger Monitor Agent
─────────────────────
Responsibility: Detect and score buying signals for a target company.

Memory interactions
───────────────────
READ  → MM.get_company_context()   — loads prior signals from Neo4j + Redis
WRITE → MM._neo4j.add_signal()     — persists each new signal to the graph
WRITE → MM._redis.save_run_summary — saves trigger metadata to episodic store

Signal types detected (extensible)
───────────────────────────────────
  • funding_round   — recent funding event in company_data
  • hiring_surge    — headcount growth above threshold
  • tech_adoption   — new tech stack indicators in metadata
  • news_mention    — press/news items in metadata
  • job_posting     — open roles matching ICP persona titles
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from app.agents.base import BaseAgent
from app.agents.state import PlannerState, SignalModel


# Minimum signal score to trigger downstream pipeline
SIGNAL_SCORE_THRESHOLD = 0.3

# Weight per signal type  (signal_type → weight)
SIGNAL_WEIGHTS: dict[str, float] = {
    "funding_round": 0.90,
    "hiring_surge": 0.70,
    "job_posting": 0.50,
    "tech_adoption": 0.60,
    "news_mention": 0.40,
}


class TriggerMonitorAgent(BaseAgent):
    """
    Scans company_data and prior context for buying signals, scores them,
    persists to the knowledge graph, and updates the episodic store.
    """

    agent_name = "trigger_monitor"

    async def _execute(self, state: PlannerState) -> dict[str, Any]:
        log = self._log(state)
        company_data: dict[str, Any] = state.get("company_data", {})
        prior_context: dict[str, Any] = state.get("prior_context", {})
        domain: str = state.get("domain", "")
        tenant_id: str = state.get("tenant_id", "")
        run_id: str = state.get("run_id", str(uuid.uuid4()))

        # ── 1. Detect signals ─────────────────────────────────────────────────
        detected: list[SignalModel] = []

        # Funding round signal
        if company_data.get("latest_funding_date") or company_data.get(
            "funding_stage"
        ):
            detected.append(
                SignalModel(
                    type="funding_round",
                    occurred_at=_parse_date(company_data.get("latest_funding_date")),
                    data={
                        "stage": company_data.get("funding_stage", ""),
                        "amount_usd": company_data.get("latest_funding_amount_usd"),
                    },
                    score=SIGNAL_WEIGHTS["funding_round"],
                )
            )
            log.info("signal_detected", signal_type="funding_round")

        # Hiring surge signal — headcount growth > 10% vs prior run
        prior_headcount = _prior_headcount(prior_context)
        current_headcount = company_data.get("headcount", 0)
        if prior_headcount and current_headcount:
            growth_pct = (current_headcount - prior_headcount) / prior_headcount
            if growth_pct >= 0.10:
                detected.append(
                    SignalModel(
                        type="hiring_surge",
                        occurred_at=datetime.now(timezone.utc),
                        data={"growth_pct": round(growth_pct, 3), "current": current_headcount},
                        score=SIGNAL_WEIGHTS["hiring_surge"] * min(growth_pct, 1.0),
                    )
                )
                log.info("signal_detected", signal_type="hiring_surge", growth_pct=growth_pct)

        # Job posting signal
        if company_data.get("open_roles"):
            detected.append(
                SignalModel(
                    type="job_posting",
                    occurred_at=datetime.now(timezone.utc),
                    data={"roles": company_data["open_roles"]},
                    score=SIGNAL_WEIGHTS["job_posting"],
                )
            )
            log.info("signal_detected", signal_type="job_posting")

        # Tech adoption signal
        if company_data.get("tech_stack"):
            detected.append(
                SignalModel(
                    type="tech_adoption",
                    occurred_at=datetime.now(timezone.utc),
                    data={"stack": company_data["tech_stack"]},
                    score=SIGNAL_WEIGHTS["tech_adoption"],
                )
            )

        # News mention signal
        if company_data.get("recent_news"):
            detected.append(
                SignalModel(
                    type="news_mention",
                    occurred_at=datetime.now(timezone.utc),
                    data={"headlines": company_data["recent_news"]},
                    score=SIGNAL_WEIGHTS["news_mention"],
                )
            )

        # ── 2. Compute aggregate trigger score ────────────────────────────────
        trigger_score = (
            sum(s.score for s in detected) / len(detected) if detected else 0.0
        )
        trigger_score = round(min(trigger_score, 1.0), 4)
        log.info("trigger_score_computed", score=trigger_score, signals=len(detected))

        # ── 3. Persist signals to Neo4j knowledge graph ───────────────────────
        for signal in detected:
            await self._mm._neo4j.add_signal(
                company_domain=domain,
                signal_type=signal.type,
                signal_data=signal.data,
                occurred_at=signal.occurred_at,
            )

        # ── 4. Save trigger metadata to Redis episodic store ──────────────────
        await self._mm._redis.save_run_summary(
            tenant_id=tenant_id,
            company_domain=domain,
            summary={
                "agent": self.agent_name,
                "run_id": run_id,
                "signals_detected": len(detected),
                "trigger_score": trigger_score,
                "signal_types": [s.type for s in detected],
            },
        )

        return {
            "signals": [s.model_dump(mode="json") for s in detected],
            "trigger_score": trigger_score,
            "status": "running",
        }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_date(value: str | None) -> datetime:
    if value:
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            pass
    return datetime.now(timezone.utc)


def _prior_headcount(prior_context: dict[str, Any]) -> int | None:
    """Extract headcount from previous Neo4j graph data if available."""
    graph = prior_context.get("graph", {})
    company = graph.get("company", {})
    return company.get("headcount")
