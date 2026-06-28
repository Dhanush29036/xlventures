"""
Neo4j GraphStore — knowledge graph for B2B prospect intelligence.

Node labels : Company | Person | Signal | Tenant
Relationships:
  (Company)-[:EMPLOYS]->(Person)
  (Company)-[:HAS_SIGNAL]->(Signal)
  (Tenant)-[:TARGETS]->(Company)
  (Person)-[:REPORTS_TO]->(Person)

All writes use MERGE + SET for full idempotency.
Indexes on Company.domain and Person.email are created at startup.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import structlog
from neo4j import AsyncDriver, AsyncGraphDatabase, AsyncSession
from neo4j.exceptions import Neo4jError

logger = structlog.get_logger(__name__)


class GraphStore:
    """
    Async Neo4j knowledge graph store.

    Parameters
    ----------
    uri:      Bolt or neo4j+s URI.
    user:     Neo4j username.
    password: Neo4j password.
    database: Target database (default ``neo4j``).
    max_connection_pool_size:
              Driver-level connection pool size.
    """

    def __init__(
        self,
        uri: str | None = None,
        user: str | None = None,
        password: str | None = None,
        database: str = "neo4j",
        max_connection_pool_size: int = 50,
    ) -> None:
        from app.core.config import get_settings
        settings = get_settings()
        self._uri = uri or settings.NEO4J_URI
        self._auth = (user or settings.NEO4J_USER, password or settings.NEO4J_PASSWORD)
        self._database = database or settings.NEO4J_DATABASE
        self._pool_size = max_connection_pool_size or settings.NEO4J_MAX_CONNECTION_POOL_SIZE
        self._driver: AsyncDriver | None = None

    # ── lifecycle ─────────────────────────────────────────────────────────────

    async def connect(self) -> None:
        self._driver = AsyncGraphDatabase.driver(
            self._uri,
            auth=self._auth,
            max_connection_pool_size=self._pool_size,
        )
        await self._driver.verify_connectivity()
        logger.info("graph_store_connected", uri=self._uri)

    async def close(self) -> None:
        if self._driver:
            await self._driver.close()
        logger.info("graph_store_closed")

    @property
    def driver(self) -> AsyncDriver:
        if self._driver is None:
            raise RuntimeError("GraphStore not connected — call connect() first")
        return self._driver

    def _session(self) -> AsyncSession:
        return self.driver.session(database=self._database)

    # ── index creation ────────────────────────────────────────────────────────

    async def create_indexes(self) -> None:
        """
        Idempotent index/constraint creation.  Safe to call on every startup.
        """
        statements = [
            # uniqueness constraints also create backing indexes
            "CREATE CONSTRAINT IF NOT EXISTS FOR (c:Company)  REQUIRE c.domain IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (p:Person)   REQUIRE p.email  IS UNIQUE",
            "CREATE CONSTRAINT IF NOT EXISTS FOR (t:Tenant)   REQUIRE t.tenant_id IS UNIQUE",
            "CREATE INDEX IF NOT EXISTS FOR (s:Signal) ON (s.signal_type)",
            "CREATE INDEX IF NOT EXISTS FOR (s:Signal) ON (s.occurred_at)",
        ]
        async with self._session() as session:
            for stmt in statements:
                await session.run(stmt)
        logger.info("graph_indexes_created")

    # ── upsert helpers ────────────────────────────────────────────────────────

    async def upsert_company(
        self,
        domain: str,
        name: str,
        metadata: dict[str, Any],
    ) -> None:
        """
        MERGE Company node by domain and update all properties atomically.
        """
        log = logger.bind(domain=domain)
        cypher = """
        MERGE (c:Company {domain: $domain})
        SET   c.name     = $name,
              c.metadata = $metadata_json,
              c.updated_at = $updated_at
        """
        params = {
            "domain": domain,
            "name": name,
            "metadata_json": str(metadata),  # stored as string; use apoc for JSON
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        # Store individual metadata fields as node properties for Cypher filtering
        if metadata:
            for k, v in metadata.items():
                if isinstance(v, (str, int, float, bool)):
                    cypher = cypher.rstrip() + f"\nSET c.{k} = ${k}\n"
                    params[k] = v

        async with self._session() as session:
            await session.run(cypher, params)
        log.info("company_upserted", name=name)

    async def upsert_person(
        self,
        email: str,
        name: str,
        title: str,
        company_domain: str,
        metadata: dict[str, Any],
    ) -> None:
        """
        MERGE Person node and create EMPLOYS relationship to Company.
        """
        log = logger.bind(domain=company_domain, email=email)
        cypher = """
        MERGE (p:Person {email: $email})
        SET   p.name     = $name,
              p.title    = $title,
              p.updated_at = $updated_at
        WITH p
        MERGE (c:Company {domain: $company_domain})
        MERGE (c)-[:EMPLOYS]->(p)
        """
        params: dict[str, Any] = {
            "email": email,
            "name": name,
            "title": title,
            "company_domain": company_domain,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        # Attach scalar metadata as node properties
        for k, v in metadata.items():
            if isinstance(v, (str, int, float, bool)):
                cypher = cypher.rstrip() + f"\nSET p.{k} = ${k}\n"
                params[k] = v

        async with self._session() as session:
            await session.run(cypher, params)
        log.info("person_upserted", name=name, title=title)

    async def add_signal(
        self,
        company_domain: str,
        signal_type: str,
        signal_data: dict[str, Any],
        occurred_at: datetime,
    ) -> None:
        """
        MERGE a Signal node keyed by (company_domain, signal_type, occurred_at)
        and attach it to the Company via HAS_SIGNAL.
        """
        log = logger.bind(domain=company_domain, signal_type=signal_type)
        cypher = """
        MERGE (c:Company {domain: $company_domain})
        MERGE (s:Signal {
            company_domain: $company_domain,
            signal_type:    $signal_type,
            occurred_at:    $occurred_at
        })
        SET s.data       = $data_str,
            s.updated_at = $updated_at
        MERGE (c)-[:HAS_SIGNAL]->(s)
        """
        params = {
            "company_domain": company_domain,
            "signal_type": signal_type,
            "occurred_at": occurred_at.isoformat(),
            "data_str": str(signal_data),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        async with self._session() as session:
            await session.run(cypher, params)
        log.info("signal_added")

    async def link_reports_to(
        self, subordinate_email: str, manager_email: str
    ) -> None:
        """Create (subordinate)-[:REPORTS_TO]->(manager) relationship."""
        cypher = """
        MATCH (sub:Person {email: $subordinate_email})
        MATCH (mgr:Person {email: $manager_email})
        MERGE (sub)-[:REPORTS_TO]->(mgr)
        """
        async with self._session() as session:
            await session.run(
                cypher,
                {"subordinate_email": subordinate_email, "manager_email": manager_email},
            )
        logger.info(
            "reports_to_linked",
            subordinate=subordinate_email,
            manager=manager_email,
        )

    async def link_tenant_targets(self, tenant_id: str, company_domain: str) -> None:
        """Create (Tenant)-[:TARGETS]->(Company) relationship."""
        cypher = """
        MERGE (t:Tenant {tenant_id: $tenant_id})
        MERGE (c:Company {domain: $company_domain})
        MERGE (t)-[:TARGETS]->(c)
        """
        async with self._session() as session:
            await session.run(
                cypher,
                {"tenant_id": tenant_id, "company_domain": company_domain},
            )
        logger.info("tenant_targets_linked", tenant_id=tenant_id, domain=company_domain)

    # ── read queries ──────────────────────────────────────────────────────────

    async def get_company_with_people(self, domain: str) -> dict[str, Any]:
        """
        Return company node properties plus a list of employees.
        """
        log = logger.bind(domain=domain)
        cypher = """
        MATCH (c:Company {domain: $domain})
        OPTIONAL MATCH (c)-[:EMPLOYS]->(p:Person)
        OPTIONAL MATCH (c)-[:HAS_SIGNAL]->(s:Signal)
        RETURN c,
               collect(DISTINCT p) AS people,
               collect(DISTINCT s) AS signals
        """
        async with self._session() as session:
            result = await session.run(cypher, {"domain": domain})
            record = await result.single()
            if record is None:
                log.info("company_not_found")
                return {}

            company_node = dict(record["c"])
            people = [dict(p) for p in record["people"] if p is not None]
            signals = [dict(s) for s in record["signals"] if s is not None]

        log.info("company_fetched", people_count=len(people), signals_count=len(signals))
        return {"company": company_node, "people": people, "signals": signals}

    async def find_companies_by_icp(
        self,
        min_headcount: int,
        max_headcount: int,
        funding_stages: list[str],
    ) -> list[dict[str, Any]]:
        """
        Cypher ICP filter — returns matching Company node dicts.
        """
        cypher = """
        MATCH (c:Company)
        WHERE c.headcount >= $min_headcount
          AND c.headcount <= $max_headcount
          AND c.funding_stage IN $funding_stages
        RETURN c
        ORDER BY c.headcount DESC
        LIMIT 500
        """
        params = {
            "min_headcount": min_headcount,
            "max_headcount": max_headcount,
            "funding_stages": funding_stages,
        }
        async with self._session() as session:
            result = await session.run(cypher, params)
            records = await result.data()

        companies = [dict(r["c"]) for r in records]
        logger.info(
            "companies_by_icp_fetched",
            count=len(companies),
            min_headcount=min_headcount,
            max_headcount=max_headcount,
        )
        return companies

    async def company_exists(self, domain: str) -> bool:
        """Return True if a Company node with *domain* exists."""
        cypher = "MATCH (c:Company {domain: $domain}) RETURN count(c) AS cnt"
        async with self._session() as session:
            result = await session.run(cypher, {"domain": domain})
            record = await result.single()
            exists = record is not None and record["cnt"] > 0
        logger.debug("company_exists_check", domain=domain, exists=exists)
        return exists

    # ── health ─────────────────────────────────────────────────────────────────

    async def ping(self) -> bool:
        """Return True if Neo4j is reachable."""
        try:
            async with self._session() as session:
                await session.run("RETURN 1")
            return True
        except Neo4jError:
            return False
