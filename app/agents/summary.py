"""
app/agents/summary.py

Summary Agent
─────────────
Responsibility: Generate the final run summary and persist it to Redis
episodic store so the Planner Agent can use it as prior context on the
next run for the same company.

Memory interactions
───────────────────
WRITE → MM._redis.save_run_summary()    — saves summary to episodic List
WRITE → MM._pg (AuditLogRepository)    — marks run as completed in audit log
READ  → state (all prior agent outputs)

Recommended action logic
─────────────────────────
  icp_score >= 0.80 AND validation_passed AND contacts ≥ 1  → "outreach"
  icp_score >= 0.50 AND hitl_cleared                        → "nurture"
  icp_score <  0.50 OR  hard validation failure             → "disqualify"
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from app.agents.base import BaseAgent
from app.agents.state import PlannerState, RunSummaryModel
from app.memory.operational import AgentRunRepository, AuditLogRepository


class SummaryAgent(BaseAgent):
    """
    Synthesises all agent outputs into a structured summary, determines the
    recommended sales action, persists to Redis episodic store, and marks
    the Postgres agent_run as completed.
    """

    agent_name = "summary"

    async def _execute(self, state: PlannerState) -> dict[str, Any]:
        log = self._log(state)
        tenant_id: str = state.get("tenant_id", "")
        domain: str = state.get("domain", "")
        run_id_str: str = state.get("run_id", str(uuid.uuid4()))

        try:
            run_id = uuid.UUID(run_id_str)
        except ValueError:
            run_id = uuid.uuid4()

        icp_score: float = state.get("icp_score", 0.0)
        trigger_score: float = state.get("trigger_score", 0.0)
        validation_passed: bool = state.get("validation_passed", False)
        hitl_required: bool = state.get("hitl_required", False)
        people: list[dict] = state.get("people", [])
        enriched_contacts: list[dict] = state.get("enriched_contacts", [])
        signals: list[dict] = state.get("signals", [])
        icp_matched_rules: list[str] = state.get("icp_matched_rules", [])
        quality_score: float = state.get("data_quality_score", 0.0)

        # ── 1. Determine recommended action ────────────────────────────────────
        decision_makers = [
            p.get("email", "") for p in people if p.get("is_decision_maker")
        ]

        if icp_score >= 0.80 and validation_passed and len(enriched_contacts) >= 1:
            recommended_action = "outreach"
        elif icp_score >= 0.50 and not hitl_required:
            recommended_action = "nurture"
        else:
            recommended_action = "disqualify"

        log.info("recommended_action_determined", action=recommended_action, icp_score=icp_score)

        # ── 2. Build structured summary ────────────────────────────────────────
        summary_model = RunSummaryModel(
            run_id=str(run_id),
            tenant_id=tenant_id,
            domain=domain,
            icp_score=icp_score,
            contacts_found=len(enriched_contacts),
            signals_detected=len(signals),
            decision_makers=decision_makers,
            recommended_action=recommended_action,
            generated_at=datetime.now(timezone.utc),
        )

        summary_dict = summary_model.model_dump(mode="json")

        # Enrich with additional context for the Planner Agent's next run
        summary_dict.update(
            {
                "trigger_score": trigger_score,
                "validation_passed": validation_passed,
                "icp_matched_rules": icp_matched_rules,
                "data_quality_score": quality_score,
                "signal_types": [s.get("type") for s in signals],
            }
        )

        # ── 3. Persist to Redis episodic store ─────────────────────────────────
        await self._mm._redis.save_run_summary(
            tenant_id=tenant_id,
            company_domain=domain,
            summary=summary_dict,
        )
        log.info("summary_saved_to_redis", domain=domain)

        # ── 4. Mark agent_run as completed in Postgres ─────────────────────────
        run_repo = AgentRunRepository(self._mm._pg)
        await run_repo.update(
            run_id,
            status="completed",
            completed_at=datetime.now(timezone.utc),
        )

        # ── 5. Append final audit event ────────────────────────────────────────
        audit_repo = AuditLogRepository(self._mm._pg)
        await audit_repo.append(
            run_id=run_id,
            agent_name=self.agent_name,
            event_type="run_completed",
            details={
                "recommended_action": recommended_action,
                "icp_score": icp_score,
                "contacts_found": len(enriched_contacts),
                "signals_detected": len(signals),
            },
        )

        log.info(
            "summary_complete",
            action=recommended_action,
            contacts=len(enriched_contacts),
            signals=len(signals),
        )

        return {
            "summary": summary_dict,
            "recommended_action": recommended_action,
            "status": "completed",
        }
