"""
app/api/routes/icp.py — ICP Config CRUD.

All routes are tenant-scoped via the JWT.
"""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel

from app.api.auth import get_current_tenant
from app.memory.operational import IcpConfig, IcpConfigRepository

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/icp", tags=["icp"])


# ── Schemas ───────────────────────────────────────────────────────────────────


class IcpCreateRequest(BaseModel):
    name: str
    rules_json: dict[str, Any]
    persona_json: dict[str, Any] | None = None

    model_config = {
        "json_schema_extra": {
            "example": {
                "name": "SaaS Mid-Market Engineering",
                "rules_json": {
                    "min_headcount": 50,
                    "max_headcount": 500,
                    "funding_stages": ["Series A", "Series B"],
                    "industries": ["SaaS", "Cloud Infrastructure"],
                },
                "persona_json": {
                    "target_titles": ["CTO", "VP Engineering", "Head of Engineering"],
                    "target_seniorities": ["C-Suite", "VP"],
                },
            }
        }
    }


class IcpUpdateRequest(BaseModel):
    name: str | None = None
    rules_json: dict[str, Any] | None = None
    persona_json: dict[str, Any] | None = None
    is_active: bool | None = None


class IcpResponse(BaseModel):
    id: str
    tenant_id: str
    name: str
    rules_json: dict[str, Any]
    persona_json: dict[str, Any] | None
    is_active: bool

    @classmethod
    def from_model(cls, obj: IcpConfig) -> "IcpResponse":
        return cls(
            id=str(obj.id),
            tenant_id=str(obj.tenant_id),
            name=obj.name,
            rules_json=obj.rules_json,
            persona_json=obj.persona_json,
            is_active=obj.is_active,
        )


# ── Routes ────────────────────────────────────────────────────────────────────


@router.post("", response_model=IcpResponse, status_code=201)
async def create_icp(
    body: IcpCreateRequest,
    request: Request,
    tenant_id: str = Depends(get_current_tenant),
) -> IcpResponse:
    """Create a new ICP config for the current tenant."""
    repo = IcpConfigRepository(request.app.state.session_factory)
    record = await repo.create(
        tenant_id=tenant_id,
        name=body.name,
        rules_json=body.rules_json,
        persona_json=body.persona_json or {},
        is_active=True,
    )
    logger.info("icp_created", tenant_id=tenant_id, icp_id=str(record.id))
    return IcpResponse.from_model(record)


@router.get("", response_model=list[IcpResponse])
async def list_icps(
    request: Request,
    tenant_id: str = Depends(get_current_tenant),
) -> list[IcpResponse]:
    """List all ICP configs for the current tenant."""
    repo = IcpConfigRepository(request.app.state.session_factory)
    records = await repo.list_by(tenant_id=tenant_id)
    return [IcpResponse.from_model(r) for r in records]


@router.get("/{icp_id}", response_model=IcpResponse)
async def get_icp(
    icp_id: str,
    request: Request,
    tenant_id: str = Depends(get_current_tenant),
) -> IcpResponse:
    """Get a single ICP config."""
    import uuid as _uuid
    repo = IcpConfigRepository(request.app.state.session_factory)
    record = await repo.get(_uuid.UUID(icp_id))
    if not record or str(record.tenant_id) != tenant_id:
        raise HTTPException(status_code=404, detail="ICP config not found")
    return IcpResponse.from_model(record)


@router.put("/{icp_id}", response_model=IcpResponse)
async def update_icp(
    icp_id: str,
    body: IcpUpdateRequest,
    request: Request,
    tenant_id: str = Depends(get_current_tenant),
) -> IcpResponse:
    """Update an ICP config."""
    import uuid as _uuid
    repo = IcpConfigRepository(request.app.state.session_factory)
    record = await repo.get(_uuid.UUID(icp_id))
    if not record or str(record.tenant_id) != tenant_id:
        raise HTTPException(status_code=404, detail="ICP config not found")

    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    updated = await repo.update(_uuid.UUID(icp_id), **updates)
    logger.info("icp_updated", tenant_id=tenant_id, icp_id=icp_id)
    return IcpResponse.from_model(updated)  # type: ignore[arg-type]


@router.delete("/{icp_id}", status_code=204)
async def delete_icp(
    icp_id: str,
    request: Request,
    tenant_id: str = Depends(get_current_tenant),
) -> None:
    """Soft-delete (deactivate) an ICP config."""
    import uuid as _uuid
    repo = IcpConfigRepository(request.app.state.session_factory)
    record = await repo.get(_uuid.UUID(icp_id))
    if not record or str(record.tenant_id) != tenant_id:
        raise HTTPException(status_code=404, detail="ICP config not found")
    await repo.update(_uuid.UUID(icp_id), is_active=False)
    logger.info("icp_deleted", tenant_id=tenant_id, icp_id=icp_id)
