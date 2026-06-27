"""
tests/test_web_monitor_live.py

End-to-end smoke test: real RSS feed -> RSSConnector -> ConnectorRegistry
-> WebMonitorAgent.execute() -> AgentResult with normalized Article dicts.

Run with: python3 tests/test_web_monitor_live.py
"""

import asyncio
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.agents.web_monitor import WebMonitorAgent
from core.connectors.rss_connector import RSSConnector
from core.registries.connector_registry import ConnectorRegistry
from core.memory.memory_service import InMemoryMemoryService


async def main():
    # 1. Wire up the registries / services WebMonitor depends on.
    connector_registry = ConnectorRegistry()
    connector_registry.register(RSSConnector())

    memory = InMemoryMemoryService()

    agent = WebMonitorAgent(
        connector_registry=connector_registry,
        memory_service=memory,
    )

    # 2. Build the slice of shared state WebMonitor expects.
    #    Using a real, stable tech-news RSS feed so we get genuine articles.
    # NOTE: this sandbox's outbound network is allowlisted to specific domains
    # (pypi, npm, github, etc). techcrunch.com (and most general news sites)
    # are blocked here with a 403, which is a sandbox restriction — not a bug
    # in RSSConnector. Using GitHub's releases Atom feed instead, which is a
    # real, live, externally-hosted RSS/Atom feed reachable from this sandbox.
    # Your actual dev machine / server won't have this restriction, so
    # techcrunch.com or any other feed will work there.
    state = {
        "workflow": {
            "steps": {
                "web_monitor": {
                    "sources": [
                        {
                            "type": "rss",
                            "feed_url": "https://github.com/anthropics/anthropic-sdk-python/releases.atom",
                        },
                    ]
                }
            }
        },
        "business_rules": {},
    }

    # 3. Run #1 — should fetch + normalize + store everything as "new".
    print("=" * 70)
    print("RUN 1 (expect: articles found, all fresh)")
    print("=" * 70)
    result1 = await agent.execute(state)
    print(f"status: {result1.status.value}")
    print(f"reasoning: {result1.reasoning}")
    print(f"error: {result1.error}")
    articles1 = result1.output.get("articles", [])
    print(f"articles returned: {len(articles1)}")
    if articles1:
        print("\nSample article (first one):")
        print(json.dumps(articles1[0], indent=2, default=str)[:800])

    # 4. Run #2 — same sources, same memory instance -> dedup should kick in
    #    and articles list should now be empty (nothing "new").
    print("\n" + "=" * 70)
    print("RUN 2 (expect: 0 articles — dedup against shared memory)")
    print("=" * 70)
    result2 = await agent.execute(state)
    print(f"status: {result2.status.value}")
    print(f"reasoning: {result2.reasoning}")
    articles2 = result2.output.get("articles", [])
    print(f"articles returned: {len(articles2)}")

    # 5. Sanity assertions
    assert result1.status.value == "success", "Run 1 should succeed"
    assert len(articles1) > 0, "Run 1 should find at least some articles from a live feed"
    assert len(articles2) == 0, "Run 2 should find 0 new articles due to dedup"
    print("\n✅ All assertions passed — WebMonitor + RSSConnector + dedup all work end-to-end.")


if __name__ == "__main__":
    asyncio.run(main())
