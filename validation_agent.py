"""
Validation Agent
----------------
Cross-checks company data for consistency, flags conflicts, and produces
a confidence score. Integrates with MemoryManager to skip already-processed
companies and persist results after validation.

Usage (called by Planner via LangGraph):
    result = await run_validation_agent(company_data, memory_manager, tenant_id)
"""

import json
import logging
from dataclasses import dataclass, field, asdict
from typing import Optional
from anthropic import AsyncAnthropic

logger = logging.getLogger(__name__)
client = AsyncAnthropic()

# ── Data models ──────────────────────────────────────────────────────────────

@dataclass
class CompanyInput:
    domain: str
    name: str
    industry: Optional[str] = None
    employee_count: Optional[int] = None
    funding_stage: Optional[str] = None
    hq_location: Optional[str] = None
    description: Optional[str] = None
    raw_text: Optional[str] = None   # free-form paste from Trigger Monitor


@dataclass
class ValidationResult:
    domain: str
    verdict: str                    # "VALID" | "NEEDS_REVIEW" | "INVALID"
    confidence: int                 # 0-100
    verified_fields: list[str] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)
    enrichment_notes: str = ""
    skipped: bool = False           # True if MemoryManager said already processed


# ── System prompt ─────────────────────────────────────────────────────────────

VALIDATION_SYSTEM_PROMPT = """You are a Validation Agent in a B2B prospect intelligence pipeline.

Your job:
1. Cross-check the company data for internal consistency and completeness.
2. Flag any conflicts (e.g. headcount vs funding stage mismatch, suspicious domain).
3. Identify which fields are verified vs missing.
4. Assign a confidence score (0-100) based on data quality.
5. Give a verdict: VALID (score ≥ 70), NEEDS_REVIEW (40-69), or INVALID (< 40).

Respond ONLY with raw JSON — no markdown, no explanation:
{
  "confidence": <integer 0-100>,
  "verdict": "VALID" | "NEEDS_REVIEW" | "INVALID",
  "verified_fields": ["field1", "field2", ...],
  "flags": ["issue description", ...],
  "enrichment_notes": "<one sentence on overall data quality>"
}"""


# ── Core agent ────────────────────────────────────────────────────────────────

async def run_validation_agent(
    company: CompanyInput,
    memory_manager=None,    # MemoryManager instance from Dhanush's layer
    tenant_id: str = "default",
) -> ValidationResult:
    """
    Main entry point called by the Planner Agent.
    Checks memory first, then runs Claude-powered validation.
    """

    # 1. Check if already processed (Redis → Neo4j fallback per memory arch)
    if memory_manager is not None:
        try:
            should_skip = await memory_manager.should_skip_company(
                tenant_id=tenant_id,
                domain=company.domain,
            )
            if should_skip:
                logger.info(f"[ValidationAgent] Skipping {company.domain} — already in memory")
                return ValidationResult(
                    domain=company.domain,
                    verdict="VALID",
                    confidence=100,
                    skipped=True,
                    enrichment_notes="Previously validated — pulled from memory.",
                )
        except Exception as e:
            logger.warning(f"[ValidationAgent] MemoryManager check failed: {e} — proceeding anyway")

    # 2. Build user message
    user_msg = _build_user_message(company)

    # 3. Call Claude
    try:
        response = await client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1000,
            system=VALIDATION_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_msg}],
        )
        raw = response.content[0].text.strip()
        parsed = json.loads(raw)
    except json.JSONDecodeError as e:
        logger.error(f"[ValidationAgent] Bad JSON from Claude: {e}\nRaw: {raw}")
        return ValidationResult(
            domain=company.domain,
            verdict="NEEDS_REVIEW",
            confidence=0,
            flags=["Claude returned malformed JSON — manual review required"],
        )
    except Exception as e:
        logger.error(f"[ValidationAgent] API error: {e}")
        raise

    # 4. Build result
    result = ValidationResult(
        domain=company.domain,
        verdict=parsed.get("verdict", "NEEDS_REVIEW"),
        confidence=int(parsed.get("confidence", 50)),
        verified_fields=parsed.get("verified_fields", []),
        flags=parsed.get("flags", []),
        enrichment_notes=parsed.get("enrichment_notes", ""),
    )

    logger.info(
        f"[ValidationAgent] {company.domain} → {result.verdict} "
        f"(confidence={result.confidence})"
    )
    return result


# ── Helpers ───────────────────────────────────────────────────────────────────

def _build_user_message(company: CompanyInput) -> str:
    parts = [f"Company domain: {company.domain}", f"Name: {company.name}"]
    if company.industry:
        parts.append(f"Industry: {company.industry}")
    if company.employee_count:
        parts.append(f"Employee count: {company.employee_count}")
    if company.funding_stage:
        parts.append(f"Funding stage: {company.funding_stage}")
    if company.hq_location:
        parts.append(f"HQ: {company.hq_location}")
    if company.description:
        parts.append(f"Description: {company.description}")
    if company.raw_text:
        parts.append(f"\nAdditional raw text:\n{company.raw_text}")
    return "\n".join(parts)


def validation_result_to_dict(result: ValidationResult) -> dict:
    """Serialise for passing to PersonaFinder or MemoryManager."""
    return asdict(result)
