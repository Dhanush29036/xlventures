"""
app/api/routes/hitl.py — Human-in-the-Loop review routes.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from app.api.auth import get_current_tenant
from app.memory.operational import HitlQueue, HitlQueueRepository

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/hitl", tags=["hitl"])


# ── Schemas ───────────────────────────────────────────────────────────────────


class HitlResponse(BaseModel):
    id: str
    run_id: str
    agent_name: str
    payload_json: dict[str, Any]
    status: str
    reviewer_id: str | None
    reviewed_at: str | None
    rejection_reason: str | None

    @classmethod
    def from_model(cls, obj: HitlQueue) -> "HitlResponse":
        return cls(
            id=str(obj.id),
            run_id=str(obj.run_id),
            agent_name=obj.agent_name,
            payload_json=obj.payload_json,
            status=obj.status,
            reviewer_id=obj.reviewer_id,
            reviewed_at=obj.reviewed_at.isoformat() if obj.reviewed_at else None,
            rejection_reason=obj.rejection_reason,
        )


class RejectRequest(BaseModel):
    reason: str


class EditApproveRequest(BaseModel):
    edited_payload: dict[str, Any]


# ── Routes ────────────────────────────────────────────────────────────────────


@router.get("", response_model=list[HitlResponse])
async def list_hitl(
    request: Request,
    tenant_id: str = Depends(get_current_tenant),
) -> list[HitlResponse]:
    """List all pending HITL items for the current tenant."""
    repo = HitlQueueRepository(request.app.state.session_factory)
    # Fetch all pending items — filter by tenant via run ownership
    items = await repo.list_by(status="pending")
    # Tenant isolation: only items where run belongs to this tenant
    results = []
    from app.memory.operational import AgentRunRepository
    run_repo = AgentRunRepository(request.app.state.session_factory)
    for item in items:
        run = await run_repo.get(item.run_id)
        if run and str(run.tenant_id) == tenant_id:
            results.append(HitlResponse.from_model(item))
    return results


@router.get("/{hitl_id}", response_model=HitlResponse)
async def get_hitl_item(
    hitl_id: str,
    request: Request,
    tenant_id: str = Depends(get_current_tenant),
) -> HitlResponse:
    """Get single HITL item with full payload."""
    item = await _get_and_verify(hitl_id, tenant_id, request)
    return HitlResponse.from_model(item)


@router.post("/{hitl_id}/approve", response_model=HitlResponse)
async def approve_hitl(
    hitl_id: str,
    request: Request,
    tenant_id: str = Depends(get_current_tenant),
) -> HitlResponse:
    """Approve a HITL item and resume the LangGraph graph execution."""
    item = await _get_and_verify(hitl_id, tenant_id, request)
    repo = HitlQueueRepository(request.app.state.session_factory)
    updated = await repo.update(
        item.id,
        status="approved",
        reviewer_id=tenant_id,
        reviewed_at=datetime.now(timezone.utc),
    )
    # Resume LangGraph execution
    await _resume_pipeline(str(item.run_id), item.payload_json, request)
    logger.info("hitl_approved", hitl_id=hitl_id, tenant_id=tenant_id)
    return HitlResponse.from_model(updated)  # type: ignore[arg-type]


@router.post("/{hitl_id}/reject", response_model=HitlResponse)
async def reject_hitl(
    hitl_id: str,
    body: RejectRequest,
    request: Request,
    tenant_id: str = Depends(get_current_tenant),
) -> HitlResponse:
    """Reject a HITL item with a reason, triggering replanning."""
    item = await _get_and_verify(hitl_id, tenant_id, request)
    repo = HitlQueueRepository(request.app.state.session_factory)
    updated = await repo.update(
        item.id,
        status="rejected",
        reviewer_id=tenant_id,
        reviewed_at=datetime.now(timezone.utc),
        rejection_reason=body.reason,
    )
    # Publish rejection event via SSE
    try:
        mm = request.app.state.memory_manager
        await mm._redis.save_run_summary(
            tenant_id=tenant_id,
            company_domain=item.payload_json.get("domain", ""),
            summary={"hitl_rejected": True, "reason": body.reason, "hitl_id": hitl_id},
        )
    except Exception:
        pass
    logger.info("hitl_rejected", hitl_id=hitl_id, reason=body.reason)
    return HitlResponse.from_model(updated)  # type: ignore[arg-type]


@router.post("/{hitl_id}/edit", response_model=HitlResponse)
async def edit_approve_hitl(
    hitl_id: str,
    body: EditApproveRequest,
    request: Request,
    tenant_id: str = Depends(get_current_tenant),
) -> HitlResponse:
    """Approve with edited payload — inject edits before resuming."""
    item = await _get_and_verify(hitl_id, tenant_id, request)
    repo = HitlQueueRepository(request.app.state.session_factory)
    # Merge original with edits
    merged_payload = {**item.payload_json, **body.edited_payload}
    updated = await repo.update(
        item.id,
        status="approved",
        payload_json=merged_payload,
        reviewer_id=tenant_id,
        reviewed_at=datetime.now(timezone.utc),
    )
    await _resume_pipeline(str(item.run_id), merged_payload, request)
    logger.info("hitl_edit_approved", hitl_id=hitl_id)
    return HitlResponse.from_model(updated)  # type: ignore[arg-type]


# ── Helpers ───────────────────────────────────────────────────────────────────


async def _get_and_verify(hitl_id: str, tenant_id: str, request: Request) -> HitlQueue:
    repo = HitlQueueRepository(request.app.state.session_factory)
    item = await repo.get(uuid.UUID(hitl_id))
    if not item:
        raise HTTPException(status_code=404, detail="HITL item not found")
    # Verify tenant owns the run
    from app.memory.operational import AgentRunRepository
    run_repo = AgentRunRepository(request.app.state.session_factory)
    run = await run_repo.get(item.run_id)
    if not run or str(run.tenant_id) != tenant_id:
        raise HTTPException(status_code=404, detail="HITL item not found")
    return item


async def _resume_pipeline(run_id: str, payload: dict[str, Any], request: Request) -> None:
    """Resume LangGraph pipeline after HITL approval."""
    try:
        planner = request.app.state.planner_agent
        if hasattr(planner, "resume_from_hitl"):
            await planner.resume_from_hitl(run_id=run_id, approved_payload=payload)
    except Exception as exc:
        logger.warning("hitl_resume_failed", run_id=run_id, error=str(exc))
