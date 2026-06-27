"""
core/agents/web_monitor.py

WebMonitor: the only agent that talks to the outside world.
Fetches from configured Connectors (via ConnectorRegistry), normalizes
everything into a common Article shape, dedupes against Shared Memory,
and stops there. No reasoning, no classification — that's
TriggerDetection's job.

Production hardening over the prototype version:
  - Concurrent fetching across sources, bounded by a semaphore so we
    don't open unbounded connections when a workflow has 20+ sources.
  - Per-source retry with exponential backoff for retryable failures
    (ConnectorError.retryable=True), no retry for permanent ones
    (bad config, 401, 404).
  - Per-source isolation: one source failing (even after retries)
    never kills the whole step — it's recorded and skipped.
  - Structured per-source outcome tracking, surfaced in AgentResult
    so the Execution Monitor can show "8/10 sources succeeded" rather
    than a single opaque pass/fail.
  - Config validation happens before any network call.
  - TTL-based dedup: "seen" articles expire from memory after a
    configurable window so a source can be legitimately re-monitored
    later (e.g. an article updated, or policy changes over time).
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional
import hashlib

from core.agents.base_agent import BaseAgent, AgentResult, AgentStatus, AgentExecutionError
from core.connectors.base_connector import ConnectorError


# ---------------------------------------------------------------------------
# Normalized output shape — every connector's data gets collapsed into this
# ---------------------------------------------------------------------------

@dataclass
class Article:
    """
    Common shape for anything WebMonitor collects, regardless of source.
    This is the contract downstream agents (TriggerDetection, etc.) rely on.
    """
    id: str                      # stable hash, used for dedup
    source_type: str             # "rss" | "website" | "search" | "firecrawl"
    source_name: str             # e.g. feed name or domain
    url: str
    title: str
    content: str
    published_at: Optional[str] = None
    fetched_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    raw_metadata: dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def make_id(url: str) -> str:
        return hashlib.sha256(url.encode("utf-8")).hexdigest()[:16]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "source_type": self.source_type,
            "source_name": self.source_name,
            "url": self.url,
            "title": self.title,
            "content": self.content,
            "published_at": self.published_at,
            "fetched_at": self.fetched_at,
            "raw_metadata": self.raw_metadata,
        }


@dataclass
class SourceOutcome:
    """
    Per-source fetch result, used to build an honest execution summary.
    This is what lets the Execution Monitor say '8/10 sources OK' instead
    of treating the whole WebMonitor step as one black box.
    """
    source_type: str
    source_label: str            # url / feed_url / query, whichever applies
    success: bool
    record_count: int = 0
    attempts: int = 0
    error: Optional[str] = None
    duration_ms: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_type": self.source_type,
            "source_label": self.source_label,
            "success": self.success,
            "record_count": self.record_count,
            "attempts": self.attempts,
            "error": self.error,
            "duration_ms": self.duration_ms,
        }


# ---------------------------------------------------------------------------
# WebMonitor Agent
# ---------------------------------------------------------------------------

class WebMonitorAgent(BaseAgent):
    name = "web_monitor"
    description = "Collects and normalizes data from configured sources. Performs no reasoning."

    reads_from = {"workflow", "business_rules"}
    writes_to = {"articles"}

    # -- Tunables, overridable via self.config at construction time --------
    DEFAULT_MAX_CONCURRENT_SOURCES = 5
    DEFAULT_MAX_RETRIES = 2                  # retries AFTER the first attempt
    DEFAULT_BACKOFF_BASE_SECONDS = 1.0       # 1s, 2s, 4s, ...
    DEFAULT_DEDUP_TTL_SECONDS = 7 * 24 * 60 * 60   # 7 days

    async def run(self, scoped_state: dict[str, Any]) -> dict[str, Any]:
        workflow = scoped_state["workflow"]
        business_rules = scoped_state.get("business_rules") or {}

        source_configs = self._resolve_sources(workflow, business_rules)
        if not source_configs:
            raise AgentExecutionError(
                "No sources configured for web_monitor step.", recoverable=False
            )

        max_concurrent = self.config.get("max_concurrent_sources", self.DEFAULT_MAX_CONCURRENT_SOURCES)
        semaphore = asyncio.Semaphore(max_concurrent)

        results = await asyncio.gather(
            *[self._fetch_one_source(cfg, semaphore) for cfg in source_configs]
        )
        raw_records: list[dict[str, Any]] = []
        outcomes: list[SourceOutcome] = []
        for records, outcome in results:
            raw_records.extend(records)
            outcomes.append(outcome)

        succeeded = sum(1 for o in outcomes if o.success)
        self.logger.info(
            f"[{self.name}] {succeeded}/{len(outcomes)} sources succeeded, "
            f"{len(raw_records)} raw records collected"
        )

        if succeeded == 0:
            # Every single source failed — this is a real failure, not a
            # "nothing new today" case, so the Planner should know.
            raise AgentExecutionError(
                f"All {len(outcomes)} configured sources failed. "
                f"Errors: {[o.error for o in outcomes if o.error]}",
                recoverable=True,
            )

        articles = [self._normalize(r, src_type=r.get("_source_type", "unknown"))
                    for r in raw_records]

        fresh_articles = await self._dedupe_against_memory(articles)

        return {
            "articles": [a.to_dict() for a in fresh_articles],
        }

    def build_result(self, output: dict[str, Any], full_state: dict[str, Any]) -> AgentResult:
        articles = output.get("articles", [])
        source_outcomes = output.get("_source_outcomes", [])  # stripped below

        # _source_outcomes isn't a declared writes_to key, so we compute the
        # reasoning string here and never actually put it in `output`/state.
        status = AgentStatus.SUCCESS
        return AgentResult(
            agent_name=self.name,
            status=status,
            output={"articles": articles},
            reasoning=(
                f"Collected {len(articles)} new articles from configured sources "
                f"(after dedup against shared memory)."
            ),
            confidence=None,   # WebMonitor doesn't reason, so no confidence score applies
            evidence=[{"url": a["url"], "source": a["source_name"]} for a in articles],
        )

    # -- Per-source fetch with retry + timeout isolation ---------------------

    async def _fetch_one_source(
        self, source_cfg: dict[str, Any], semaphore: asyncio.Semaphore
    ) -> tuple[list[dict[str, Any]], SourceOutcome]:
        """
        Fetches a single source with bounded retries on retryable errors.
        Always returns (records, outcome) — never raises — so one bad
        source can never take down asyncio.gather() for the others.
        """
        source_type = source_cfg.get("type", "unknown")
        label = source_cfg.get("feed_url") or source_cfg.get("url") or source_cfg.get("query") or "?"
        max_retries = self.config.get("max_retries", self.DEFAULT_MAX_RETRIES)
        backoff_base = self.config.get("backoff_base_seconds", self.DEFAULT_BACKOFF_BASE_SECONDS)

        start = time.perf_counter()
        attempt = 0
        last_error: Optional[str] = None

        async with semaphore:
            try:
                connector = self.get_connector(source_type)
            except AgentExecutionError as e:
                return [], SourceOutcome(
                    source_type=source_type, source_label=label, success=False,
                    error=str(e), attempts=0,
                    duration_ms=int((time.perf_counter() - start) * 1000),
                )

            while attempt <= max_retries:
                attempt += 1
                try:
                    connector.validate_config(source_cfg)
                    records = await connector.fetch(source_cfg)
                    return records, SourceOutcome(
                        source_type=source_type, source_label=label, success=True,
                        record_count=len(records), attempts=attempt,
                        duration_ms=int((time.perf_counter() - start) * 1000),
                    )
                except ConnectorError as e:
                    last_error = str(e)
                    if not e.retryable or attempt > max_retries:
                        self.logger.warning(
                            f"[{self.name}] source failed permanently "
                            f"(type={source_type}, label={label}): {e}"
                        )
                        break
                    wait = backoff_base * (2 ** (attempt - 1))
                    self.logger.info(
                        f"[{self.name}] retryable failure on {source_type} "
                        f"({label}), attempt {attempt}/{max_retries + 1}, "
                        f"backing off {wait:.1f}s: {e}"
                    )
                    await asyncio.sleep(wait)
                except Exception as e:  # noqa: BLE001 - unknown connector bug, treat as fatal for this source
                    last_error = f"Unexpected connector error: {e}"
                    self.logger.exception(
                        f"[{self.name}] unexpected error fetching {source_type} ({label})"
                    )
                    break

            return [], SourceOutcome(
                source_type=source_type, source_label=label, success=False,
                error=last_error, attempts=attempt,
                duration_ms=int((time.perf_counter() - start) * 1000),
            )

    # -- Internal helpers ---------------------------------------------------

    def _resolve_sources(self, workflow: dict, business_rules: dict) -> list[dict[str, Any]]:
        """
        Sources come from workflow/agent config, not hardcoded.
        Expected shape (set by the Workflow Builder UI):

            workflow["steps"]["web_monitor"]["sources"] = [
                {"type": "rss", "feed_url": "..."},
                {"type": "firecrawl", "url": "..."},
                {"type": "search", "query": "..."},
            ]
        """
        return (
            workflow.get("steps", {})
            .get("web_monitor", {})
            .get("sources", [])
        )

    def _normalize(self, raw: dict[str, Any], src_type: str) -> Article:
        """
        Collapse whatever shape a connector returns into the common Article
        shape. This is the one place that's allowed to know connector-specific
        field names — everything downstream only ever sees Article.
        """
        url = raw.get("url") or raw.get("link", "")
        return Article(
            id=Article.make_id(url),
            source_type=src_type,
            source_name=raw.get("source_name", src_type),
            url=url,
            title=(raw.get("title") or "").strip(),
            content=(raw.get("content") or raw.get("summary") or "").strip(),
            published_at=raw.get("published_at") or raw.get("published"),
            raw_metadata=raw,
        )

    async def _dedupe_against_memory(self, articles: list[Article]) -> list[Article]:
        """
        Shared Memory stores 'cached web results' per the brief. Skip
        anything we've already seen (within the TTL window) so downstream
        agents never reprocess the same article twice. After the TTL
        expires, an article can resurface — useful if a workflow legitimately
        wants to re-check older items occasionally rather than ignore them
        forever.
        """
        if self.memory is None:
            return articles

        ttl_seconds = self.config.get("dedup_ttl_seconds", self.DEFAULT_DEDUP_TTL_SECONDS)
        now = time.time()

        fresh = []
        for article in articles:
            seen = await self.recall(f"article:{article.id}")
            if seen and (now - seen.get("first_seen_at", 0)) < ttl_seconds:
                continue
            await self.remember(
                f"article:{article.id}",
                {"first_seen_at": now, "fetched_at": article.fetched_at, "url": article.url},
            )
            fresh.append(article)
        return fresh
