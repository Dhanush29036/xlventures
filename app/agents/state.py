"""
app/agents/state.py

LangGraph shared state schema + Pydantic v2 data contracts used by all agents.

The ``PlannerState`` TypedDict is the single object that flows through every
node in the LangGraph graph.  Each agent node receives the full state and
returns a *partial* dict — LangGraph merges the partial update back in.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any
from typing_extensions import Annotated, TypedDict
from pydantic import BaseModel, EmailStr, Field, field_validator


# ---------------------------------------------------------------------------
# Pydantic v2 data contracts (shared between agents and memory layer)
# ---------------------------------------------------------------------------


class SignalModel(BaseModel):
    """A buying signal observed for a company."""

    type: str  # e.g. "funding_round", "job_posting", "news_mention"
    occurred_at: datetime
    data: dict[str, Any] = Field(default_factory=dict)
    score: float = Field(default=0.0, ge=0.0, le=1.0)

    @field_validator("occurred_at", mode="before")
    @classmethod
    def parse_dt(cls, v: Any) -> datetime:
        if isinstance(v, str):
            return datetime.fromisoformat(v)
        return v


class PersonModel(BaseModel):
    """A person (employee / contact) at a target company."""

    email: str
    name: str
    title: str
    company_domain: str
    seniority: str = ""          # C-Suite | VP | Director | Manager | IC
    is_decision_maker: bool = False
    linkedin_url: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CompanyModel(BaseModel):
    """Core company profile used throughout the pipeline."""

    domain: str
    name: str
    description: str = ""
    headcount: int = 0
    funding_stage: str = ""      # Seed | Series A | Series B | ...
    industry: str = ""
    hq_country: str = ""
    annual_revenue_usd: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class IcpScoreModel(BaseModel):
    """Output of the ICP Scorer agent."""

    score: float = Field(ge=0.0, le=1.0)
    matched_rules: list[str] = Field(default_factory=list)
    disqualifying_rules: list[str] = Field(default_factory=list)
    is_match: bool = False


class ValidationResultModel(BaseModel):
    """Output of the Validation agent."""

    passed: bool
    issues: list[str] = Field(default_factory=list)
    hitl_required: bool = False
    hitl_item_id: str | None = None


class EnrichmentResultModel(BaseModel):
    """Output of the Contact Enrichment agent."""

    enriched_contacts: list[PersonModel] = Field(default_factory=list)
    contacts_found: int = 0
    data_quality_score: float = Field(default=0.0, ge=0.0, le=1.0)


class RunSummaryModel(BaseModel):
    """Final summary persisted to Redis episodic store."""

    run_id: str
    tenant_id: str
    domain: str
    icp_score: float
    contacts_found: int
    signals_detected: int
    decision_makers: list[str] = Field(default_factory=list)
    recommended_action: str = ""   # "outreach" | "nurture" | "disqualify"
    generated_at: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# LangGraph State
# ---------------------------------------------------------------------------


class PlannerState(TypedDict, total=False):
    """
    Shared mutable state flowing through every node in the LangGraph pipeline.

    Fields are populated progressively as each agent runs.  Agents only need
    to return the keys they modify — LangGraph merges the partial update.
    """

    # ── Identity ─────────────────────────────────────────────────────────────
    run_id: str           # UUID string for this pipeline run
    tenant_id: str
    domain: str           # target company domain

    # ── Input context (set by Planner before graph runs) ─────────────────────
    company_data: dict[str, Any]        # raw company profile dict
    icp_config: dict[str, Any]          # ICP rules + description + persona_json
    prior_context: dict[str, Any]       # output of MM.get_company_context()

    # ── Deduplication ────────────────────────────────────────────────────────
    should_skip: bool                   # True → skip all agents, go to END

    # ── Trigger Monitor outputs ───────────────────────────────────────────────
    signals: list[dict[str, Any]]
    trigger_score: float

    # ── ICP Scorer outputs ────────────────────────────────────────────────────
    icp_score: float
    icp_matched_rules: list[str]
    icp_is_match: bool

    # ── Validation outputs ────────────────────────────────────────────────────
    validation_passed: bool
    validation_issues: list[str]
    hitl_required: bool
    hitl_item_id: str | None

    # ── Persona Finder outputs ────────────────────────────────────────────────
    people: list[dict[str, Any]]
    target_personas: list[dict[str, Any]]

    # ── Contact Enrichment outputs ────────────────────────────────────────────
    enriched_contacts: list[dict[str, Any]]
    data_quality_score: float

    # ── Summary outputs ───────────────────────────────────────────────────────
    summary: dict[str, Any]
    recommended_action: str   # "outreach" | "nurture" | "disqualify"

    # ── Error / status ────────────────────────────────────────────────────────
    error: str | None
    status: str   # running | completed | failed | skipped | awaiting_hitl
