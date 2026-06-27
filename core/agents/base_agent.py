"""
core/agents/base_agent.py

Base class for all agents in the platform. Every concrete agent
(WebMonitor, TriggerDetection, CompanyIntelligence, PersonaMatching,
Recommendation, HiringDetection, CompetitorAnalysis, ...) inherits from this.

Design goals (tied directly to the project brief):
- Planner never knows agent internals -> uniform interface (execute()).
- Agents only touch their declared slice of shared state.
- Agents request tools/connectors from registries instead of importing them.
- Every agent produces a structured, explainable result.
- Failures are structured, not raised raw, so the Planner can decide
  whether to retry, skip, or pause for human approval.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
import logging
import time
import uuid


# ---------------------------------------------------------------------------
# Status + Result types
# ---------------------------------------------------------------------------

class AgentStatus(str, Enum):
    SUCCESS = "success"
    FAILED = "failed"
    PARTIAL = "partial"          # ran, but with degraded/incomplete output
    SKIPPED = "skipped"          # planner decided not to run it
    AWAITING_APPROVAL = "awaiting_approval"  # human-in-the-loop gate


@dataclass
class AgentResult:
    """
    Uniform output shape for every agent.

    This is what the Planner, Execution Monitor, and Recommendation
    agent all consume. Keeping it identical across agents is what lets
    the Execution Monitor render status generically, and lets the
    Recommendation agent assemble 'reasoning + confidence + evidence'
    without special-casing each upstream agent.
    """
    agent_name: str
    status: AgentStatus
    output: dict[str, Any] = field(default_factory=dict)   # data to merge into shared state
    reasoning: Optional[str] = None                          # why this output was produced
    confidence: Optional[float] = None                       # 0.0 - 1.0, optional per-agent
    evidence: list[dict[str, Any]] = field(default_factory=list)  # supporting sources/snippets
    error: Optional[str] = None
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    duration_ms: Optional[int] = None
    run_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def to_log_entry(self) -> dict[str, Any]:
        """Shape used for execution_logs in shared state / Execution Monitor UI."""
        return {
            "run_id": self.run_id,
            "agent": self.agent_name,
            "status": self.status.value,
            "reasoning": self.reasoning,
            "confidence": self.confidence,
            "evidence_count": len(self.evidence),
            "error": self.error,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "duration_ms": self.duration_ms,
        }


class AgentExecutionError(Exception):
    """Raised internally, caught by execute(), turned into a FAILED AgentResult."""
    def __init__(self, message: str, recoverable: bool = True):
        super().__init__(message)
        self.recoverable = recoverable


# ---------------------------------------------------------------------------
# Base Agent
# ---------------------------------------------------------------------------

class BaseAgent(ABC):
    """
    Abstract base class every agent must inherit from.

    Subclasses MUST set:
      - name: str                      -> unique id used in Agent Registry
      - reads_from: set[str]           -> shared state keys this agent reads
      - writes_to: set[str]            -> shared state keys this agent is allowed to write

    Subclasses MUST implement:
      - async def run(self, state: dict) -> dict
            The actual agent logic. Takes the relevant slice of shared
            state, returns a dict of ONLY the keys this agent owns.

    Subclasses MAY override:
      - validate_input(state)         -> pre-flight checks before run()
      - build_result(output, state)   -> customize how reasoning/confidence/evidence are derived
    """

    name: str = "base_agent"
    description: str = ""
    reads_from: set[str] = set()
    writes_to: set[str] = set()

    def __init__(
        self,
        tool_registry: Optional[Any] = None,
        connector_registry: Optional[Any] = None,
        memory_service: Optional[Any] = None,
        config: Optional[dict[str, Any]] = None,
        logger: Optional[logging.Logger] = None,
    ):
        """
        Dependencies are injected, never imported directly.

        tool_registry      -> things like Tavily, Firecrawl-as-a-tool, etc.
        connector_registry  -> data source abstractions (RSS, Website, Search...)
        memory_service      -> shared memory (not conversation history)

        Kept as two separate registries (rather than one) to mirror the
        architecture diagram in the brief: Tool Registry and Connector
        Registry are distinct boxes with distinct responsibilities.
        """
        self.tools = tool_registry
        self.connectors = connector_registry
        self.memory = memory_service
        self.config = config or {}
        self.logger = logger or logging.getLogger(f"agent.{self.name}")

    # -- Public entrypoint, called by the Planner -----------------------

    async def execute(self, state: dict[str, Any]) -> AgentResult:
        """
        The ONLY method the Planner ever calls. Wraps run() with:
          - input validation
          - state-access enforcement (reads_from / writes_to)
          - timing
          - structured error handling

        Subclasses never override this. They implement run() instead.
        """
        started_at = datetime.now(timezone.utc).isoformat()
        start = time.perf_counter()

        try:
            self.validate_input(state)
            scoped_input = self._extract_scoped_state(state)

            self.logger.info(f"[{self.name}] starting")
            raw_output = await self.run(scoped_input)

            self._enforce_write_scope(raw_output)

            result = self.build_result(raw_output, state)

        except AgentExecutionError as e:
            self.logger.error(f"[{self.name}] failed: {e}")
            result = AgentResult(
                agent_name=self.name,
                status=AgentStatus.FAILED,
                error=str(e),
            )
        except Exception as e:  # noqa: BLE001 - last line of defense
            self.logger.exception(f"[{self.name}] unexpected error")
            result = AgentResult(
                agent_name=self.name,
                status=AgentStatus.FAILED,
                error=f"Unexpected error: {e}",
            )

        finished_at = datetime.now(timezone.utc).isoformat()
        result.started_at = started_at
        result.finished_at = finished_at
        result.duration_ms = int((time.perf_counter() - start) * 1000)
        result.agent_name = self.name

        self.logger.info(f"[{self.name}] finished status={result.status.value} "
                          f"in {result.duration_ms}ms")
        return result

    # -- Subclasses implement this ---------------------------------------

    @abstractmethod
    async def run(self, scoped_state: dict[str, Any]) -> dict[str, Any]:
        """
        Core agent logic. Receives ONLY the state keys declared in
        reads_from. Must return a dict containing ONLY keys declared
        in writes_to.
        """
        raise NotImplementedError

    # -- Hooks subclasses may override -----------------------------------

    def validate_input(self, state: dict[str, Any]) -> None:
        """Default: ensure every declared read key exists in state."""
        missing = [k for k in self.reads_from if k not in state]
        if missing:
            raise AgentExecutionError(
                f"Missing required state keys: {missing}", recoverable=False
            )

    def build_result(
        self, output: dict[str, Any], full_state: dict[str, Any]
    ) -> AgentResult:
        """
        Default: wrap raw output into AgentResult with no reasoning/confidence.
        Override in agents like Recommendation where explainability fields
        are produced directly by the LLM call inside run().
        """
        return AgentResult(
            agent_name=self.name,
            status=AgentStatus.SUCCESS,
            output=output,
        )

    # -- Internal helpers --------------------------------------------------

    def _extract_scoped_state(self, state: dict[str, Any]) -> dict[str, Any]:
        """Agent only ever sees the keys it declared via reads_from."""
        return {k: state.get(k) for k in self.reads_from}

    def _enforce_write_scope(self, output: dict[str, Any]) -> None:
        """
        Hard guardrail for: 'Each agent only updates its own part of state.'
        If an agent tries to sneak in a key it didn't declare, fail loudly
        instead of silently corrupting shared state.
        """
        illegal_keys = set(output.keys()) - self.writes_to
        if illegal_keys:
            raise AgentExecutionError(
                f"{self.name} attempted to write undeclared keys: {illegal_keys}. "
                f"Declared writes_to={self.writes_to}",
                recoverable=False,
            )

    # -- Convenience for subclasses ----------------------------------------

    def get_tool(self, tool_name: str):
        """Agents call this instead of importing tools directly."""
        if self.tools is None:
            raise AgentExecutionError(
                f"{self.name} requested tool '{tool_name}' but no ToolRegistry was injected."
            )
        return self.tools.get(tool_name)

    def get_connector(self, connector_type: str):
        """Agents call this instead of importing connectors directly."""
        if self.connectors is None:
            raise AgentExecutionError(
                f"{self.name} requested connector '{connector_type}' but no "
                f"ConnectorRegistry was injected."
            )
        return self.connectors.get(connector_type)

    async def remember(self, key: str, value: Any) -> None:
        """Write to shared memory (not conversation history — see brief)."""
        if self.memory:
            await self.memory.set(self.name, key, value)

    async def recall(self, key: str) -> Any:
        if self.memory:
            return await self.memory.get(self.name, key)
        return None
