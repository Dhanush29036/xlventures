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

logger = structlog.get_logger(__name__)
settings = get_settings()

async def _run_pipeline_async(run_id: str, tenant_id: str, icp_config: dict):
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
        from scripts.seed_demo_data import COMPANIES
        
        # Update run status to running
        await run_repo.update(uuid.UUID(run_id), status="running")
        
        custom_domain = icp_config.get("company_domain")
        if custom_domain:
            company_name = custom_domain.split(".")[0].capitalize()
            companies_to_run = [{
                "domain": custom_domain,
                "name": company_name,
                "headcount": 120,
                "funding_stage": "Series B",
                "industry": "SaaS",
                "hq_country": "US",
                "annual_revenue_usd": 15_000_000,
                "tech_stack": ["Python", "AWS", "React"],
                "icp_score": 0.85,
                "recommended_action": "outreach",
                "people": [
                    {"email": f"cto@{custom_domain}", "name": "Jane Doe", "title": "CTO", "seniority": "C-Suite", "is_decision_maker": True},
                    {"email": f"vpe@{custom_domain}", "name": "John Doe", "title": "VP Engineering", "seniority": "VP", "is_decision_maker": True},
                ],
                "signals": [
                    {"type": "funding_round", "score": 0.85, "data": {"stage": "Series B", "amount_usd": 20_000_000}},
                ],
            }]
        else:
            companies_to_run = COMPANIES

        # Execute the planner for each company
        for company in companies_to_run:
            company_data = {
                "domain": company["domain"],
                "name": company["name"],
                "headcount": company["headcount"],
                "funding_stage": company["funding_stage"],
                "industry": company["industry"],
                "hq_country": company["hq_country"],
                "annual_revenue_usd": company.get("annual_revenue_usd", 0),
                "tech_stack": company.get("tech_stack", []),
            }
            people = []
            for p in company.get("people", []):
                person = dict(p)
                person["company_domain"] = company["domain"]
                people.append(person)

            await planner.run(
                tenant_id=tenant_id,
                domain=company["domain"],
                company_data=company_data,
                icp_config=icp_config,
                people=people,
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
def run_pipeline(run_id: str, tenant_id: str, icp_config: dict):
    asyncio.run(_run_pipeline_async(run_id, tenant_id, icp_config))
