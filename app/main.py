"""
FastAPI application entry point.

Run with:
    uvicorn app.main:app --reload
"""

from __future__ import annotations

import structlog
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.agents.planner import PlannerAgent
from app.agents.state import CompanyModel  # noqa: F401 — available for consumers
from app.core.config import get_settings
from app.core.lifespan import get_memory_manager, lifespan
from app.memory.manager import HealthChecker, MemoryManager

logger = structlog.get_logger(__name__)
settings = get_settings()

app = FastAPI(
    title="XL Ventures — Agentic Prospect Intelligence",
    description="Memory & Data Layer for B2B prospect intelligence platform",
    version="1.0.0",
    lifespan=lifespan,
)


# ---------------------------------------------------------------------------
# Health endpoint
# ---------------------------------------------------------------------------


@app.get("/health", tags=["ops"])
async def health(
    mm: MemoryManager = Depends(get_memory_manager),
) -> JSONResponse:
    """
    Ping all four backend stores and return aggregate health.

    Returns 200 if all stores are healthy, 503 if any store is down.
    """
    checker = HealthChecker(mm)
    result = await checker.check()
    status_code = 200 if result["status"] == "healthy" else 503
    return JSONResponse(content=result, status_code=status_code)


# ---------------------------------------------------------------------------
# Memory query routes (used by agents and API consumers)
# ---------------------------------------------------------------------------


@app.get("/company/{domain}/context", tags=["memory"])
async def company_context(
    domain: str,
    tenant_id: str,
    mm: MemoryManager = Depends(get_memory_manager),
) -> dict:
    """Return prior-run context for a company — used by Planner Agent."""
    return await mm.get_company_context(tenant_id=tenant_id, domain=domain)


@app.get("/company/{domain}/skip", tags=["memory"])
async def should_skip(
    domain: str,
    tenant_id: str,
    mm: MemoryManager = Depends(get_memory_manager),
) -> dict:
    """Check whether this company should be skipped (already processed)."""
    skip = await mm.should_skip_company(tenant_id=tenant_id, domain=domain)
    return {"domain": domain, "should_skip": skip}


@app.post("/icp/candidates", tags=["memory"])
async def icp_candidates(
    tenant_id: str,
    icp_config: dict,
    mm: MemoryManager = Depends(get_memory_manager),
) -> list:
    """Find ICP-matching companies via semantic + graph + dedup pipeline."""
    return await mm.find_icp_candidates(tenant_id=tenant_id, icp_config=icp_config)


# ---------------------------------------------------------------------------
# Planner Agent dependency
# ---------------------------------------------------------------------------


def get_planner_agent(request: Request) -> PlannerAgent:
    """
    FastAPI dependency — inject the compiled LangGraph PlannerAgent.

    Usage::

        @router.post("/pipeline/run")
        async def run(planner: PlannerAgent = Depends(get_planner_agent)):
            ...
    """
    return request.app.state.planner_agent


# ---------------------------------------------------------------------------
# Pipeline trigger route
# ---------------------------------------------------------------------------


class PipelineRunRequest(BaseModel):
    """Request body for triggering the full enrichment pipeline."""

    tenant_id: str
    domain: str
    company_data: dict
    icp_config: dict
    people: list[dict] = []


@app.post("/pipeline/run", tags=["agents"])
async def run_pipeline(
    body: PipelineRunRequest,
    planner: PlannerAgent = Depends(get_planner_agent),
) -> dict:
    """
    Trigger the full LangGraph enrichment pipeline for one company.

    Orchestrates:
      check_skip → TriggerMonitor → ICPScorer → ContactEnrichment
      → PersonaFinder → Validation → Summary

    Returns the final PlannerState dict including:
      - ``recommended_action``: "outreach" | "nurture" | "disqualify"
      - ``status``:             "completed" | "skipped" | "awaiting_hitl" | "failed"
      - ``summary``:            Full RunSummaryModel dict
    """
    try:
        final_state = await planner.run(
            tenant_id=body.tenant_id,
            domain=body.domain,
            company_data=body.company_data,
            icp_config=body.icp_config,
            people=body.people,
        )
        return final_state
    except Exception as exc:
        logger.exception("pipeline_run_failed", domain=body.domain, error=str(exc))
        raise HTTPException(status_code=500, detail=str(exc))
