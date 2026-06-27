"""
core/connectors/firecrawl_connector.py

Wraps Firecrawl's scrape API (per your tech stack) behind the Connector
interface. Firecrawl handles JS-rendered pages and returns clean markdown,
which is why your brief lists it separately from the plain WebsiteConnector
(httpx + BeautifulSoup won't render JS-heavy sites).

Requires FIRECRAWL_API_KEY in the environment (or source_config["api_key"]).
"""

import os
from typing import Any

import httpx

from core.connectors.base_connector import BaseConnector, ConnectorError

FIRECRAWL_ENDPOINT = "https://api.firecrawl.dev/v1/scrape"


class FirecrawlConnector(BaseConnector):
    type_name = "firecrawl"
    required_fields = ("url",)
    default_timeout_seconds = 30.0   # Firecrawl renders JS — slower than plain httpx

    async def fetch(self, source_config: dict[str, Any]) -> list[dict[str, Any]]:
        self.validate_config(source_config)
        url = source_config["url"]
        timeout = source_config.get("timeout_seconds", self.default_timeout_seconds)

        api_key = source_config.get("api_key") or os.environ.get("FIRECRAWL_API_KEY")
        if not api_key:
            raise ConnectorError(
                "FirecrawlConnector requires FIRECRAWL_API_KEY (env var or source_config['api_key'])",
                retryable=False,
            )

        payload = {"url": url, "formats": ["markdown"]}
        headers = {"Authorization": f"Bearer {api_key}"}

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(FIRECRAWL_ENDPOINT, json=payload, headers=headers)
        except httpx.TimeoutException as e:
            raise ConnectorError(f"Firecrawl timed out after {timeout}s for {url}", retryable=True) from e
        except httpx.ConnectError as e:
            raise ConnectorError(f"Could not connect to Firecrawl: {e}", retryable=True) from e

        if response.status_code == 401:
            raise ConnectorError("Firecrawl API key rejected (401)", retryable=False)
        if response.status_code >= 400:
            raise ConnectorError(
                f"Firecrawl returned HTTP {response.status_code}: {response.text[:200]}",
                retryable=response.status_code >= 500,
            )

        data = response.json()
        result = data.get("data", {})
        markdown = result.get("markdown", "")
        metadata = result.get("metadata", {})

        return [{
            "_source_type": self.type_name,
            "source_name": metadata.get("sourceURL", url),
            "url": metadata.get("sourceURL", url),
            "title": metadata.get("title", url),
            "content": markdown[:20_000],
            "published_at": metadata.get("publishedTime"),
        }]
