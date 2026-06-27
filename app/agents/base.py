"""
app/agents/base.py

Abstract base class for all specialized agents.

Every agent:
  • Receives a ``MemoryManager`` at construction — the single gateway to all stores.
  • Exposes an async ``run(state) -> dict`` method that returns a partial
    PlannerState update.
  • Binds tenant_id and domain to every log entry via structlog context vars.
  • Handles and re-raises exceptions with structured error context so the
    Planner can route to an error handler node.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

import structlog

from app.agents.state import PlannerState
from app.memory.manager import MemoryManager


class BaseAgent(ABC):
    """
    Abstract base for all six specialized agents.

    Subclasses must implement ``_execute(state)`` which contains the
    agent-specific business logic.  ``run()`` wraps it with logging,
    error handling, and context binding.
    """

    #: Override in subclass with the agent's canonical name (used in logs + audit)
    agent_name: str = "base_agent"

    def __init__(self, memory_manager: MemoryManager) -> None:
        self._mm = memory_manager
        self._logger = structlog.get_logger(self.__class__.__name__)

    # ── Public entrypoint ─────────────────────────────────────────────────────

    async def run(self, state: PlannerState) -> dict[str, Any]:
        """
        Entrypoint called by the LangGraph node.

        Returns a *partial* PlannerState dict — LangGraph merges the result
        back into the full state automatically.
        """
        tenant_id = state.get("tenant_id", "unknown")
        domain = state.get("domain", "unknown")
        run_id = state.get("run_id", "unknown")

        log = self._logger.bind(
            agent=self.agent_name,
            tenant_id=tenant_id,
            domain=domain,
            run_id=run_id,
        )

        log.info("agent_start")
        try:
            result = await self._execute(state)
            log.info("agent_complete", result_keys=list(result.keys()))
            return result
        except Exception as exc:
            log.exception("agent_error", error=str(exc))
            return {
                "status": "failed",
                "error": f"[{self.agent_name}] {exc!s}",
            }

    # ── Abstract method ───────────────────────────────────────────────────────

    @abstractmethod
    async def _execute(self, state: PlannerState) -> dict[str, Any]:
        """
        Agent-specific logic.  Must return a partial PlannerState dict.
        Has access to ``self._mm`` (MemoryManager) and ``self._logger``.
        """
        ...

    # ── Convenience helpers ───────────────────────────────────────────────────

    def _log(self, state: PlannerState, **extra: Any) -> structlog.BoundLogger:
        """Return a logger bound with tenant_id and domain from state."""
        return self._logger.bind(
            agent=self.agent_name,
            tenant_id=state.get("tenant_id", "unknown"),
            domain=state.get("domain", "unknown"),
            run_id=state.get("run_id", "unknown"),
            **extra,
        )
