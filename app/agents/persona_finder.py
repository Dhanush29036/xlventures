"""
app/agents/persona_finder.py

Persona Finder Agent
────────────────────
Responsibility: Identify buyer personas from people data and ICP persona
configuration.  Classifies people by seniority/role fit and marks decision
makers.  Writes every person into the Neo4j knowledge graph.

Memory interactions
───────────────────
READ  → state (people, icp_config.persona_json)
READ  → MM._neo4j.get_company_with_people() — existing people from graph
WRITE → MM._neo4j.upsert_person()           — upsert each person node
WRITE → MM._neo4j.link_reports_to()         — builds org hierarchy links
"""

from __future__ import annotations

from typing import Any

from app.agents.base import BaseAgent
from app.agents.state import PersonModel, PlannerState

# Seniority tiers in descending decision-making weight
SENIORITY_TIERS: dict[str, list[str]] = {
    "C-Suite": ["ceo", "cto", "cfo", "coo", "cpo", "ciso", "founder", "co-founder"],
    "VP": ["vp", "vice president"],
    "Director": ["director", "head of"],
    "Manager": ["manager", "lead"],
    "IC": [],  # catch-all
}

# Roles that map to decision maker status in B2B SaaS
DECISION_MAKER_TITLES = {"C-Suite", "VP", "Director"}


def _classify_seniority(title: str) -> str:
    title_lower = title.lower()
    for tier, keywords in SENIORITY_TIERS.items():
        if any(kw in title_lower for kw in keywords):
            return tier
    return "IC"


class PersonaFinderAgent(BaseAgent):
    """
    Classifies people by persona fit against ICP persona_json config,
    marks decision makers, and persists the org structure to Neo4j.
    """

    agent_name = "persona_finder"

    async def _execute(self, state: PlannerState) -> dict[str, Any]:
        log = self._log(state)
        domain: str = state.get("domain", "")
        icp_config: dict[str, Any] = state.get("icp_config", {})
        raw_people: list[dict[str, Any]] = state.get("people", [])

        # Load persona configuration from ICP config
        persona_config: dict[str, Any] = icp_config.get("persona_json") or {}
        target_titles: list[str] = [
            t.lower() for t in persona_config.get("target_titles", [])
        ]
        target_seniorities: list[str] = persona_config.get(
            "target_seniorities", list(DECISION_MAKER_TITLES)
        )

        # ── 1. Load existing people from Neo4j graph (to avoid re-upserts) ────
        existing_graph = await self._mm._neo4j.get_company_with_people(domain)
        existing_emails = {
            p.get("email", "") for p in existing_graph.get("people", [])
        }
        log.info("existing_people_in_graph", count=len(existing_emails))

        # ── 2. Classify and enrich people from state ───────────────────────────
        classified: list[PersonModel] = []
        target_personas: list[dict[str, Any]] = []

        for raw in raw_people:
            email = raw.get("email", "")
            if not email:
                continue

            title = raw.get("title", "")
            seniority = _classify_seniority(title)
            is_dm = seniority in target_seniorities

            # Check if this person's title matches any target ICP persona title
            is_persona_match = any(kw in title.lower() for kw in target_titles) if target_titles else is_dm

            person = PersonModel(
                email=email,
                name=raw.get("name", ""),
                title=title,
                company_domain=domain,
                seniority=seniority,
                is_decision_maker=is_dm,
                linkedin_url=raw.get("linkedin_url"),
                metadata={k: v for k, v in raw.items() if k not in {"email", "name", "title"}},
            )
            classified.append(person)

            if is_persona_match:
                target_personas.append(
                    {
                        **person.model_dump(mode="json"),
                        "persona_match_reason": f"seniority={seniority}",
                    }
                )

            # ── 3. Upsert into Neo4j ───────────────────────────────────────────
            await self._mm._neo4j.upsert_person(
                email=email,
                name=person.name,
                title=title,
                company_domain=domain,
                metadata={
                    "seniority": seniority,
                    "is_decision_maker": is_dm,
                    "linkedin_url": person.linkedin_url or "",
                },
            )

        # ── 4. Build REPORTS_TO relationships ─────────────────────────────────
        # Link ICs and Managers to the first VP/C-suite found (simplified org tree)
        leaders = [p for p in classified if p.seniority in ("C-Suite", "VP")]
        reports = [p for p in classified if p.seniority in ("Manager", "IC")]
        if leaders and reports:
            top_leader = leaders[0]
            for report in reports:
                await self._mm._neo4j.link_reports_to(
                    subordinate_email=report.email,
                    manager_email=top_leader.email,
                )

        log.info(
            "persona_finder_complete",
            people_classified=len(classified),
            target_personas=len(target_personas),
            decision_makers=sum(1 for p in classified if p.is_decision_maker),
        )

        return {
            "people": [p.model_dump(mode="json") for p in classified],
            "target_personas": target_personas,
            "status": "running",
        }
