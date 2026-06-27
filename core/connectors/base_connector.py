"""
core/connectors/base_connector.py

Connectors abstract external data sources (RSS, Website, Search, Firecrawl...).
WebMonitor never imports a connector directly — it asks the ConnectorRegistry
for one by type name, then calls .fetch(config) on whatever it gets back.

This is what lets you add a new data source (e.g. a LinkedIn connector)
without touching WebMonitorAgent at all: write the connector, register it,
done.

Production additions over the prototype version:
  - required_fields: declared per-connector so config mistakes are caught
    BEFORE a network call, with a clear error pointing at the bad source.
  - default_timeout_seconds: connector-specific default, overridable per
    source config (a slow Firecrawl crawl vs a fast RSS fetch shouldn't
    share one timeout).
  - ConnectorError: a typed exception so WebMonitor can distinguish
    "config problem" (don't retry) from "transient network problem"
    (worth retrying).
"""

from abc import ABC, abstractmethod
from typing import Any


class ConnectorError(Exception):
    """
    Raised by connectors on failure. `retryable=True` means WebMonitor's
    retry logic should retry this fetch; `retryable=False` means the
    error is permanent (bad config, 404, auth failure) and retrying is
    pointless.
    """
    def __init__(self, message: str, retryable: bool = True):
        super().__init__(message)
        self.retryable = retryable


class BaseConnector(ABC):
    """
    Every connector must implement fetch() and return a list of raw dicts.
    Connectors do NOT need to agree on field names with each other — that's
    WebMonitor's _normalize() job. Connectors just need to return *something*
    reasonable for their source type.
    """

    type_name: str = "base"
    required_fields: tuple[str, ...] = ()       # e.g. ("feed_url",) for RSS
    default_timeout_seconds: float = 15.0

    def validate_config(self, source_config: dict[str, Any]) -> None:
        """
        Checked by WebMonitor BEFORE calling fetch(), so a missing
        'feed_url' fails fast with a clear message instead of an
        AttributeError three layers deep inside a network call.
        """
        missing = [f for f in self.required_fields if not source_config.get(f)]
        if missing:
            raise ConnectorError(
                f"{self.type_name} connector config missing required field(s): {missing}. "
                f"Got config keys: {list(source_config.keys())}",
                retryable=False,
            )

    @abstractmethod
    async def fetch(self, source_config: dict[str, Any]) -> list[dict[str, Any]]:
        """
        source_config is whatever shape was set in the Workflow Builder UI
        for this specific source, e.g. {"type": "rss", "feed_url": "..."}.
        Must return a list of raw records (dicts). Each dict should at least
        try to include url/link, title, content/summary, published_at —
        but WebMonitor's normalizer is tolerant of missing fields.

        Raise ConnectorError on failure (set retryable appropriately).
        Any other exception is treated as retryable by default.
        """
        raise NotImplementedError
