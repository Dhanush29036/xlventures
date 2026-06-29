"""
app/agents/web_enricher.py

Real-World Company Data Enricher
─────────────────────────────────
Collects live data about a company by:
  1. Fetching the company's website via httpx
  2. Parsing HTML with stdlib (no BeautifulSoup needed)
  3. Searching DuckDuckGo Lite for recent news/signals (no API key)
  4. If OpenAI key available, uses gpt-4o-mini for smarter extraction

Returns an enriched company_data dict merged with any seed data provided.
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any

import httpx
import structlog

logger = structlog.get_logger(__name__)

# Browser-like headers to avoid bot blocks
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# Tech stack keyword detection
TECH_KEYWORDS = [
    "React", "Vue", "Angular", "Next.js", "TypeScript", "JavaScript", "Python",
    "Go", "Rust", "Java", "Kotlin", "Swift", "Ruby", "PHP", "Node.js",
    "AWS", "Azure", "GCP", "Google Cloud", "Kubernetes", "Docker", "Terraform",
    "PostgreSQL", "MySQL", "MongoDB", "Redis", "Elasticsearch", "Kafka",
    "Stripe", "Twilio", "Salesforce", "HubSpot", "Shopify",
    "GraphQL", "REST API", "gRPC", "microservices", "serverless",
]

# Headcount hint patterns (look for employee/team size mentions)
HEADCOUNT_PATTERNS = [
    r"(\d[\d,]+)\s*(?:employees?|team members?|people|staff)",
    r"(?:team of|over|more than)\s*(\d[\d,]+)",
    r"(\d+)\+\s*employees?",
]

# Funding stage patterns
FUNDING_PATTERNS = {
    "Seed": r"\bseed\s+(?:round|funding|stage)\b",
    "Series A": r"\bseries\s+a\b",
    "Series B": r"\bseries\s+b\b",
    "Series C": r"\bseries\s+c\b",
    "Series D": r"\bseries\s+d\b",
    "Pre-Seed": r"\bpre.?seed\b",
    "IPO": r"\bip[oe]\b|\bpublic(?:ly listed)?\b",
    "Bootstrapped": r"\bbootstrapped\b|\bprofitable\b",
}


def _strip_html(html: str) -> str:
    """Remove HTML tags and normalise whitespace."""
    # Remove scripts, styles, and their content
    html = re.sub(r"<script[^>]*>.*?</script>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<style[^>]*>.*?</style>", " ", html, flags=re.DOTALL | re.IGNORECASE)
    # Remove HTML comments
    html = re.sub(r"<!--.*?-->", " ", html, flags=re.DOTALL)
    # Remove tags
    text = re.sub(r"<[^>]+>", " ", html)
    # Normalise whitespace
    return " ".join(text.split())


def _extract_meta(html: str, name: str) -> str:
    """Extract meta tag content by name or property."""
    pattern = rf'<meta[^>]+(?:name|property)=["\'](?:og:)?{re.escape(name)}["\'][^>]+content=["\']([^"\']+)["\']'
    m = re.search(pattern, html, re.IGNORECASE)
    if m:
        return m.group(1).strip()
    # Try reversed attribute order
    pattern2 = rf'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:name|property)=["\'](?:og:)?{re.escape(name)}["\']'
    m2 = re.search(pattern2, html, re.IGNORECASE)
    return m2.group(1).strip() if m2 else ""


def _extract_title(html: str) -> str:
    m = re.search(r"<title[^>]*>([^<]+)</title>", html, re.IGNORECASE)
    return m.group(1).strip() if m else ""


def _detect_tech_stack(text: str) -> list[str]:
    found = []
    lower = text.lower()
    for tech in TECH_KEYWORDS:
        if tech.lower() in lower:
            found.append(tech)
    return list(dict.fromkeys(found))  # dedupe preserving order


def _detect_headcount(text: str) -> int | None:
    for pattern in HEADCOUNT_PATTERNS:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            raw = m.group(1).replace(",", "")
            try:
                return int(raw)
            except ValueError:
                pass
    return None


def _detect_funding_stage(text: str) -> str:
    lower = text.lower()
    for stage, pattern in FUNDING_PATTERNS.items():
        if re.search(pattern, lower):
            return stage
    return ""


def _detect_open_roles(text: str) -> list[str]:
    """Detect job/hiring signals from text."""
    roles: list[str] = []
    patterns = [
        r"(?:we['\u2019]re|we are)\s+hiring\s+([A-Z][^\.\n,]{3,40})",
        r"(?:open|current)\s+(?:positions?|roles?|jobs?)[:\-\s]+([A-Z][^\.\n,]{3,40})",
        r"join our team as (?:a |an )?([A-Z][^\.\n,]{3,40})",
    ]
    for pat in patterns:
        for m in re.finditer(pat, text):
            role = m.group(1).strip()
            if len(role) < 60:
                roles.append(role)
    return roles[:5]  # cap at 5


async def _fetch_website(domain: str) -> tuple[str, str]:
    """Fetch website HTML. Returns (html, final_url)."""
    urls = [f"https://{domain}", f"https://www.{domain}"]
    async with httpx.AsyncClient(follow_redirects=True, timeout=12.0, headers=_HEADERS) as client:
        for url in urls:
            try:
                resp = await client.get(url)
                if resp.status_code == 200:
                    return resp.text, str(resp.url)
            except Exception:
                continue
    return "", ""


async def _search_ddg_news(query: str) -> list[str]:
    """Search DuckDuckGo Lite for recent news. No API key needed."""
    results: list[str] = []
    try:
        encoded = query.replace(" ", "+")
        url = f"https://lite.duckduckgo.com/lite/?q={encoded}&df=m"  # last month
        async with httpx.AsyncClient(follow_redirects=True, timeout=10.0, headers=_HEADERS) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                text = _strip_html(resp.text)
                # Extract snippets (DDG lite results are plain text between | separators)
                snippets = [s.strip() for s in text.split("|") if len(s.strip()) > 30]
                results = snippets[:6]
    except Exception:
        pass
    return results


async def _enrich_with_openai(
    domain: str,
    website_text: str,
    existing: dict[str, Any],
    api_key: str,
) -> dict[str, Any]:
    """Use OpenAI gpt-4o-mini to extract richer structured data."""
    try:
        from openai import AsyncOpenAI  # type: ignore
        client = AsyncOpenAI(api_key=api_key)
        prompt = f"""You are a B2B market research analyst. Based on this website content for {domain}, extract company intelligence.

Website text (first 4000 chars):
{website_text[:4000]}

Return ONLY a JSON object with:
- name: company name
- description: 2-sentence company description
- industry: main industry (e.g. SaaS, Fintech, HealthTech, EdTech, etc.)
- headcount: integer estimate of employee count, or null
- funding_stage: one of Seed/Series A/Series B/Series C/Series D/IPO/Bootstrapped or null
- hq_country: ISO 2-letter country code (US/UK/IN/CA/DE etc), or null
- annual_revenue_usd: integer estimate, or null
- tech_stack: list of technologies/tools they use
- open_roles: list of job title strings if hiring, else []
- recent_news: list of brief news snippets or product announcements"""

        resp = await client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": "Extract business intelligence. Return valid JSON only."},
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
            max_tokens=800,
        )
        extracted: dict[str, Any] = json.loads(resp.choices[0].message.content)
        # Merge: existing non-null values take priority
        merged = dict(extracted)
        for k, v in existing.items():
            if v not in (None, "", 0, [], {}):
                merged[k] = v
        return merged
    except Exception as e:
        logger.warning("openai_enrichment_failed", domain=domain, error=str(e))
        return existing


async def enrich_company_from_web(
    domain: str,
    seed_data: dict[str, Any] | None = None,
    openai_api_key: str = "",
) -> dict[str, Any]:
    """
    Main entry point — fetches real-world data for a domain and returns
    an enriched company_data dict merged with any seed_data provided.

    Parameters
    ----------
    domain:         Company domain (e.g. "acme.com")
    seed_data:      Optional base data (e.g. from DEMO_COMPANIES or ICP config)
    openai_api_key: If provided, uses GPT-4o-mini for smarter extraction
    """
    seed = dict(seed_data or {})
    log = logger.bind(domain=domain)
    log.info("web_enrichment_start")

    # Fetch website and search news in parallel
    html_task = asyncio.create_task(_fetch_website(domain))
    news_task = asyncio.create_task(_search_ddg_news(f"{domain} company funding news 2024 2025"))

    html, final_url = await html_task
    news_snippets = await news_task

    if not html:
        log.warning("web_enrichment_no_html", domain=domain)
        return seed

    # ── Parse website ────────────────────────────────────────────────────────
    page_text = _strip_html(html)[:8000]

    # Company name — meta og:title > <title> > seed
    og_title = _extract_meta(html, "title")
    title_tag = _extract_title(html)
    description_meta = _extract_meta(html, "description") or _extract_meta(html, "og:description")

    name = og_title or title_tag or seed.get("name", domain)
    # Clean up common suffix patterns: "Company | Home", "Company - Products"
    name = re.sub(r"\s*[\|\-–]\s*.+$", "", name).strip()

    tech_stack = _detect_tech_stack(page_text)
    headcount = _detect_headcount(page_text)
    funding_stage = _detect_funding_stage(page_text)
    open_roles = _detect_open_roles(page_text)

    # ── Build enriched data ───────────────────────────────────────────────────
    enriched: dict[str, Any] = {
        "domain": domain,
        "name": name or seed.get("name", domain),
        "description": description_meta or seed.get("description", ""),
        "tech_stack": tech_stack or seed.get("tech_stack", []),
        "headcount": headcount or seed.get("headcount"),
        "funding_stage": funding_stage or seed.get("funding_stage", ""),
        "industry": seed.get("industry", ""),
        "hq_country": seed.get("hq_country", "US"),
        "annual_revenue_usd": seed.get("annual_revenue_usd"),
        "open_roles": open_roles or seed.get("open_roles", []),
        "recent_news": news_snippets[:5] if news_snippets else seed.get("recent_news", []),
        "website_url": final_url or f"https://{domain}",
        "people": seed.get("people", []),
        "signals": seed.get("signals", []),
    }

    # ── If OpenAI available, do a smarter extraction pass ────────────────────
    if openai_api_key:
        enriched = await _enrich_with_openai(domain, page_text, enriched, openai_api_key)

    log.info(
        "web_enrichment_complete",
        name=enriched.get("name"),
        tech_count=len(enriched.get("tech_stack", [])),
        has_news=bool(enriched.get("recent_news")),
        has_roles=bool(enriched.get("open_roles")),
    )
    return enriched
