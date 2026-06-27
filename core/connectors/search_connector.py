"""
core/connectors/search_connector.py

Wraps Tavily's search API (per your tech stack) behind the same Connector
interface. Lets WebMonitor run a configured query ("companies that raised
Series A in fintech this week") and get back search-result-shaped records,
normalized the same way an RSS entry or scraped page would be.

Requires TAVILY_API_KEY to be set in the environment (or passed via
source_config["api_key"] for per-source overrides).
"""

import os
from typing import Any

import httpx

from core.connectors.base_connector import BaseConnector, ConnectorError

TAVILY_ENDPOINT = "https://api.tavily.com/search"


class SearchConnector(BaseConnector):
    type_name = "search"
    required_fields = ("query",)
    default_timeout_seconds = 20.0

    async def fetch(self, source_config: dict[str, Any]) -> list[dict[str, Any]]:
        self.validate_config(source_config)
        query = source_config["query"]
        timeout = source_config.get("timeout_seconds", self.default_timeout_seconds)
        max_results = source_config.get("max_results", 10)

        api_key = source_config.get("api_key") or os.environ.get("TAVILY_API_KEY")
        if not api_key:
            raise ConnectorError(
                "SearchConnector requires TAVILY_API_KEY (env var or source_config['api_key'])",
                retryable=False,
            )

        payload = {
            "api_key": api_key,
            "query": query,
            "max_results": max_results,
            "search_depth": source_config.get("search_depth", "basic"),
        }

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(TAVILY_ENDPOINT, json=payload)
        except httpx.TimeoutException as e:
            raise ConnectorError(f"Tavily search timed out after {timeout}s for query={query!r}", retryable=True) from e
        except httpx.ConnectError as e:
            raise ConnectorError(f"Could not connect to Tavily: {e}", retryable=True) from e

        if response.status_code == 401:
            raise ConnectorError("Tavily API key rejected (401)", retryable=False)
        if response.status_code >= 400:
            raise ConnectorError(
                f"Tavily search returned HTTP {response.status_code}: {response.text[:200]}",
                retryable=response.status_code >= 500,
            )

        data = response.json()
        results = data.get("results", [])

        records = []
        for r in results:
            records.append({
                "_source_type": self.type_name,
                "source_name": f"search:{query}",
                "url": r.get("url", ""),
                "title": r.get("title", ""),
                "summary": r.get("content", ""),
                "published_at": r.get("published_date"),
            })
        return records
