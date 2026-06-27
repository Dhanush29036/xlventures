"""
Contact Enrichment Agent
------------------------
Takes personas from PersonaFinder and resolves contact details.
After human approval, calls memory_manager.record_company_enriched() which
triggers parallel writes (asyncio.gather) to:
    - PostgreSQL  → audit_log, agent_runs
    - Redis DB0   → processed:{tenant_id} Set, episodic:runs List (with TTL)
    - Neo4j       → Upsert Company, Person nodes; create EMPLOYS, HAS_SIGNAL, TARGETS links
    - Qdrant      → Generate embedding (text-embedding-3-small, size 1536), upsert to
                    'companies' collection with headcount + funding_stage payload

HITL flow (per project spec):
    - pipeline.py sets human_approved=False initially
    - Planner writes to PostgreSQL hitl_queue table
    - UI surfaces approval prompt
    - On approve: pipeline re-called with human_approved=True
    - This agent then runs + persists

In production: replace _mock_enrich_via_tools() with real Hunter.io /
Proxycurl / Datagma API calls.

Usage:
    result = await run_contact_enrichment(company, persona_result,
                                          validation_result, memory_manager,
                                          tenant_id, human_approved)
"""

import json
import logging
from dataclasses import dataclass, field, asdict
from typing import Optional
from anthropic import AsyncAnthropic

from validation_agent import CompanyInput, ValidationResult
from persona_finder_agent import PersonaFinderResult, Persona

logger = logging.getLogger(__name__)
client = AsyncAnthropic()


# ── Data models ───────────────────────────────────────────────────────────────

@dataclass
class EnrichedContact:
    name: str
    title: str
    email: str
    phone: str
    linkedin_url: str
    source: str             # "Hunter.io" | "Proxycurl" | "Datagma"
    confidence: int         # 0-100
    department: str = ""
    seniority: str = ""
    org_depth: int = 2


@dataclass
class ContactEnrichmentResult:
    domain: str
    contacts: list[EnrichedContact] = field(default_factory=list)
    enrichment_summary: str = ""
    persisted_to_memory: bool = False
    hitl_queued: bool = False       # True if written to PostgreSQL hitl_queue


# ── System prompt ─────────────────────────────────────────────────────────────

ENRICHMENT_SYSTEM_PROMPT = """You are a Contact Enrichment Agent in a B2B prospect intelligence pipeline.

Given a company and target personas, generate the most realistic enriched
contact record for each persona — simulating what Hunter.io, Proxycurl, and
Datagma would return.

Rules:
- Use the company domain to infer the email pattern (e.g. first.last@domain.com)
- Phone numbers should match the HQ country/region format
- LinkedIn slug format: firstname-lastname + short hash (e.g. sarah-chen-4b2a)
- Assign each contact to the most appropriate enrichment source
- Confidence reflects how findable this seniority level typically is

Output raw JSON only — no markdown:
{
  "contacts": [
    {
      "name": "...",
      "title": "...",
      "email": "...",
      "phone": "...",
      "linkedin_url": "https://linkedin.com/in/...",
      "source": "Hunter.io" | "Proxycurl" | "Datagma",
      "confidence": <integer 0-100>
    }
  ],
  "enrichment_summary": "<one sentence on overall coverage quality>"
}"""


# ── Core agent ────────────────────────────────────────────────────────────────

async def run_contact_enrichment(
    company: CompanyInput,
    persona_result: PersonaFinderResult,
    validation_result: Optional[ValidationResult] = None,
    memory_manager=None,
    tenant_id: str = "default",
    human_approved: bool = False,
) -> ContactEnrichmentResult:
    """
    Main entry point. Requires human_approved=True to run and persist.
    If human_approved=False, writes a HITL record to PostgreSQL hitl_queue
    and returns early — the Planner will surface this to the UI.
    """

    # ── HITL gate ─────────────────────────────────────────────────────────────
    if not human_approved:
        queued = await _queue_hitl(
            memory_manager=memory_manager,
            tenant_id=tenant_id,
            company=company,
            persona_result=persona_result,
        )
        return ContactEnrichmentResult(
            domain=company.domain,
            enrichment_summary="Awaiting human approval before contact enrichment.",
            hitl_queued=queued,
        )

    if not persona_result.personas:
        return ContactEnrichmentResult(
            domain=company.domain,
            enrichment_summary="No personas to enrich.",
        )

    # ── Call Claude ───────────────────────────────────────────────────────────
    user_msg = _build_user_message(company, persona_result)
    try:
        response = await client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1000,
            system=ENRICHMENT_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_msg}],
        )
        raw = response.content[0].text.strip()
        parsed = json.loads(raw)
    except json.JSONDecodeError as e:
        logger.error(f"[ContactEnrichment] Bad JSON from Claude: {e}")
        return ContactEnrichmentResult(
            domain=company.domain,
            enrichment_summary="Enrichment failed — malformed Claude response.",
        )
    except Exception as e:
        logger.error(f"[ContactEnrichment] API error: {e}")
        raise

    # ── Merge persona metadata into contacts ──────────────────────────────────
    contacts = []
    for i, c in enumerate(parsed.get("contacts", [])):
        persona: Optional[Persona] = (
            persona_result.personas[i]
            if i < len(persona_result.personas)
            else None
        )
        contacts.append(EnrichedContact(
            name=c.get("name", ""),
            title=c.get("title", ""),
            email=c.get("email", ""),
            phone=c.get("phone", ""),
            linkedin_url=c.get("linkedin_url", ""),
            source=c.get("source", "Hunter.io"),
            confidence=int(c.get("confidence", 50)),
            department=persona.department if persona else "",
            seniority=persona.seniority if persona else "",
            org_depth=persona.org_depth if persona else 2,
        ))

    result = ContactEnrichmentResult(
        domain=company.domain,
        contacts=contacts,
        enrichment_summary=parsed.get("enrichment_summary", ""),
    )

    # ── Persist to unified memory layer ───────────────────────────────────────
    if memory_manager is not None:
        result.persisted_to_memory = await _persist_to_memory(
            memory_manager=memory_manager,
            tenant_id=tenant_id,
            company=company,
            persona_result=persona_result,
            validation_result=validation_result,
            enrichment_result=result,
        )

    logger.info(
        f"[ContactEnrichment] {company.domain} → {len(contacts)} contacts, "
        f"persisted={result.persisted_to_memory}"
    )
    return result


# ── HITL queue ────────────────────────────────────────────────────────────────

async def _queue_hitl(
    memory_manager,
    tenant_id: str,
    company: CompanyInput,
    persona_result: PersonaFinderResult,
) -> bool:
    """
    Write a pending approval record to PostgreSQL hitl_queue table.
    Schema inferred from architecture: hitl_queue stores pending human decisions.
    """
    if memory_manager is None:
        logger.warning("[ContactEnrichment] No memory_manager — HITL not queued")
        return False
    try:
        repo = getattr(memory_manager, "repo", None)
        if repo is None:
            return False

        # Adjust to match Dhanush's actual BaseRepository / hitl_queue schema
        await repo.insert(
            table="hitl_queue",
            data={
                "tenant_id": tenant_id,
                "domain": company.domain,
                "company_name": company.name,
                "persona_count": len(persona_result.personas),
                "icp_match_score": persona_result.icp_match_score,
                "status": "pending",
                "payload": json.dumps({
                    "company": asdict(company) if hasattr(company, '__dataclass_fields__') else {},
                    "personas": [asdict(p) for p in persona_result.personas],
                }),
            },
        )
        logger.info(f"[ContactEnrichment] HITL queued for {company.domain}")
        return True
    except Exception as e:
        logger.error(f"[ContactEnrichment] Failed to queue HITL: {e}")
        return False


# ── Memory persistence ────────────────────────────────────────────────────────

async def _persist_to_memory(
    memory_manager,
    tenant_id: str,
    company: CompanyInput,
    persona_result: PersonaFinderResult,
    validation_result: Optional[ValidationResult],
    enrichment_result: "ContactEnrichmentResult",
) -> bool:
    """
    Calls memory_manager.record_company_enriched() which per the architecture
    triggers asyncio.gather() across all 4 backends:

    PostgreSQL  → append to audit_log
    Redis DB0   → SADD processed:{tenant_id}, LPUSH episodic:runs (with TTL)
    Neo4j       → MERGE Company node, CREATE Person nodes,
                  link EMPLOYS + HAS_SIGNAL + TARGETS relationships
    Qdrant      → generate text-embedding-3-small (1536-dim),
                  upsert to 'companies' collection with payload:
                  {headcount, funding_stage, icp_score, tenant_id}
    """
    try:
        await memory_manager.record_company_enriched(
            tenant_id=tenant_id,
            domain=company.domain,
            company_name=company.name,
            industry=company.industry,
            employee_count=company.employee_count,
            funding_stage=company.funding_stage,
            hq_location=company.hq_location,
            description=company.description,
            # Personas → Neo4j Person nodes via EMPLOYS edges
            personas=[asdict(p) for p in persona_result.personas],
            # Contacts → Neo4j Person nodes with contact fields
            contacts=[asdict(c) for c in enrichment_result.contacts],
            # ICP score → Qdrant payload metadata
            icp_match_score=persona_result.icp_match_score,
            # Validation context → audit_log
            validation_verdict=(
                validation_result.verdict if validation_result else None
            ),
            validation_confidence=(
                validation_result.confidence if validation_result else None
            ),
            enrichment_summary=enrichment_result.enrichment_summary,
        )
        logger.info(f"[ContactEnrichment] Persisted {company.domain} to all memory backends")
        return True
    except Exception as e:
        logger.error(f"[ContactEnrichment] record_company_enriched failed: {e}")
        return False


# ── Helpers ───────────────────────────────────────────────────────────────────

def _build_user_message(company: CompanyInput, persona_result: PersonaFinderResult) -> str:
    persona_lines = "\n".join(
        f"  {i+1}. {p.title} ({p.seniority}, {p.department}, L{p.org_depth})"
        for i, p in enumerate(persona_result.personas)
    )
    return (
        f"Company: {company.name}\n"
        f"Domain: {company.domain}\n"
        f"HQ: {company.hq_location or 'Unknown'}\n"
        f"Industry: {company.industry or 'Unknown'}\n"
        f"Employees: {company.employee_count or 'Unknown'}\n"
        f"Funding: {company.funding_stage or 'Unknown'}\n\n"
        f"Target personas to enrich:\n{persona_lines}"
    )


def contact_result_to_dict(result: "ContactEnrichmentResult") -> dict:
    return asdict(result)
