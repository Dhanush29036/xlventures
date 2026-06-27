# Agentic Platform — Base Agent + WebMonitor (production)

## Structure

```
core/
  agents/
    base_agent.py        # BaseAgent abstract class — every agent inherits this
    web_monitor.py        # WebMonitorAgent — concurrent fetch + retry + normalize + dedupe
  connectors/
    base_connector.py     # BaseConnector interface + ConnectorError(retryable=...)
    rss_connector.py        # RSS/Atom via feedparser
    website_connector.py     # Single-page scrape via httpx + BeautifulSoup
    search_connector.py      # Tavily search API
    firecrawl_connector.py   # Firecrawl scrape API (JS-rendered pages)
  registries/
    connector_registry.py  # name -> connector lookup + build_default_connector_registry()
  memory/
    memory_service.py      # InMemoryMemoryService stub (swap for Postgres/Redis in real prod)
tests/
  test_web_monitor_live.py        # basic end-to-end + dedup proof
  test_web_monitor_failures.py    # partial failure + no-sources-configured paths
  test_web_monitor_production.py  # concurrency, retry/backoff, TTL dedup, WebsiteConnector
requirements.txt
```

## Setup

```bash
pip install -r requirements.txt
```

Search and Firecrawl connectors need API keys at runtime (not import time):

```bash
export TAVILY_API_KEY=...
export FIRECRAWL_API_KEY=...
```

## Run tests

```bash
python3 tests/test_web_monitor_live.py
python3 tests/test_web_monitor_failures.py
python3 tests/test_web_monitor_production.py
```

## What "production" means here

- **Concurrency**: all sources in a workflow step are fetched in parallel,
  bounded by a semaphore (`max_concurrent_sources`, default 5) so a workflow
  with 20 sources doesn't open 20 simultaneous connections.
- **Retry with backoff**: each connector classifies its own failures as
  `retryable` or not (e.g. DNS failure / 5xx = retryable, bad config / 401 /
  404 = not). WebMonitor retries retryable failures with exponential backoff
  (`max_retries`, `backoff_base_seconds`), and gives up immediately on
  non-retryable ones instead of wasting time.
- **Isolation**: one source failing — even after retries — never kills the
  step. `SourceOutcome` tracks per-source success/failure so you always know
  exactly which sources worked.
- **Full failure vs partial failure**: if *every* source fails, WebMonitor
  raises a real `AgentExecutionError` so the Planner knows this run actually
  failed, rather than silently returning an empty article list.
- **TTL-based dedup**: "already seen" articles are tracked with a
  `first_seen_at` timestamp and a configurable `dedup_ttl_seconds` (default
  7 days), so articles can legitimately resurface for re-processing later
  instead of being suppressed forever.
- **Config validation before network calls**: every connector declares
  `required_fields`; missing fields raise a non-retryable `ConnectorError`
  immediately, before any HTTP/DNS call is attempted.

## Wiring it up for real

```python
from core.agents.web_monitor import WebMonitorAgent
from core.registries.connector_registry import build_default_connector_registry
from core.memory.memory_service import InMemoryMemoryService  # swap for real impl

agent = WebMonitorAgent(
    connector_registry=build_default_connector_registry(),
    memory_service=InMemoryMemoryService(),
    config={
        "max_concurrent_sources": 5,
        "max_retries": 2,
        "backoff_base_seconds": 1.0,
        "dedup_ttl_seconds": 7 * 24 * 60 * 60,
    },
)

result = await agent.execute(state)
```

`state["workflow"]["steps"]["web_monitor"]["sources"]` accepts a mix of:

```python
[
    {"type": "rss", "feed_url": "https://example.com/feed.xml"},
    {"type": "website", "url": "https://example.com/about"},
    {"type": "search", "query": "Series A funding fintech this week"},
    {"type": "firecrawl", "url": "https://example.com/js-heavy-page"},
]
```

## Known sandbox caveat (dev environment only)

While developing this, outbound network access was restricted to an
allowlist (pypi, npm, github, etc). General sites like TechCrunch returned
403s purely due to that sandbox restriction — tests here use GitHub's Atom
feeds and github.com pages as stand-ins. None of this affects real
deployments; swap in whatever real feed/site/query URLs you need once
running outside a restricted sandbox.

## Next steps (not yet built)

- Agent Registry + Tool Registry
- Planner orchestration loop (LangGraph)
- TriggerDetection agent (first consumer of `articles`)
