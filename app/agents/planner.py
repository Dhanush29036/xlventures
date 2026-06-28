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
# Custom Worker Agent & Loader
# ---------------------------------------------------------------------------

class CustomWorkerAgent(BaseAgent):
    def __init__(self, agent_id: str, name: str, description: str, tools_needed: list[str], memory_manager: MemoryManager):
        super().__init__(memory_manager)
        self.agent_name = agent_id
        self.display_name = name
        self.description = description
        self.tools_needed = tools_needed

    async def _execute(self, state: PlannerState) -> dict[str, Any]:
        import importlib
        try:
            mod = importlib.import_module(f"app.agents.workers.{self.agent_name}")
            func = getattr(mod, f"{self.agent_name}_agent")
            
            inputs = {
                "domain": state.get("domain"),
                "company_data": state.get("company_data"),
                "people": state.get("people"),
                "signals": state.get("signals"),
            }
            res = await func(inputs)
            
            return {
                "status": "completed",
                "signals": state.get("signals", []) + [{
                    "type": "custom_agent_output",
                    "score": 0.8,
                    "data": {
                        "agent_id": self.agent_name,
                        "result": res.get("result") or res
                    }
                }]
            }
        except Exception as e:
            self._logger.exception("custom_agent_exec_error", agent=self.agent_name, error=str(e))
            return {
                "status": "failed",
                "error": f"[{self.agent_name}] {e!s}"
            }

def load_custom_agents(mm: MemoryManager) -> dict[str, CustomWorkerAgent]:
    import os
    import json
    custom_agents = {}
    worker_path = os.path.join(os.path.dirname(__file__), "workers")
    if os.path.exists(worker_path):
        for file in os.listdir(worker_path):
            if file.endswith(".json"):
                try:
                    with open(os.path.join(worker_path, file), "r") as f:
                        data = json.load(f)
                        agent_id = data.get("agent_id")
                        if agent_id:
                            custom_agents[agent_id] = CustomWorkerAgent(
                                agent_id=agent_id,
                                name=data.get("name", agent_id),
                                description=data.get("description", ""),
                                tools_needed=data.get("capabilities", []),
                                memory_manager=mm
                            )
                except Exception:
                    pass
    return custom_agents


# ---------------------------------------------------------------------------
# Graph builder
# ---------------------------------------------------------------------------


def build_planner_graph(mm: MemoryManager, selected_agents: list[str] | None = None) -> StateGraph:
    """
    Build and return the compiled LangGraph dynamically.
    """
    # Instantiate core agents
    trigger_monitor = TriggerMonitorAgent(mm)
    icp_scorer = IcpScorerAgent(mm)
    contact_enrichment = ContactEnrichmentAgent(mm)
    persona_finder = PersonaFinderAgent(mm)
    validation = ValidationAgent(mm)
    summary_agent = SummaryAgent(mm)

    core_agents = {
        "trigger_monitor": trigger_monitor,
        "company_icp_agent": icp_scorer,
        "icp_scorer": icp_scorer,
        "contact_enrichment": contact_enrichment,
        "persona_finder": persona_finder,
        "validation_agent": validation,
        "validation": validation,
        "summary_agent": summary_agent,
        "summary": summary_agent,
    }

    custom_agents = load_custom_agents(mm)
    all_agents = {**core_agents, **custom_agents}

    graph = StateGraph(PlannerState)

    async def check_skip_wrapper(state: PlannerState) -> dict[str, Any]:
        return await _check_skip_node(state, mm)

    graph.add_node("filter_available_agents", _filter_available_agents)
    graph.add_node("check_skip", check_skip_wrapper)

    # Determine execution sequence
    if selected_agents:
        # Use exact sequence selected by user
        sequence = [a for a in selected_agents if a in all_agents]
    else:
        sequence = ["trigger_monitor", "icp_scorer", "contact_enrichment", "persona_finder", "validation", "summary"]

    for agent_id in sequence:
        agent = all_agents[agent_id]
        graph.add_node(agent_id, _make_node(agent))

    # Add edges
    graph.add_edge(START, "filter_available_agents")
    graph.add_edge("filter_available_agents", "check_skip")

    first_agent = sequence[0] if sequence else "summary"
    
    def _route_after_skip_dynamic(state: PlannerState) -> str:
        if state.get("should_skip"):
            return "end_skipped"
        return first_agent

    graph.add_conditional_edges(
        "check_skip",
        _route_after_skip_dynamic,
        {
            "end_skipped": END,
            first_agent: first_agent,
        },
    )

    for i in range(len(sequence)):
        current = sequence[i]
        if i == len(sequence) - 1:
            graph.add_edge(current, END)
        else:
            nxt = sequence[i + 1]
            if current in ("validation", "validation_agent"):
                def _route_after_val_dynamic(state: PlannerState) -> str:
                    if state.get("hitl_required"):
                        return "end_hitl"
                    if not state.get("validation_passed", True):
                        return "end_failed"
                    return nxt
                
                graph.add_conditional_edges(
                    current,
                    _route_after_val_dynamic,
                    {
                        "end_hitl": END,
                        "end_failed": END,
                        nxt: nxt,
                    }
                )
            else:
                graph.add_edge(current, nxt)

    return graph.compile()


# ---------------------------------------------------------------------------
# Planner entrypoint
# ---------------------------------------------------------------------------


class PlannerAgent:
    """
    High-level interface for the LangGraph planner.
    """

    def __init__(self, memory_manager: MemoryManager) -> None:
        self._mm = memory_manager
        self._log = logger.bind(agent="planner")

    async def run(
        self,
        tenant_id: str,
        domain: str,
        company_data: dict[str, Any],
        icp_config: dict[str, Any],
        people: list[dict[str, Any]] | None = None,
        selected_agents: list[str] | None = None,
        run_id: str | uuid.UUID | None = None,
    ) -> dict[str, Any]:
        """
        Execute the full pipeline for one company.
        """
        if run_id is None:
            actual_run_id = uuid.uuid4()
        elif isinstance(run_id, str):
            actual_run_id = uuid.UUID(run_id)
        else:
            actual_run_id = run_id

        log = self._log.bind(
            tenant_id=tenant_id, domain=domain, run_id=str(actual_run_id)
        )
        log.info("planner_run_start")

        # ── Create or update agent_run in Postgres ────────────────────────────
        run_repo = AgentRunRepository(self._mm._pg)
        existing = await run_repo.get(actual_run_id)
        if existing:
            await run_repo.update(
                actual_run_id,
                status="running",
                plan_json={
                    **(existing.plan_json or {}),
                    "domain": domain,
                    "icp_config_keys": list(icp_config.keys()),
                    "people_provided": len(people or []),
                }
            )
        else:
            await run_repo.create(
                id=actual_run_id,
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
            "run_id": str(actual_run_id),
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
            graph = build_planner_graph(self._mm, selected_agents)
            final_state: dict[str, Any] = await graph.ainvoke(initial_state)
            log.info(
                "planner_run_complete",
                status=final_state.get("status"),
                action=final_state.get("recommended_action"),
            )
            return final_state
        except Exception as exc:
            log.exception("planner_run_error", error=str(exc))
            # Mark run as failed in Postgres
            await run_repo.update(actual_run_id, status="failed")
            raise
