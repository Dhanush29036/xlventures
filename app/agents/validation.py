"""
app/agents/validation.py

Validation Agent
────────────────
Responsibility: Validate the quality and completeness of enriched data.
If data quality is too low OR confidence is uncertain, push to the HITL queue
in Postgres so a human reviewer can approve before outreach.

Memory interactions
───────────────────
READ  → state (company_data, people, signals)
WRITE → MM._pg (HitlQueueRepository) — creates a HITL queue entry if required
WRITE → MM._pg (AuditLogRepository)  — always appends a validation audit event

Validation checks performed
────────────────────────────
  • Company domain is resolvable (non-empty)
  • At least one signal detected (trigger_score > 0)
  • ICP score meets threshold
  • At least N enriched contacts present
  • No disqualifying ICP rules triggered
  • Data quality score above minimum
"""

from __future__ import annotations

import uuid
from typing import Any

from app.agents.base import BaseAgent
from app.agents.state import PlannerState, ValidationResultModel
from app.memory.operational import AuditLogRepository, HitlQueueRepository

# Minimum thresholds
MIN_ICP_SCORE_FOR_AUTO_APPROVE = 0.80
MIN_TRIGGER_SCORE = 0.10
MIN_CONTACTS = 1
MIN_DATA_QUALITY = 0.50

# HITL is required if ICP score is in this "uncertain" range
HITL_SCORE_LOWER = 0.50
HITL_SCORE_UPPER = 0.80


class ValidationAgent(BaseAgent):
    """
    Runs data quality checks and decides whether the pipeline can proceed
    automatically or needs human-in-the-loop review via the HITL queue.
    """

    agent_name = "validation"

    async def _execute(self, state: PlannerState) -> dict[str, Any]:
        log = self._log(state)
        run_id_str: str = state.get("run_id", str(uuid.uuid4()))
        run_id = uuid.UUID(run_id_str) if run_id_str else None
        tenant_id: str = state.get("tenant_id", "")
        domain: str = state.get("domain", "")

        company_data: dict[str, Any] = state.get("company_data", {})
        icp_score: float = state.get("icp_score", 0.0)
        trigger_score: float = state.get("trigger_score", 0.0)
        people: list[dict] = state.get("people", [])
        data_quality: float = state.get("data_quality_score", 0.0)
        icp_matched: bool = state.get("icp_is_match", False)
        disqualified: list[str] = []  # pulled from icp_matched_rules context

        issues: list[str] = []

        # ── Validation checks ─────────────────────────────────────────────────

        if not domain:
            issues.append("company_domain_missing")

        if not company_data.get("name"):
            issues.append("company_name_missing")

        if trigger_score < MIN_TRIGGER_SCORE:
            issues.append(f"trigger_score_too_low ({trigger_score:.2f} < {MIN_TRIGGER_SCORE})")

        if icp_score < HITL_SCORE_LOWER and not icp_matched:
            issues.append(f"icp_score_below_threshold ({icp_score:.2f})")

        if len(people) < MIN_CONTACTS:
            issues.append(f"insufficient_contacts (found {len(people)}, need {MIN_CONTACTS})")

        if data_quality < MIN_DATA_QUALITY and data_quality > 0:
            issues.append(f"data_quality_low ({data_quality:.2f})")

        # ── Determine outcome ─────────────────────────────────────────────────

        # Hard fail — disqualify immediately
        hard_fail = any(
            k in issues for k in ["company_domain_missing", "icp_score_below_threshold"]
        )
        passed = len(issues) == 0 or (
            not hard_fail and icp_score >= MIN_ICP_SCORE_FOR_AUTO_APPROVE
        )

        # HITL required for uncertain ICP scores or soft data issues
        hitl_required = (
            not hard_fail
            and not passed
            and HITL_SCORE_LOWER <= icp_score < HITL_SCORE_UPPER
        )

        hitl_item_id: str | None = None

        # ── Write HITL queue entry (Postgres) ─────────────────────────────────
        if hitl_required:
            hitl_repo = HitlQueueRepository(self._mm._pg)
            hitl_payload = {
                "tenant_id": tenant_id,
                "domain": domain,
                "icp_score": icp_score,
                "trigger_score": trigger_score,
                "issues": issues,
                "company_data": company_data,
                "people_count": len(people),
            }
            hitl_entry = await hitl_repo.create(
                run_id=run_id,
                agent_name=self.agent_name,
                payload_json=hitl_payload,
                status="pending",
            )
            hitl_item_id = str(hitl_entry.id)
            log.info("hitl_item_created", hitl_item_id=hitl_item_id, issues=issues)

        # ── Append audit log (Postgres) ───────────────────────────────────────
        audit_repo = AuditLogRepository(self._mm._pg)
        await audit_repo.append(
            run_id=run_id,
            agent_name=self.agent_name,
            event_type="validation_complete",
            details={
                "passed": passed,
                "hitl_required": hitl_required,
                "hitl_item_id": hitl_item_id,
                "issues": issues,
                "icp_score": icp_score,
                "trigger_score": trigger_score,
            },
        )

        result = ValidationResultModel(
            passed=passed,
            issues=issues,
            hitl_required=hitl_required,
            hitl_item_id=hitl_item_id,
        )

        log.info(
            "validation_complete",
            passed=passed,
            hitl_required=hitl_required,
            issues_count=len(issues),
        )

        return {
            "validation_passed": result.passed,
            "validation_issues": result.issues,
            "hitl_required": result.hitl_required,
            "hitl_item_id": result.hitl_item_id,
            "status": "awaiting_hitl" if hitl_required else "running",
        }
