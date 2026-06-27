"""
app/agents/icp_scorer.py

ICP Scorer Agent
────────────────
Responsibility: Score a target company against the tenant's ICP rules.

Memory interactions
───────────────────
READ  → MM.find_icp_candidates()         — Qdrant semantic + Neo4j structural filter
READ  → MM._pg (IcpConfigRepository)    — loads active ICP rules from Postgres
READ  → MM.get_company_context()        — uses prior_context already in state

Scoring algorithm
─────────────────
1. Load active ICP rules from Postgres (icp_configs table).
2. Evaluate each rule against company_data.
3. Combine rule score (0-1) with the semantic similarity score from Qdrant
   (already in prior state via find_icp_candidates upstream call).
4. Compute weighted final score and populate icp_score, icp_is_match fields.
"""

from __future__ import annotations

from typing import Any

from app.agents.base import BaseAgent
from app.agents.state import IcpScoreModel, PlannerState
from app.memory.operational import IcpConfigRepository


# Weight split between rule-based and semantic scoring
RULE_WEIGHT = 0.60
SEMANTIC_WEIGHT = 0.40

# Company must score above this to be considered an ICP match
ICP_MATCH_THRESHOLD = 0.65


class IcpScorerAgent(BaseAgent):
    """
    Evaluates a company against the tenant's ICP using both rule-based logic
    (from Postgres) and semantic similarity (from Qdrant via MemoryManager).
    """

    agent_name = "icp_scorer"

    async def _execute(self, state: PlannerState) -> dict[str, Any]:
        log = self._log(state)
        tenant_id: str = state.get("tenant_id", "")
        company_data: dict[str, Any] = state.get("company_data", {})
        icp_config: dict[str, Any] = state.get("icp_config", {})

        # ── 1. Load active ICP configs from Postgres ──────────────────────────
        icp_repo = IcpConfigRepository(self._mm._pg)
        active_configs = await icp_repo.get_active_for_tenant(tenant_id)

        # Merge rules: use state icp_config rules first, then DB fallback
        rules: dict[str, Any] = icp_config.get("rules_json") or {}
        if not rules and active_configs:
            rules = active_configs[0].rules_json or {}
            log.info("icp_rules_loaded_from_db", config_id=str(active_configs[0].id))

        if not rules:
            log.warning("no_icp_rules_found", tenant_id=tenant_id)
            return {
                "icp_score": 0.0,
                "icp_matched_rules": [],
                "icp_is_match": False,
                "status": "running",
            }

        # ── 2. Evaluate rules ──────────────────────────────────────────────────
        matched: list[str] = []
        disqualified: list[str] = []
        total_rules = 0

        # Headcount rule
        if "min_headcount" in rules or "max_headcount" in rules:
            total_rules += 1
            hc = company_data.get("headcount", 0)
            min_hc = rules.get("min_headcount", 0)
            max_hc = rules.get("max_headcount", 1_000_000)
            if min_hc <= hc <= max_hc:
                matched.append(f"headcount_in_range ({hc})")
            else:
                disqualified.append(f"headcount_out_of_range ({hc})")

        # Funding stage rule
        if "funding_stages" in rules:
            total_rules += 1
            stage = company_data.get("funding_stage", "")
            if stage in rules["funding_stages"]:
                matched.append(f"funding_stage_match ({stage})")
            else:
                disqualified.append(f"funding_stage_mismatch ({stage})")

        # Industry rule
        if "industries" in rules:
            total_rules += 1
            industry = company_data.get("industry", "")
            if industry in rules["industries"]:
                matched.append(f"industry_match ({industry})")
            else:
                disqualified.append(f"industry_mismatch ({industry})")

        # Geography rule
        if "hq_countries" in rules:
            total_rules += 1
            country = company_data.get("hq_country", "")
            if country in rules["hq_countries"]:
                matched.append(f"geography_match ({country})")
            else:
                disqualified.append(f"geography_mismatch ({country})")

        # Revenue rule
        if "min_revenue_usd" in rules:
            total_rules += 1
            revenue = company_data.get("annual_revenue_usd", 0) or 0
            if revenue >= rules["min_revenue_usd"]:
                matched.append(f"revenue_above_min ({revenue})")
            else:
                disqualified.append(f"revenue_below_min ({revenue})")

        rule_score = (len(matched) / total_rules) if total_rules > 0 else 0.0

        # ── 3. Retrieve semantic score from prior Qdrant results ───────────────
        # The semantic score for this domain may have been computed by the planner
        # during find_icp_candidates and stored in the company_data context.
        semantic_score: float = float(
            company_data.get("semantic_score") or icp_config.get("semantic_score") or 0.0
        )

        # ── 4. Compute weighted final score ────────────────────────────────────
        final_score = round(
            (rule_score * RULE_WEIGHT) + (semantic_score * SEMANTIC_WEIGHT), 4
        )
        is_match = final_score >= ICP_MATCH_THRESHOLD

        result = IcpScoreModel(
            score=final_score,
            matched_rules=matched,
            disqualifying_rules=disqualified,
            is_match=is_match,
        )

        log.info(
            "icp_score_computed",
            score=final_score,
            is_match=is_match,
            matched=len(matched),
            disqualified=len(disqualified),
        )

        return {
            "icp_score": result.score,
            "icp_matched_rules": result.matched_rules,
            "icp_is_match": result.is_match,
            "status": "running",
        }
