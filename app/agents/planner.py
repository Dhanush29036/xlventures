"""
app/agents/planner.py

LangGraph Planner Agent — Orchestrator
───────────────────────────────────────
Builds and compiles the LangGraph StateGraph that sequences all six
specialized agents.  Each agent is an async node function; conditional edges
implement the routing logic (skip, HITL pause, error handling).

Graph topology
──────────────

    START
      │
      ▼
  [check_skip] ──── should_skip=True ──────────────────────► END (skipped)
      │
   skip=False
      │
      ▼
  [trigger_monitor]
      │
      ▼
  [icp_scorer]
      │
      ▼
  [contact_enrichment]   ← enriches + writes to all 4 stores
      │
      ▼
  [persona_finder]
      │
      ▼
  [validation]
      │
      ├── hitl_required=True  ────────────────────────────► END (awaiting_hitl)
      │
      ├── validation_passed=False ──────────────────────── ► END (failed)
      │
      ▼
  [summary]
      │
      ▼
     END (completed)

Memory interactions at graph level
───────────────────────────────────
check_skip  → MM.should_skip_company()         (Redis + Neo4j)
check_skip  → MM.get_company_context()         (Redis + Neo4j)
check_skip  → MM.find_icp_candidates()         (Qdrant + Neo4j + Redis)
Each agent  → via their own _execute() — see individual agent files
"""

from __future__ import annotations

import uuid
from typing import Any

import structlog
from langgraph.graph import END, START, StateGraph

from app.agents.base import BaseAgent
from app.agents.contact_enrichment import ContactEnrichmentAgent
from app.agents.icp_scorer import IcpScorerAgent
from app.agents.persona_finder import PersonaFinderAgent
from app.agents.state import PlannerState
from app.agents.summary import SummaryAgent
from app.agents.trigger_monitor import TriggerMonitorAgent
from app.agents.validation import ValidationAgent
from app.memory.manager import MemoryManager
from app.memory.operational import AgentRunRepository

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Node functions
# ---------------------------------------------------------------------------


def _make_node(agent: BaseAgent):
    """Wrap an agent's run() method as a LangGraph node coroutine."""

    async def node(state: PlannerState) -> dict[str, Any]:
        # Respect user-selected agents
        selected = state.get("selected_agents")
        if selected is not None and agent.agent_name not in selected:
            logger.info("agent_skipped_by_user_selection", agent=agent.agent_name)
            return {}
        return await agent.run(state)

    node.__name__ = agent.agent_name
    return node

async def _filter_available_agents(state: PlannerState) -> dict[str, Any]:
    """
    Initial node to log or filter the available agents based on the selected_agents array.
    """
    selected = state.get("selected_agents")
    if selected is not None:
        logger.info("filtering_available_agents", selected_agents=selected)
    return {}

async def _check_skip_node(
    state: PlannerState,
    mm: MemoryManager,
) -> dict[str, Any]:
    """
    Pre-flight node:
    1. Checks if company was already processed (Redis → Neo4j).
    2. If not skipped, fetches prior context (Redis + Neo4j) for the Planner.
    3. Optionally kicks off find_icp_candidates to pre-score the company.
    """
    tenant_id = state.get("tenant_id", "")
    domain = state.get("domain", "")
    log = logger.bind(node="check_skip", tenant_id=tenant_id, domain=domain)

    # ── Deduplication check ───────────────────────────────────────────────────
    should_skip = await mm.should_skip_company(tenant_id, domain)
    if should_skip:
        log.info("company_skipped_as_duplicate")
        return {"should_skip": True, "status": "skipped"}

    # ── Fetch prior context ───────────────────────────────────────────────────
    prior_context = await mm.get_company_context(tenant_id, domain)
    log.info("prior_context_fetched", has_prior_runs=bool(prior_context.get("prior_runs")))

    # ── Optionally pre-compute semantic ICP score ─────────────────────────────
    icp_config: dict[str, Any] = state.get("icp_config", {})
    semantic_score = 0.0
    if icp_config.get("description"):
        candidates = await mm.find_icp_candidates(tenant_id, icp_config)
        # Check if this domain appears in top results
        for candidate in candidates:
            if candidate.get("domain") == domain:
                semantic_score = candidate.get("score", 0.0)
                break
        # Inject semantic score into company_data for IcpScorerAgent
        company_data = dict(state.get("company_data", {}))
        company_data["semantic_score"] = semantic_score

        log.info("semantic_score_precomputed", score=semantic_score)
        return {
            "should_skip": False,
            "prior_context": prior_context,
            "company_data": company_data,
            "status": "running",
        }

    return {
        "should_skip": False,
        "prior_context": prior_context,
        "status": "running",
    }


# ---------------------------------------------------------------------------
# Conditional edge functions
# ---------------------------------------------------------------------------


def _route_after_skip(state: PlannerState) -> str:
    """Route to END if skipped, else continue to trigger_monitor."""
    if state.get("should_skip"):
        return "end_skipped"
    return "trigger_monitor"


def _route_after_validation(state: PlannerState) -> str:
    """Route based on validation outcome."""
    if state.get("hitl_required"):
        return "end_hitl"
    if not state.get("validation_passed", True):
        return "end_failed"
    return "summary"


def _route_after_error(state: PlannerState) -> str:
    """If any agent set status=failed, short-circuit to END."""
    if state.get("status") == "failed":
        return "end_failed"
    return "continue"


# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------


def build_planner_graph(mm: MemoryManager) -> StateGraph:
    """
    Build and return the compiled LangGraph for the prospect intelligence pipeline.

    Parameters
    ----------
    mm:
        Connected MemoryManager instance (injected at startup).

    Returns
    -------
    Compiled LangGraph app (call ``.ainvoke(initial_state)`` to run).
    """
    # Instantiate all specialized agents with the shared MemoryManager
    trigger_monitor = TriggerMonitorAgent(mm)
    icp_scorer = IcpScorerAgent(mm)
    contact_enrichment = ContactEnrichmentAgent(mm)
    persona_finder = PersonaFinderAgent(mm)
    validation = ValidationAgent(mm)
    summary_agent = SummaryAgent(mm)

    graph = StateGraph(PlannerState)

    async def check_skip_wrapper(state: PlannerState) -> dict[str, Any]:
        return await _check_skip_node(state, mm)

    graph.add_node("filter_available_agents", _filter_available_agents)
    graph.add_node("check_skip", check_skip_wrapper)
    graph.add_node("trigger_monitor", _make_node(trigger_monitor))
    graph.add_node("icp_scorer", _make_node(icp_scorer))
    graph.add_node("contact_enrichment", _make_node(contact_enrichment))
    graph.add_node("persona_finder", _make_node(persona_finder))
    graph.add_node("validation", _make_node(validation))
    graph.add_node("summary", _make_node(summary_agent))

    # ── Define edges ──────────────────────────────────────────────────────────
    graph.add_edge(START, "filter_available_agents")
    graph.add_edge("filter_available_agents", "check_skip")

    graph.add_conditional_edges(
        "check_skip",
        _route_after_skip,
        {
            "end_skipped": END,
            "trigger_monitor": "trigger_monitor",
        },
    )

    graph.add_edge("trigger_monitor", "icp_scorer")
    graph.add_edge("icp_scorer", "contact_enrichment")
    graph.add_edge("contact_enrichment", "persona_finder")
    graph.add_edge("persona_finder", "validation")

    graph.add_conditional_edges(
        "validation",
        _route_after_validation,
        {
            "end_hitl": END,
            "end_failed": END,
            "summary": "summary",
        },
    )

    graph.add_edge("summary", END)

    return graph.compile()


# ---------------------------------------------------------------------------
# Planner entrypoint
# ---------------------------------------------------------------------------


class PlannerAgent:
    """
    High-level interface for the LangGraph planner.  Used by API routes and
    Celery tasks to trigger the full enrichment pipeline for a company.

    Example::

        planner = PlannerAgent(memory_manager)
        result  = await planner.run(
            tenant_id="tenant_abc",
            domain="acme.com",
            company_data={...},
            icp_config={...},
        )
    """

    def __init__(self, memory_manager: MemoryManager) -> None:
        self._mm = memory_manager
        self._graph = build_planner_graph(memory_manager)
        self._log = logger.bind(agent="planner")

    async def run(
        self,
        tenant_id: str,
        domain: str,
        company_data: dict[str, Any],
        icp_config: dict[str, Any],
        people: list[dict[str, Any]] | None = None,
        selected_agents: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Execute the full pipeline for one company.
        """
        run_id = uuid.uuid4()
        log = self._log.bind(
            tenant_id=tenant_id, domain=domain, run_id=str(run_id)
        )
        log.info("planner_run_start")

        # ── Create agent_run in Postgres ──────────────────────────────────────
        run_repo = AgentRunRepository(self._mm._pg)
        await run_repo.create(
            id=run_id,
            tenant_id=tenant_id,
            status="running",
            plan_json={
                "domain": domain,
                "icp_config_keys": list(icp_config.keys()),
                "people_provided": len(people or []),
            },
        )

        # ── Build initial state ───────────────────────────────────────────────
        initial_state: PlannerState = {
            "run_id": str(run_id),
            "tenant_id": tenant_id,
            "domain": domain,
            "company_data": company_data,
            "icp_config": icp_config,
            "people": people or [],
            "signals": [],
            "prior_context": {},
            "should_skip": False,
            "status": "running",
            "error": None,
        }
        if selected_agents is not None:
            initial_state["selected_agents"] = selected_agents

        # ── Execute LangGraph pipeline ────────────────────────────────────────
        try:
            final_state: dict[str, Any] = await self._graph.ainvoke(initial_state)
            log.info(
                "planner_run_complete",
                status=final_state.get("status"),
                action=final_state.get("recommended_action"),
            )
            return final_state
        except Exception as exc:
            log.exception("planner_run_error", error=str(exc))
            # Mark run as failed in Postgres
            await run_repo.update(run_id, status="failed")
            raise
