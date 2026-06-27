"""
tests/test_web_monitor_failures.py

Checks WebMonitor's graceful-degradation paths:
  1. A connector that fails (bad URL) shouldn't kill the whole step if
     other sources still succeed.
  2. No sources configured at all -> clean AgentExecutionError -> FAILED
     AgentResult (not an unhandled crash the Planner can't reason about).
"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.agents.web_monitor import WebMonitorAgent
from core.connectors.rss_connector import RSSConnector
from core.registries.connector_registry import ConnectorRegistry
from core.memory.memory_service import InMemoryMemoryService


async def test_partial_failure_one_bad_source():
    connector_registry = ConnectorRegistry()
    connector_registry.register(RSSConnector())
    agent = WebMonitorAgent(
        connector_registry=connector_registry,
        memory_service=InMemoryMemoryService(),
    )

    state = {
        "workflow": {
            "steps": {
                "web_monitor": {
                    "sources": [
                        # bad / unreachable domain (not on sandbox allowlist, or just garbage)
                        {"type": "rss", "feed_url": "https://this-domain-does-not-exist-xyz123.com/feed"},
                        # good, reachable feed
                        {"type": "rss", "feed_url": "https://github.com/anthropics/anthropic-sdk-python/releases.atom"},
                    ]
                }
            }
        },
        "business_rules": {},
    }

    result = await agent.execute(state)
    print("=" * 70)
    print("TEST: one bad source + one good source")
    print("=" * 70)
    print(f"status: {result.status.value}")
    print(f"error: {result.error}")
    print(f"articles returned: {len(result.output.get('articles', []))}")

    assert result.status.value == "success", "Should still succeed despite one bad source"
    assert len(result.output.get("articles", [])) > 0, "Good source should still produce articles"
    print("✅ Partial failure handled gracefully — bad source skipped, good source still processed.\n")


async def test_no_sources_configured():
    connector_registry = ConnectorRegistry()
    connector_registry.register(RSSConnector())
    agent = WebMonitorAgent(
        connector_registry=connector_registry,
        memory_service=InMemoryMemoryService(),
    )

    state = {
        "workflow": {"steps": {"web_monitor": {"sources": []}}},
        "business_rules": {},
    }

    result = await agent.execute(state)
    print("=" * 70)
    print("TEST: no sources configured at all")
    print("=" * 70)
    print(f"status: {result.status.value}")
    print(f"error: {result.error}")

    assert result.status.value == "failed", "Should fail cleanly, not crash"
    assert result.error is not None
    print("✅ No-sources case fails cleanly with a structured AgentResult (Planner can react).\n")


async def main():
    await test_partial_failure_one_bad_source()
    await test_no_sources_configured()
    print("✅ All failure-path tests passed.")


if __name__ == "__main__":
    asyncio.run(main())
