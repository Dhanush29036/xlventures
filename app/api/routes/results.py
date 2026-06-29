"""
app/api/routes/results.py — Results retrieval + CSV export.
"""

from __future__ import annotations

import csv
import io
import uuid
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.api.auth import get_current_tenant
from app.memory.operational import AgentRunRepository

logger = structlog.get_logger(__name__)
router = APIRouter(prefix="/results", tags=["results"])


class CompanyResult(BaseModel):
    domain: str
    name: str
    icp_score: float
    recommended_action: str
    people: list[dict[str, Any]]
    signals: list[dict[str, Any]]
    funding_stage: str
    headcount: int


class ResultsResponse(BaseModel):
    run_id: str
    status: str
    companies: list[CompanyResult]
    total_companies: int
    total_contacts: int
    total_signals: int


async def _get_run_or_404(run_id: str, tenant_id: str, request: Request):
    repo = AgentRunRepository(request.app.state.session_factory)
    run = await repo.get(uuid.UUID(run_id))
    if not run or str(run.tenant_id) != tenant_id:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


@router.get("/{run_id}", response_model=ResultsResponse)
async def get_results(
    run_id: str,
    request: Request,
    tenant_id: str = Depends(get_current_tenant),
) -> ResultsResponse:
    """Full enriched results for a completed run."""
    run = await _get_run_or_404(run_id, tenant_id, request)

    mm = request.app.state.memory_manager
    companies_raw: list[CompanyResult] = []

    # ── 1. Try audit_log (written by record_company_enriched) ─────────────────
    if run.plan_json:
        from sqlalchemy import select as sa_select, and_
        from app.memory.operational import AuditLog

        async with request.app.state.session_factory() as session:
            result = await session.execute(
                sa_select(AuditLog).where(
                    and_(
                        AuditLog.run_id == uuid.UUID(run_id),
                        AuditLog.event_type == "company_enriched",
                    )
                )
            )
            audit_entries = result.scalars().all()

        for entry in audit_entries:
            d = entry.details_json or {}
            domain = d.get("domain", "")
            if not domain:
                continue
            graph_data = await mm._neo4j.get_company_with_people(domain)
            prior = await mm._redis.get_prior_runs(tenant_id, domain)
            last_summary = prior[-1] if prior else {}

            companies_raw.append(
                CompanyResult(
                    domain=domain,
                    name=graph_data.get("company", {}).get("name", domain),
                    icp_score=last_summary.get("icp_score", 0.0),
                    recommended_action=last_summary.get("recommended_action", "unknown"),
                    people=graph_data.get("people", []),
                    signals=graph_data.get("signals", []),
                    funding_stage=graph_data.get("company", {}).get("funding_stage", ""),
                    headcount=graph_data.get("company", {}).get("headcount", 0),
                )
            )

    # ── 2. Fallback: read domains from plan_json → query Neo4j directly ────────
    if not companies_raw and run.plan_json:
        plan = run.plan_json
        # Gather candidate domains from plan
        candidate_domains: list[str] = []
        if plan.get("company_domain"):
            candidate_domains.append(plan["company_domain"])
        if plan.get("domain"):
            candidate_domains.append(plan["domain"])

        # If no specific domains, use DEMO_COMPANIES domains
        if not candidate_domains:
            from app.tasks import DEMO_COMPANIES
            candidate_domains = [c["domain"] for c in DEMO_COMPANIES]

        for domain in candidate_domains:
            try:
                graph_data = await mm._neo4j.get_company_with_people(domain)
                if not graph_data.get("company"):
                    continue
                prior = await mm._redis.get_prior_runs(tenant_id, domain)
                last_summary = prior[-1] if prior else {}
                company_node = graph_data.get("company", {})

                companies_raw.append(
                    CompanyResult(
                        domain=domain,
                        name=company_node.get("name", domain),
                        icp_score=float(last_summary.get("icp_score", 0.0)),
                        recommended_action=last_summary.get("recommended_action", "review"),
                        people=graph_data.get("people", []),
                        signals=graph_data.get("signals", []),
                        funding_stage=company_node.get("funding_stage", ""),
                        headcount=company_node.get("headcount", 0) or 0,
                    )
                )
            except Exception:
                continue

    total_contacts = sum(len(c.people) for c in companies_raw)
    total_signals = sum(len(c.signals) for c in companies_raw)

    return ResultsResponse(
        run_id=run_id,
        status=run.status,
        companies=companies_raw,
        total_companies=len(companies_raw),
        total_contacts=total_contacts,
        total_signals=total_signals,
    )



@router.get("/{run_id}/export")
async def export_csv(
    run_id: str,
    request: Request,
    tenant_id: str = Depends(get_current_tenant),
) -> StreamingResponse:
    """Export results as CSV."""
    result = await get_results(run_id, request, tenant_id)

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "domain", "company_name", "icp_score", "recommended_action",
        "headcount", "funding_stage", "contact_count", "signal_count",
        "contact_emails", "contact_titles",
    ])
    for c in result.companies:
        emails = "; ".join(p.get("email", "") for p in c.people)
        titles = "; ".join(p.get("title", "") for p in c.people)
        writer.writerow([
            c.domain, c.name, c.icp_score, c.recommended_action,
            c.headcount, c.funding_stage, len(c.people), len(c.signals),
            emails, titles,
        ])

    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=results_{run_id[:8]}.csv"},
    )


@router.post("/{run_id}/company/{domain}/approve", status_code=200)
async def approve_company(
    run_id: str,
    domain: str,
    request: Request,
    tenant_id: str = Depends(get_current_tenant),
) -> dict[str, str]:
    """Mark a company as approved for outreach."""
    await _get_run_or_404(run_id, tenant_id, request)
    mm = request.app.state.memory_manager
    await mm._redis.save_run_summary(
        tenant_id=tenant_id,
        company_domain=domain,
        summary={"approved_for_outreach": True, "run_id": run_id},
    )
    logger.info("company_approved_for_outreach", domain=domain, run_id=run_id)
    return {"status": "approved", "domain": domain}


@router.post("/{run_id}/company/{domain}/reject", status_code=200)
async def reject_company(
    run_id: str,
    domain: str,
    request: Request,
    tenant_id: str = Depends(get_current_tenant),
) -> dict[str, str]:
    """Mark a company as not a fit."""
    await _get_run_or_404(run_id, tenant_id, request)
    mm = request.app.state.memory_manager
    await mm._redis.save_run_summary(
        tenant_id=tenant_id,
        company_domain=domain,
        summary={"not_a_fit": True, "run_id": run_id},
    )
    logger.info("company_rejected", domain=domain, run_id=run_id)
    return {"status": "rejected", "domain": domain}
