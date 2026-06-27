"""
core/connectors/website_connector.py

Fetches a single webpage and extracts readable text. Uses httpx for the
HTTP call (async-native, unlike requests) and BeautifulSoup for parsing
(per your tech stack). This is the simplest connector — one URL in,
one normalized record out — but still goes through the same timeout /
retryable-error contract as every other connector.
"""

from typing import Any

import httpx
from bs4 import BeautifulSoup

from core.connectors.base_connector import BaseConnector, ConnectorError


class WebsiteConnector(BaseConnector):
    type_name = "website"
    required_fields = ("url",)
    default_timeout_seconds = 15.0

    # Tags that are never article content — stripped before extracting text.
    _NOISE_TAGS = ("script", "style", "nav", "footer", "header", "aside", "form", "noscript")

    async def fetch(self, source_config: dict[str, Any]) -> list[dict[str, Any]]:
        self.validate_config(source_config)
        url = source_config["url"]
        timeout = source_config.get("timeout_seconds", self.default_timeout_seconds)

        try:
            async with httpx.AsyncClient(
                timeout=timeout,
                follow_redirects=True,
                headers={"User-Agent": "Mozilla/5.0 (compatible; AgenticPlatformBot/1.0)"},
            ) as client:
                response = await client.get(url)
        except httpx.TimeoutException as e:
            raise ConnectorError(f"Website fetch timed out after {timeout}s for {url}", retryable=True) from e
        except httpx.ConnectError as e:
            raise ConnectorError(f"Could not connect to {url}: {e}", retryable=True) from e

        if response.status_code >= 400:
            raise ConnectorError(
                f"Website {url} returned HTTP {response.status_code}",
                retryable=response.status_code >= 500,
            )

        soup = BeautifulSoup(response.text, "html.parser")

        for tag in soup(self._NOISE_TAGS):
            tag.decompose()

        title = soup.title.string.strip() if soup.title and soup.title.string else url
        text = " ".join(soup.get_text(separator=" ").split())  # collapse whitespace

        return [{
            "_source_type": self.type_name,
            "source_name": _domain_from_url(url),
            "url": url,
            "title": title,
            "content": text[:20_000],   # cap to keep downstream LLM calls sane
            "published_at": None,        # raw HTML rarely has reliable publish dates
        }]


def _domain_from_url(url: str) -> str:
    try:
        from urllib.parse import urlparse
        return urlparse(url).netloc or url
    except Exception:
        return url
