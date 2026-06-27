"""
Agent pipeline routes
---------------------
Add to app/main.py:

    from app.agents.routes import router as agents_router
    app.include_router(agents_router)

Endpoints
─────────
POST /agents/pipeline/run          — run full pipeline (validation → persona → contact)
POST /agents/pipeline/approve      — approve HITL gate, re-run with human_approved=True
GET  /agents/pipeline/status/{run_id} — check run status from episodic memory

All routes use Depends(get_memory_manager) matching Dhanush's DI pattern.
"""

from __future__ import annotations

import uuid
from typing import Any, Optional

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.lifespan import get_memory_manager
from app.memory.manager import MemoryManager

# Import your 3 agents via pipeline
import sys, os
sys.path.insert(0, os.path.dirname(__file__))
from pipeline import run_agent_pipeline

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/agents", tags=["agents"])


# ── Request / Response models ─────────────────────────────────────────────────

class CompanyPayload(BaseModel):
    domain: str
    name: str
    industry: Optional[str] = None
    employee_count: Optional[int] = None
    funding_stage: Optional[str] = None
    hq_location: Optional[str] = None
    description: Optional[str] = None
    raw_text: Optional[str] = None


class PipelineRunRequest(BaseModel):
    tenant_id: str
    company: CompanyPayload
    run_id: Optional[uuid.UUID] = Field(default_factory=uuid.uuid4)


class PipelineApproveRequest(BaseModel):
    tenant_id: str
    company: CompanyPayload
    run_id: uuid.UUID      # must match the original run


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/pipeline/run")
async def run_pipeline(
    request: PipelineRunRequest,
    mm: MemoryManager = Depends(get_memory_manager),
) -> dict[str, Any]:
    """
    Run Validation → Persona Finder → Contact Enrichment for one company.

    First call always returns status="awaiting_human_approval" with a
    hitl_prompt the UI should surface to the user.

    If the company was already processed (Redis/Neo4j hit) returns
    status="skipped_duplicate" immediately.
    """
    logger.info(
        "pipeline_run_start",
        tenant_id=request.tenant_id,
        domain=request.company.domain,
        run_id=str(request.run_id),
    )

    result = await run_agent_pipeline(
        company_data=request.company.model_dump(),
        memory_manager=mm,
        tenant_id=request.tenant_id,
        human_approved=False,           # always False on first call
        run_id=request.run_id,
    )

    logger.info(
        "pipeline_run_complete",
        domain=request.company.domain,
        status=result.get("status"),
    )
    return result


@router.post("/pipeline/approve")
async def approve_pipeline(
    request: PipelineApproveRequest,
    mm: MemoryManager = Depends(get_memory_manager),
) -> dict[str, Any]:
    """
    Human-in-the-Loop approval endpoint.

    Call this after the user approves the persona recommendations.
    Re-runs the pipeline with human_approved=True, which triggers
    contact enrichment and persists everything to all 4 backends
    via memory_manager.record_company_enriched().

    Use the same run_id from the original /pipeline/run response so
    audit_log entries are grouped by the same UUID.
    """
    logger.info(
        "pipeline_approve_start",
        tenant_id=request.tenant_id,
        domain=request.company.domain,
        run_id=str(request.run_id),
    )

    result = await run_agent_pipeline(
        company_data=request.company.model_dump(),
        memory_manager=mm,
        tenant_id=request.tenant_id,
        human_approved=True,
        run_id=request.run_id,
    )

    if result.get("status") != "complete":
        raise HTTPException(
            status_code=422,
            detail=f"Pipeline did not complete: {result.get('status')}",
        )

    logger.info(
        "pipeline_approve_complete",
        domain=request.company.domain,
        contacts=len(result.get("contact", {}).get("contacts", [])),
        persisted=result.get("contact", {}).get("persisted_to_memory"),
    )
    return result


@router.get("/pipeline/context/{domain}")
async def pipeline_context(
    domain: str,
    tenant_id: str,
    mm: MemoryManager = Depends(get_memory_manager),
) -> dict[str, Any]:
    """
    Fetch all prior-run context for a domain before running the pipeline.
    Returns Redis episodic runs + Neo4j graph (company + people + signals).
    Useful for the Planner Agent to check what's already known.
    """
    return await mm.get_company_context(tenant_id=tenant_id, domain=domain)
