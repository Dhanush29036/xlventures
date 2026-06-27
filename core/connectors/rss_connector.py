"""
core/connectors/rss_connector.py

Production RSS/Atom connector using feedparser. Network fetch is run in
a thread (feedparser is sync) with an enforced timeout, and failures are
classified into retryable vs non-retryable ConnectorErrors so WebMonitor's
retry logic knows what's worth retrying.
"""

from typing import Any
import asyncio

import feedparser

from core.connectors.base_connector import BaseConnector, ConnectorError


class RSSConnector(BaseConnector):
    type_name = "rss"
    required_fields = ("feed_url",)
    default_timeout_seconds = 12.0

    async def fetch(self, source_config: dict[str, Any]) -> list[dict[str, Any]]:
        self.validate_config(source_config)
        feed_url = source_config["feed_url"]
        timeout = source_config.get("timeout_seconds", self.default_timeout_seconds)

        try:
            parsed = await asyncio.wait_for(
                asyncio.to_thread(feedparser.parse, feed_url),
                timeout=timeout,
            )
        except asyncio.TimeoutError as e:
            raise ConnectorError(
                f"RSS fetch timed out after {timeout}s for {feed_url}", retryable=True
            ) from e

        # feedparser doesn't raise on HTTP errors / malformed XML — it sets
        # flags instead. We have to check those explicitly or we silently
        # return zero articles and never know why.
        status = parsed.get("status")
        if status is not None and status >= 400:
            raise ConnectorError(
                f"RSS feed {feed_url} returned HTTP {status}",
                retryable=status >= 500,  # 4xx = don't bother retrying, 5xx = might be transient
            )

        if parsed.bozo and not parsed.entries:
            # bozo=True with zero entries usually means the XML was garbage
            # or unreachable. bozo=True with entries present is often a minor
            # spec violation we can ignore (feedparser is very lenient).
            raise ConnectorError(
                f"RSS feed {feed_url} failed to parse: {parsed.get('bozo_exception')}",
                retryable=True,
            )

        source_name = parsed.feed.get("title", feed_url)
        records = []
        for entry in parsed.entries:
            records.append({
                "_source_type": self.type_name,
                "source_name": source_name,
                "url": entry.get("link", ""),
                "title": entry.get("title", ""),
                "summary": entry.get("summary", entry.get("description", "")),
                "published_at": entry.get("published", entry.get("updated")),
            })
        return records
