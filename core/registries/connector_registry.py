"""
core/registries/connector_registry.py

Simple name -> connector-instance lookup. Deliberately dumb: registries
in this platform aren't supposed to contain logic, just registration
and lookup. Keeping them dumb is what makes them trustworthy plumbing.
"""

from typing import Any

from core.connectors.base_connector import BaseConnector


class ConnectorRegistry:
    def __init__(self):
        self._connectors: dict[str, BaseConnector] = {}

    def register(self, connector: BaseConnector) -> None:
        if not connector.type_name or connector.type_name == "base":
            raise ValueError("Connector must declare a real type_name before registering.")
        self._connectors[connector.type_name] = connector

    def get(self, type_name: str) -> BaseConnector:
        if type_name not in self._connectors:
            raise KeyError(
                f"No connector registered for type '{type_name}'. "
                f"Available: {list(self._connectors.keys())}"
            )
        return self._connectors[type_name]

    def list_types(self) -> list[str]:
        return list(self._connectors.keys())


def build_default_connector_registry() -> "ConnectorRegistry":
    """
    Convenience factory: registers all four connector types named in the
    project brief (RSS, Website, Search, Firecrawl). Search/Firecrawl will
    raise a clear ConnectorError at fetch-time if their API keys aren't
    set — they don't fail at registration time, since you may only need
    RSS + Website for a given workflow.
    """
    from core.connectors.rss_connector import RSSConnector
    from core.connectors.website_connector import WebsiteConnector
    from core.connectors.search_connector import SearchConnector
    from core.connectors.firecrawl_connector import FirecrawlConnector

    registry = ConnectorRegistry()
    registry.register(RSSConnector())
    registry.register(WebsiteConnector())
    registry.register(SearchConnector())
    registry.register(FirecrawlConnector())
    return registry
