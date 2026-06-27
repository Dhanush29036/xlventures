"""
Agent Pipeline Runner
---------------------
Connects Validation → Persona Finder → Contact Enrichment in sequence.
Plugs into Dhanush's LangGraph Planner via run_agent_pipeline().

The Planner Agent calls this function. It handles:
- Memory skip-check (dedup via Redis/Neo4j)
- Sequential agent execution
- Human-in-the-Loop approval gate before contact enrichment
- Final payload passed to Summary Agent

Wire this into the Planner's LangGraph node like:
    workflow.add_node("validation_persona_contact", run_agent_pipeline)
"""

import logging
from typing import Optional

from validation_agent import CompanyInput, run_validation_agent, validation_result_to_dict
from persona_finder_agent import run_persona_finder, persona_result_to_dict
from contact_enrichment_agent import run_contact_enrichment, contact_result_to_dict

logger = logging.getLogger(__name__)


async def run_agent_pipeline(
    company_data: dict,
    memory_manager=None,
    tenant_id: str = "default",
    human_approved: bool = False,   # Planner sets True after HITL approval
) -> dict:
    """
    Full pipeline: Validation → Persona Finder → Contact Enrichment.

    Args:
        company_data:    dict with keys matching CompanyInput fields
        memory_manager:  MemoryManager instance from Dhanush's layer
        tenant_id:       tenant scoping key
        human_approved:  must be True for contact enrichment to run + persist

    Returns:
        dict with keys: validation, persona, contact, status
    """

    # ── Parse input ───────────────────────────────────────────────────────────
    company = CompanyInput(
        domain=company_data.get("domain", ""),
        name=company_data.get("name", "Unknown"),
        industry=company_data.get("industry"),
        employee_count=company_data.get("employee_count"),
        funding_stage=company_data.get("funding_stage"),
        hq_location=company_data.get("hq_location"),
        description=company_data.get("description"),
        raw_text=company_data.get("raw_text"),
    )

    output = {"domain": company.domain, "status": "ok"}

    # ── Stage 1: Validation ───────────────────────────────────────────────────
    logger.info(f"[Pipeline] Stage 1 — Validation: {company.domain}")
    validation = await run_validation_agent(
        company=company,
        memory_manager=memory_manager,
        tenant_id=tenant_id,
    )
    output["validation"] = validation_result_to_dict(validation)

    if validation.skipped:
        output["status"] = "skipped_duplicate"
        logger.info(f"[Pipeline] {company.domain} was a duplicate — stopping pipeline")
        return output

    if validation.verdict == "INVALID":
        output["status"] = "invalid_company"
        logger.info(f"[Pipeline] {company.domain} failed validation — stopping pipeline")
        return output

    # ── Stage 2: Persona Finder ───────────────────────────────────────────────
    logger.info(f"[Pipeline] Stage 2 — Persona Finder: {company.domain}")
    persona = await run_persona_finder(
        company=company,
        validation=validation,
        memory_manager=memory_manager,
        tenant_id=tenant_id,
    )
    output["persona"] = persona_result_to_dict(persona)

    if not persona.personas:
        output["status"] = "no_personas_found"
        logger.info(f"[Pipeline] No personas for {company.domain} — stopping pipeline")
        return output

    # ── HITL gate ─────────────────────────────────────────────────────────────
    if not human_approved:
        output["status"] = "awaiting_human_approval"
        output["hitl_prompt"] = (
            f"Found {len(persona.personas)} personas at {company.name} "
            f"(ICP score: {persona.icp_match_score}/100). "
            f"Approve contact enrichment?"
        )
        logger.info(f"[Pipeline] Waiting for human approval on {company.domain}")
        return output

    # ── Stage 3: Contact Enrichment ───────────────────────────────────────────
    logger.info(f"[Pipeline] Stage 3 — Contact Enrichment: {company.domain}")
    contact = await run_contact_enrichment(
        company=company,
        persona_result=persona,
        validation_result=validation,
        memory_manager=memory_manager,
        tenant_id=tenant_id,
        human_approved=human_approved,
    )
    output["contact"] = contact_result_to_dict(contact)
    output["status"] = "complete"

    return output
