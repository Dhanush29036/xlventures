"""
core/memory/memory_service.py

Minimal in-memory implementation of Shared Memory for local testing.
In production this would be backed by Postgres/Redis, but the interface
(get/set scoped by agent name + key) is what agents depend on — so this
stub is enough to prove WebMonitor's dedup logic actually works.
"""

from typing import Any


class InMemoryMemoryService:
    def __init__(self):
        self._store: dict[str, Any] = {}

    def _scoped_key(self, agent_name: str, key: str) -> str:
        return f"{agent_name}:{key}"

    async def set(self, agent_name: str, key: str, value: Any) -> None:
        self._store[self._scoped_key(agent_name, key)] = value

    async def get(self, agent_name: str, key: str) -> Any:
        return self._store.get(self._scoped_key(agent_name, key))

    def dump(self) -> dict[str, Any]:
        """Debug helper to inspect what's been stored."""
        return dict(self._store)
