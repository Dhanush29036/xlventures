"""
app/api/routes/runs.py — Run management routes.

POST /runs   → create agent_run, dispatch PlannerAgent via Celery, return run_id
GET  /runs   → list runs (paginated, status filter)
GET  /runs/{run_id} → run detail + status + summary
DELETE /runs/{run_id} → cancel in-progress run
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Literal

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel

from app.api.auth import get_current_tenant
from app.memory.operational import AgentRun, AgentRunRepository, IcpConfigRepository

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/runs", tags=["runs"])


# ── Schemas ───────────────────────────────────────────────────────────────────


class CreateRunRequest(BaseModel):
    icp_config_id: str
    max_companies: int = 20
    trigger_keywords: list[str] = []
    company_domain: str | None = None
    selected_agents: list[str] | None = None

    model_config = {
        "json_schema_extra": {
            "example": {
                "icp_config_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
                "max_companies": 20,
                "trigger_keywords": ["Series B", "hiring engineers", "launched"],
                "company_domain": "tesla.com",
                "selected_agents": ["trigger_monitor", "icp_scorer", "summary"]
            }
        }
    }


class RunResponse(BaseModel):
    id: str
    tenant_id: str
    status: str
    plan_json: dict[str, Any] | None
    created_at: str
    completed_at: str | None
    summary: dict[str, Any] | None = None

    @classmethod
    def from_model(cls, obj: AgentRun) -> "RunResponse":
        return cls(
            id=str(obj.id),
            tenant_id=str(obj.tenant_id),
            status=obj.status,
            plan_json=obj.plan_json,
            created_at=obj.created_at.isoformat(),
            completed_at=obj.completed_at.isoformat() if obj.completed_at else None,
            summary=obj.plan_json.get("summary") if obj.plan_json else None,
        )


class RunListResponse(BaseModel):
    items: list[RunResponse]
    total: int
    page: int
    page_size: int


# ── Routes ────────────────────────────────────────────────────────────────────


@router.post("", response_model=RunResponse, status_code=201)
async def create_run(
    body: CreateRunRequest,
    request: Request,
    tenant_id: str = Depends(get_current_tenant),
) -> RunResponse:
    """
    Trigger a new discovery run.
    Creates agent_run row, dispatches PlannerAgent via Celery, returns run_id.
    """
    # Validate ICP config belongs to tenant
    icp_repo = IcpConfigRepository(request.app.state.session_factory)
    icp = await icp_repo.get(uuid.UUID(body.icp_config_id))
    if not icp or str(icp.tenant_id) != tenant_id:
        raise HTTPException(status_code=404, detail="ICP config not found")

    run_repo = AgentRunRepository(request.app.state.session_factory)
    plan = {
        "icp_config_id": body.icp_config_id,
        "max_companies": body.max_companies,
        "trigger_keywords": body.trigger_keywords,
        "company_domain": body.company_domain,
        "icp_rules": icp.rules_json,
        "icp_persona": icp.persona_json,
        "selected_agents": body.selected_agents,
        "force": True,
    }
    run = await run_repo.create(
        tenant_id=tenant_id,
        status="pending",
        plan_json=plan,
    )
    run_id = str(run.id)

    # Dispatch to Celery (fire-and-forget)
    try:
        from celery_config import celery_app
        celery_app.send_task(
            "app.tasks.run_pipeline",
            kwargs={
                "run_id": run_id,
                "tenant_id": tenant_id,
                "icp_config": plan,
                "selected_agents": body.selected_agents,
            },
            queue="enrichment",
            task_id=run_id,
        )
        logger.info("run_dispatched_to_celery", run_id=run_id)
    except Exception as exc:
        # If Celery is not running, execute inline (dev mode)
        logger.warning("celery_unavailable_running_inline", error=str(exc))
        run = await run_repo.update(run.id, status="running")

    logger.info("run_created", tenant_id=tenant_id, run_id=run_id)
    return RunResponse.from_model(run)  # type: ignore[arg-type]


@router.get("", response_model=RunListResponse)
async def list_runs(
    request: Request,
    tenant_id: str = Depends(get_current_tenant),
    status_filter: str | None = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> RunListResponse:
    """List all runs for the tenant, optionally filtered by status."""
    repo = AgentRunRepository(request.app.state.session_factory)
    filters: dict[str, Any] = {"tenant_id": tenant_id}
    if status_filter:
        filters["status"] = status_filter
    records = await repo.list_by(**filters)

    # Simple in-memory pagination
    start = (page - 1) * page_size
    paginated = records[start : start + page_size]
    return RunListResponse(
        items=[RunResponse.from_model(r) for r in paginated],
        total=len(records),
        page=page,
        page_size=page_size,
    )


@router.get("/{run_id}", response_model=RunResponse)
async def get_run(
    run_id: str,
    request: Request,
    tenant_id: str = Depends(get_current_tenant),
) -> RunResponse:
    """Get run detail + current status."""
    repo = AgentRunRepository(request.app.state.session_factory)
    run = await repo.get(uuid.UUID(run_id))
    if not run or str(run.tenant_id) != tenant_id:
        raise HTTPException(status_code=404, detail="Run not found")
    return RunResponse.from_model(run)


@router.delete("/{run_id}", status_code=204)
async def cancel_run(
    run_id: str,
    request: Request,
    tenant_id: str = Depends(get_current_tenant),
) -> None:
    """Cancel an in-progress run by revoking the Celery task."""
    repo = AgentRunRepository(request.app.state.session_factory)
    run = await repo.get(uuid.UUID(run_id))
    if not run or str(run.tenant_id) != tenant_id:
        raise HTTPException(status_code=404, detail="Run not found")
    if run.status not in ("pending", "running"):
        raise HTTPException(status_code=400, detail=f"Cannot cancel run with status '{run.status}'")

    try:
        from celery_config import celery_app
        celery_app.control.revoke(run_id, terminate=True)
    except Exception:
        pass

    await repo.update(
        uuid.UUID(run_id),
        status="cancelled",
        completed_at=datetime.now(timezone.utc),
    )
    logger.info("run_cancelled", run_id=run_id, tenant_id=tenant_id)
