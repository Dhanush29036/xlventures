import asyncio
import uuid
import structlog
from celery_config import celery_app
from app.core.config import get_settings
from app.db.session import build_async_engine, build_session_factory
from app.memory.episodic import EpisodicMemoryStore
from app.memory.graph import GraphStore
from app.memory.semantic import SemanticICPStore
from app.memory.manager import MemoryManager
from app.agents.planner import PlannerAgent
from app.memory.operational import AgentRunRepository
from app.agents.web_enricher import enrich_company_from_web

logger = structlog.get_logger(__name__)
settings = get_settings()

# ── Inline demo companies (avoids fragile scripts/ module import under Celery) ──
DEMO_COMPANIES = [
    {
        "domain": "acme-saas.io",
        "name": "Acme SaaS",
        "headcount": 150,
        "funding_stage": "Series B",
        "industry": "SaaS",
        "hq_country": "US",
        "annual_revenue_usd": 12_000_000,
        "tech_stack": ["Python", "AWS", "React"],
        "people": [
            {"email": "cto@acme-saas.io", "name": "Alex Chen", "title": "CTO", "seniority": "C-Suite", "is_decision_maker": True},
            {"email": "vpe@acme-saas.io", "name": "Jordan Smith", "title": "VP Engineering", "seniority": "VP", "is_decision_maker": True},
        ],
        "signals": [
            {"type": "funding_round", "score": 0.9, "data": {"stage": "Series B", "amount_usd": 25_000_000}},
        ],
    },
    {
        "domain": "fintech-flow.com",
        "name": "FintechFlow",
        "headcount": 280,
        "funding_stage": "Series C",
        "industry": "Fintech",
        "hq_country": "UK",
        "annual_revenue_usd": 45_000_000,
        "tech_stack": ["Go", "Kubernetes", "PostgreSQL"],
        "people": [
            {"email": "cpo@fintech-flow.com", "name": "Sam Patel", "title": "CPO", "seniority": "C-Suite", "is_decision_maker": True},
        ],
        "signals": [
            {"type": "job_posting", "score": 0.5, "data": {"roles": ["Senior Backend Engineer"]}},
        ],
    },
    {
        "domain": "cloudnative.dev",
        "name": "CloudNative Dev",
        "headcount": 85,
        "funding_stage": "Series A",
        "industry": "Cloud Infrastructure",
        "hq_country": "US",
        "annual_revenue_usd": 5_000_000,
        "tech_stack": ["Rust", "Terraform", "GCP"],
        "people": [
            {"email": "ceo@cloudnative.dev", "name": "Taylor Wong", "title": "CEO", "seniority": "C-Suite", "is_decision_maker": True},
        ],
        "signals": [
            {"type": "tech_adoption", "score": 0.6, "data": {"stack": ["Rust", "Terraform"]}},
        ],
    },
]

async def _run_pipeline_async(run_id: str, tenant_id: str, icp_config: dict, selected_agents: list | None = None):
    # Initialize connection to all 4 stores
    engine = build_async_engine(settings)
    session_factory = build_session_factory(engine)

    episodic_store = EpisodicMemoryStore(
        redis_url=settings.REDIS_URL,
        default_ttl=settings.EPISODIC_TTL_SECONDS,
        max_connections=settings.REDIS_MAX_CONNECTIONS,
    )
    await episodic_store.connect()

    graph_store = GraphStore(
        uri=settings.NEO4J_URI,
        user=settings.NEO4J_USER,
        password=settings.NEO4J_PASSWORD,
        database=settings.NEO4J_DATABASE,
        max_connection_pool_size=settings.NEO4J_MAX_CONNECTION_POOL_SIZE,
    )
    await graph_store.connect()

    semantic_store = SemanticICPStore(
        host=settings.QDRANT_HOST,
        port=settings.QDRANT_PORT,
        grpc_port=settings.QDRANT_GRPC_PORT,
        api_key=settings.QDRANT_API_KEY,
        collection_name=settings.QDRANT_COLLECTION_NAME,
        vector_size=settings.QDRANT_VECTOR_SIZE,
        openai_api_key=settings.OPENAI_API_KEY,
        embedding_model=settings.OPENAI_EMBEDDING_MODEL,
    )
    await semantic_store.connect()

    mm = MemoryManager(
        pg=session_factory,
        redis=episodic_store,
        neo4j=graph_store,
        qdrant=semantic_store,
    )
    
    planner = PlannerAgent(mm)
    run_repo = AgentRunRepository(session_factory)

    try:
        # Update run status to running
        await run_repo.update(uuid.UUID(run_id), status="running")

        # Determine which companies to research
        custom_domain = icp_config.get("company_domain")
        if custom_domain:
            companies_to_run = [
                {"domain": custom_domain, "name": custom_domain.split(".")[0].capitalize()}
            ]
        else:
            companies_to_run = DEMO_COMPANIES

        openai_key = settings.OPENAI_API_KEY or ""

        # Execute the planner for each company
        for company in companies_to_run:
            domain = company["domain"]
            logger.info("enriching_company_from_web", domain=domain, run_id=run_id)

            # ── REAL-WORLD DATA: fetch live website + news ──────────────────
            try:
                enriched_data = await enrich_company_from_web(
                    domain=domain,
                    seed_data=company,  # fallback / merge base
                    openai_api_key=openai_key,
                )
            except Exception as web_err:
                logger.warning("web_enrichment_failed", domain=domain, error=str(web_err))
                enriched_data = dict(company)  # fall back to seed data

            # Build the company_data dict passed into agent state
            company_data = {
                k: enriched_data.get(k, company.get(k))
                for k in [
                    "domain", "name", "headcount", "funding_stage",
                    "industry", "hq_country", "annual_revenue_usd",
                    "tech_stack", "description", "website_url",
                    "open_roles", "recent_news",
                ]
            }

            # Build people list (seed + any from enriched)
            people = []
            for p in (enriched_data.get("people") or company.get("people", [])):
                person = dict(p)
                person["company_domain"] = domain
                people.append(person)

            await planner.run(
                tenant_id=tenant_id,
                domain=domain,
                company_data=company_data,
                icp_config=icp_config,
                people=people,
                selected_agents=selected_agents,
                run_id=run_id,
            )
            
        await run_repo.update(uuid.UUID(run_id), status="completed")
        logger.info("celery_run_completed", run_id=run_id)
        from app.core.events import AgentEventPublisher
        publisher = AgentEventPublisher(episodic_store.client)
        await publisher.publish_run_completed(run_id, {"status": "completed"})

    except Exception as e:
        logger.exception("celery_run_failed", run_id=run_id, error=str(e))
        await run_repo.update(uuid.UUID(run_id), status="failed")
        from app.core.events import AgentEventPublisher
        publisher = AgentEventPublisher(episodic_store.client)
        await publisher.publish_run_failed(run_id, str(e))
    finally:
        await asyncio.gather(graph_store.close(), episodic_store.close(), return_exceptions=True)
        await engine.dispose()

@celery_app.task(name="app.tasks.run_pipeline")
def run_pipeline(run_id: str, tenant_id: str, icp_config: dict, selected_agents: list | None = None):
    asyncio.run(_run_pipeline_async(run_id, tenant_id, icp_config, selected_agents))
