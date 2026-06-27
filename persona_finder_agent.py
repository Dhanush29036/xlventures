"""
Persona Finder Agent
--------------------
Takes validated company data and identifies the top decision-maker personas
most relevant for B2B outreach.

Neo4j schema (from architecture diagram):
    (Tenant)-[:TARGETS]->(Company)
    (Company)-[:EMPLOYS]->(Person)
    (Company)-[:HAS_SIGNAL]->(Signal)
    (Person)-[:REPORTS_TO]->(Person)

MemoryManager lives at: app/memory/manager.py
    - memory_manager.graph_store  → GraphStore (neo4j async driver)
    - memory_manager.episodic     → EpisodicMemoryStore (Redis DB0)
    - memory_manager.semantic     → SemanticICPStore (Qdrant)
    - memory_manager.repo         → BaseRepository (PostgreSQL / SQLAlchemy)

Usage:
    result = await run_persona_finder(company, validation_result, memory_manager, tenant_id)
"""

import json
import logging
from dataclasses import dataclass, field, asdict
from typing import Optional
from anthropic import AsyncAnthropic

from validation_agent import CompanyInput, ValidationResult

logger = logging.getLogger(__name__)
client = AsyncAnthropic()


# ── Data models ───────────────────────────────────────────────────────────────

@dataclass
class Persona:
    title: str
    seniority: str          # "C-suite" | "VP" | "Director" | "Manager"
    department: str
    why: str
    org_depth: int          # 1=CEO, 2=direct report, 3=their report...


@dataclass
class PersonaFinderResult:
    domain: str
    personas: list[Persona] = field(default_factory=list)
    icp_match_score: int = 0
    recommendation: str = ""
    from_cache: bool = False        # True if pulled from Neo4j (Company)-[:EMPLOYS]->(Person)


# ── System prompt ─────────────────────────────────────────────────────────────

PERSONA_SYSTEM_PROMPT = """You are a Persona Finder Agent in a B2B prospect intelligence pipeline.

Given validated company information, identify the top 3 decision-maker personas
most relevant for B2B outreach. Reason from company size, industry, funding
stage, and typical org-chart patterns.

For each persona:
- title: realistic job title at this company
- seniority: one of C-suite / VP / Director / Manager
- department: which department they lead
- why: one sentence — why are they the economic buyer or key influencer here?
- org_depth: levels from CEO (1=CEO, 2=VP direct report, 3=Director, 4=Manager)

Also output:
- icp_match_score (0-100): how well this company fits a high-value ICP
- recommendation: one concrete next-action for the sales team

Respond ONLY with raw JSON — no markdown, no explanation:
{
  "personas": [
    {
      "title": "...",
      "seniority": "...",
      "department": "...",
      "why": "...",
      "org_depth": <integer>
    }
  ],
  "icp_match_score": <integer 0-100>,
  "recommendation": "..."
}"""


# ── Core agent ────────────────────────────────────────────────────────────────

async def run_persona_finder(
    company: CompanyInput,
    validation: ValidationResult,
    memory_manager=None,
    tenant_id: str = "default",
) -> PersonaFinderResult:
    """
    Main entry point called by the Planner Agent after ValidationAgent.

    Flow:
        1. Bail early if company is INVALID
        2. Check Neo4j for existing (Company)-[:EMPLOYS]->(Person) nodes
        3. If cache miss → call Claude → return result
           (Nodes are written to Neo4j by ContactEnrichment via record_company_enriched)
    """

    # 1. Guard
    if validation.verdict == "INVALID":
        logger.warning(f"[PersonaFinder] Skipping {company.domain} — validation INVALID")
        return PersonaFinderResult(
            domain=company.domain,
            recommendation="Company failed validation — do not proceed.",
        )

    # 2. Try Neo4j cache: (Company {domain})-[:EMPLOYS]->(Person)
    if memory_manager is not None:
        try:
            cached = await _fetch_cached_personas(memory_manager, tenant_id, company.domain)
            if cached:
                logger.info(f"[PersonaFinder] Cache hit for {company.domain} from Neo4j")
                return cached
        except Exception as e:
            logger.warning(f"[PersonaFinder] Neo4j cache lookup failed: {e} — running fresh")

    # 3. Call Claude
    user_msg = _build_user_message(company, validation)
    try:
        response = await client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1000,
            system=PERSONA_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_msg}],
        )
        raw = response.content[0].text.strip()
        parsed = json.loads(raw)
    except json.JSONDecodeError as e:
        logger.error(f"[PersonaFinder] Bad JSON from Claude: {e}")
        return PersonaFinderResult(
            domain=company.domain,
            recommendation="Persona extraction failed — manual review required.",
        )
    except Exception as e:
        logger.error(f"[PersonaFinder] API error: {e}")
        raise

    personas = [
        Persona(
            title=p.get("title", ""),
            seniority=p.get("seniority", ""),
            department=p.get("department", ""),
            why=p.get("why", ""),
            org_depth=int(p.get("org_depth", 2)),
        )
        for p in parsed.get("personas", [])
    ]

    result = PersonaFinderResult(
        domain=company.domain,
        personas=personas,
        icp_match_score=int(parsed.get("icp_match_score", 50)),
        recommendation=parsed.get("recommendation", ""),
    )

    logger.info(
        f"[PersonaFinder] {company.domain} → {len(result.personas)} personas "
        f"(ICP={result.icp_match_score})"
    )
    return result


# ── Neo4j cache lookup ────────────────────────────────────────────────────────

async def _fetch_cached_personas(
    memory_manager,
    tenant_id: str,
    domain: str,
) -> Optional[PersonaFinderResult]:
    """
    Query Neo4j via memory_manager.graph_store for Person nodes already
    linked to this Company.

    Graph pattern used:
        (:Tenant {id: tenant_id})-[:TARGETS]->
        (:Company {domain: domain})-[:EMPLOYS]->
        (:Person)

    Also fetches REPORTS_TO depth to compute org_depth.
    Returns None if no Person nodes exist yet.
    """
    graph_store = getattr(memory_manager, "graph_store", None)
    if graph_store is None:
        return None

    # Cypher: find persons + compute org depth via REPORTS_TO chain length
    query = """
        MATCH (:Tenant {id: $tenant_id})-[:TARGETS]->(c:Company {domain: $domain})
        MATCH (c)-[:EMPLOYS]->(p:Person)
        OPTIONAL MATCH path = (p)-[:REPORTS_TO*]->(ceo:Person)
        WHERE NOT (ceo)-[:REPORTS_TO]->()
        RETURN
            p.title       AS title,
            p.seniority   AS seniority,
            p.department  AS department,
            p.why         AS why,
            coalesce(length(path) + 1, 1) AS org_depth
        ORDER BY org_depth ASC
        LIMIT 5
    """
    try:
        records = await graph_store.query(
            query,
            {"tenant_id": tenant_id, "domain": domain},
        )
    except Exception as e:
        logger.warning(f"[PersonaFinder] graph_store.query failed: {e}")
        return None

    if not records:
        return None

    personas = [
        Persona(
            title=r["title"],
            seniority=r["seniority"],
            department=r["department"],
            why=r.get("why", "Previously identified decision-maker."),
            org_depth=int(r["org_depth"]),
        )
        for r in records
    ]

    return PersonaFinderResult(
        domain=domain,
        personas=personas,
        icp_match_score=75,     # assume qualified if already in graph
        recommendation="Personas loaded from knowledge graph — proceed to contact enrichment.",
        from_cache=True,
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _build_user_message(company: CompanyInput, validation: ValidationResult) -> str:
    lines = [
        f"Company: {company.name} ({company.domain})",
        f"Industry: {company.industry or 'Unknown'}",
        f"Employees: {company.employee_count or 'Unknown'}",
        f"Funding stage: {company.funding_stage or 'Unknown'}",
        f"HQ: {company.hq_location or 'Unknown'}",
        f"Description: {company.description or 'N/A'}",
        "",
        f"Validation verdict: {validation.verdict} ({validation.confidence}% confidence)",
        f"Verified fields: {', '.join(validation.verified_fields) or 'none'}",
    ]
    if validation.flags:
        lines.append(f"Flags: {'; '.join(validation.flags)}")
    return "\n".join(lines)


def persona_result_to_dict(result: PersonaFinderResult) -> dict:
    return asdict(result)
