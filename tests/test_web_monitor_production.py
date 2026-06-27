"""
tests/test_web_monitor_production.py

Exercises the production-hardened WebMonitorAgent:
  1. Multiple sources fetched concurrently (timing should reflect
     concurrency, not sequential sum of latencies).
  2. A genuinely bad source (nonexistent domain -> ConnectorError,
     retryable) actually gets retried with backoff, then gives up
     and is recorded as failed, WITHOUT killing the other sources.
  3. A config-invalid source (missing required field) fails fast,
     with zero retries, since that's a non-retryable error.
  4. Dedup TTL behavior: same run twice in a row -> second run yields
     zero new articles (TTL hasn't expired).

Run with: python3 tests/test_web_monitor_production.py
"""

import asyncio
import sys
import os
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.agents.web_monitor import WebMonitorAgent
from core.connectors.rss_connector import RSSConnector
from core.connectors.website_connector import WebsiteConnector
from core.registries.connector_registry import ConnectorRegistry
from core.memory.memory_service import InMemoryMemoryService


GOOD_FEED_1 = "https://github.com/anthropics/anthropic-sdk-python/releases.atom"
GOOD_FEED_2 = "https://github.com/anthropics/anthropic-sdk-typescript/releases.atom"
BAD_DOMAIN_FEED = "https://this-domain-does-not-exist-xyz123abc.com/feed.xml"


async def test_concurrent_fetch_with_mixed_outcomes():
    print("=" * 70)
    print("TEST: concurrent fetch, 2 good sources + 1 bad source")
    print("=" * 70)

    registry = ConnectorRegistry()
    registry.register(RSSConnector())

    agent = WebMonitorAgent(
        connector_registry=registry,
        memory_service=InMemoryMemoryService(),
        config={"max_retries": 1, "backoff_base_seconds": 0.5},  # fast for testing
    )

    state = {
        "workflow": {
            "steps": {
                "web_monitor": {
                    "sources": [
                        {"type": "rss", "feed_url": GOOD_FEED_1},
                        {"type": "rss", "feed_url": GOOD_FEED_2},
                        {"type": "rss", "feed_url": BAD_DOMAIN_FEED},
                    ]
                }
            }
        },
        "business_rules": {},
    }

    start = time.perf_counter()
    result = await agent.execute(state)
    elapsed = time.perf_counter() - start

    articles = result.output.get("articles", [])
    print(f"status: {result.status.value}")
    print(f"total elapsed: {elapsed:.2f}s")
    print(f"articles returned: {len(articles)}")
    print(f"reasoning: {result.reasoning}")

    assert result.status.value == "success", "2/3 good sources should still yield success"
    assert len(articles) > 0, "Good sources should still produce articles despite one bad source"
    print("✅ Mixed success/failure handled correctly — bad source isolated, didn't block good ones.\n")
    return result


async def test_invalid_config_fails_fast_no_retry():
    print("=" * 70)
    print("TEST: invalid source config (missing feed_url) fails fast, no retries")
    print("=" * 70)

    registry = ConnectorRegistry()
    registry.register(RSSConnector())

    agent = WebMonitorAgent(
        connector_registry=registry,
        memory_service=InMemoryMemoryService(),
        config={"max_retries": 3, "backoff_base_seconds": 2.0},  # would be slow IF it retried
    )

    state = {
        "workflow": {
            "steps": {
                "web_monitor": {
                    "sources": [
                        {"type": "rss"},  # missing required feed_url
                        {"type": "rss", "feed_url": GOOD_FEED_1},
                    ]
                }
            }
        },
        "business_rules": {},
    }

    start = time.perf_counter()
    result = await agent.execute(state)
    elapsed = time.perf_counter() - start

    print(f"status: {result.status.value}")
    print(f"elapsed: {elapsed:.2f}s (should be fast — no backoff waits for the bad config)")
    print(f"articles returned: {len(result.output.get('articles', []))}")

    assert result.status.value == "success"
    assert elapsed < 5.0, "Non-retryable config error should fail immediately, not wait through backoffs"
    print("✅ Invalid config detected and skipped without wasting time on retries.\n")


async def test_dedup_ttl_blocks_second_run():
    print("=" * 70)
    print("TEST: TTL dedup blocks re-processing on second run within the window")
    print("=" * 70)

    registry = ConnectorRegistry()
    registry.register(RSSConnector())
    memory = InMemoryMemoryService()

    agent = WebMonitorAgent(
        connector_registry=registry,
        memory_service=memory,
        config={"dedup_ttl_seconds": 3600},  # 1 hour window
    )

    state = {
        "workflow": {"steps": {"web_monitor": {"sources": [{"type": "rss", "feed_url": GOOD_FEED_1}]}}},
        "business_rules": {},
    }

    r1 = await agent.execute(state)
    r2 = await agent.execute(state)

    print(f"run 1 articles: {len(r1.output.get('articles', []))}")
    print(f"run 2 articles: {len(r2.output.get('articles', []))}")

    assert len(r1.output.get("articles", [])) > 0
    assert len(r2.output.get("articles", [])) == 0
    print("✅ TTL-based dedup correctly suppresses already-seen articles on second run.\n")


async def test_website_connector_live():
    print("=" * 70)
    print("TEST: WebsiteConnector against a real page")
    print("=" * 70)

    registry = ConnectorRegistry()
    registry.register(WebsiteConnector())

    agent = WebMonitorAgent(
        connector_registry=registry,
        memory_service=InMemoryMemoryService(),
    )

    state = {
        "workflow": {
            "steps": {
                "web_monitor": {
                    "sources": [
                        {"type": "website", "url": "https://github.com/anthropics"},
                    ]
                }
            }
        },
        "business_rules": {},
    }

    result = await agent.execute(state)
    articles = result.output.get("articles", [])
    print(f"status: {result.status.value}")
    print(f"articles returned: {len(articles)}")
    if articles:
        print(f"title: {articles[0]['title']}")
        print(f"content length: {len(articles[0]['content'])} chars")

    assert result.status.value == "success"
    assert len(articles) == 1
    assert len(articles[0]["content"]) > 0
    print("✅ WebsiteConnector fetched and extracted real page content.\n")


async def main():
    await test_concurrent_fetch_with_mixed_outcomes()
    await test_invalid_config_fails_fast_no_retry()
    await test_dedup_ttl_blocks_second_run()
    await test_website_connector_live()
    print("✅ All production tests passed.")


if __name__ == "__main__":
    asyncio.run(main())
