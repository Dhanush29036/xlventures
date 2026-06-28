from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from app.api.auth import get_current_tenant
import json

from app.agents.intent_parser import IntentParser, WorkflowPlan

router = APIRouter(tags=["Studio"])

class AgentDefinition(BaseModel):
    agent_id: str
    name: str
    description: str
    capabilities: list[str]
    required_inputs: list[str]
    outputs: list[str]
    typical_duration_seconds: int
    is_core: bool
    compatible_with: list[str]
    icon: str

AGENT_REGISTRY = [
    AgentDefinition(
        agent_id="trigger_monitor",
        name="Trigger Monitor",
        description="Monitors web and market sources for business signals matching your ICP — funding rounds, job postings, leadership changes, product launches",
        capabilities=["funding_signals", "hiring_signals", "news_monitoring", "rss_scraping"],
        required_inputs=["trigger_keywords", "date_range"],
        outputs=["signal_list"],
        typical_duration_seconds=45,
        is_core=True,
        compatible_with=["company_icp_agent"],
        icon="ti-radar"
    ),
    AgentDefinition(
        agent_id="company_icp_agent",
        name="ICP Scorer",
        description="Scores companies against your Ideal Customer Profile using headcount, funding stage, industry, tech stack, and growth signals",
        capabilities=["icp_scoring", "company_enrichment", "clearbit_lookup", "apollo_enrichment"],
        required_inputs=["icp_rules", "company_list_or_signals"],
        outputs=["scored_companies"],
        typical_duration_seconds=60,
        is_core=True,
        compatible_with=["validation_agent", "persona_finder"],
        icon="ti-building"
    ),
    AgentDefinition(
        agent_id="validation_agent",
        name="Validation Agent",
        description="Cross-validates company data across multiple sources, flags conflicts, and assigns confidence scores to every data point",
        capabilities=["cross_source_validation", "confidence_scoring", "conflict_detection"],
        required_inputs=["scored_companies"],
        outputs=["validated_companies"],
        typical_duration_seconds=30,
        is_core=False,
        compatible_with=["company_icp_agent", "persona_finder"],
        icon="ti-shield-check"
    ),
    AgentDefinition(
        agent_id="persona_finder",
        name="Persona Finder",
        description="Identifies key decision-makers at target companies based on configurable title patterns, seniority level, and org-chart depth",
        capabilities=["linkedin_search", "title_matching", "org_chart_analysis", "seniority_scoring"],
        required_inputs=["validated_companies", "target_personas"],
        outputs=["decision_makers"],
        typical_duration_seconds=90,
        is_core=True,
        compatible_with=["contact_enrichment"],
        icon="ti-users"
    ),
    AgentDefinition(
        agent_id="contact_enrichment",
        name="Contact Enrichment",
        description="Resolves email addresses, phone numbers, and LinkedIn profiles for identified decision-makers using Hunter.io, Proxycurl, and Datagma",
        capabilities=["email_resolution", "phone_resolution", "linkedin_enrichment", "email_verification"],
        required_inputs=["decision_makers"],
        outputs=["enriched_contacts"],
        typical_duration_seconds=120,
        is_core=True,
        compatible_with=["summary_agent"],
        icon="ti-mail"
    ),
    AgentDefinition(
        agent_id="summary_agent",
        name="Summary & Recommendations",
        description="Synthesizes all findings into an actionable report with ranked companies, contact priority scores, and recommended outreach next actions",
        capabilities=["synthesis", "ranking", "action_recommendation", "report_generation"],
        required_inputs=["enriched_contacts", "validated_companies"],
        outputs=["final_report"],
        typical_duration_seconds=20,
        is_core=True,
        compatible_with=[],
        icon="ti-report-analytics"
    ),
]


class IntentRequest(BaseModel):
    prompt: str
    context: dict | None = None


@router.post("/studio/parse-intent", response_model=WorkflowPlan)
async def parse_intent(
    body: IntentRequest,
    tenant_id: str = Depends(get_current_tenant)
) -> WorkflowPlan:
    parser = IntentParser()
    return await parser.parse(body.prompt, body.context)


class ExecuteRequest(BaseModel):
    workflow_plan: WorkflowPlan
    selected_agent_ids: list[str]
    overrides: dict | None = None
    max_companies: int = 20


@router.post("/studio/execute")
async def execute_workflow(
    body: ExecuteRequest,
    tenant_id: str = Depends(get_current_tenant)
) -> dict:
    from app.db.session import build_async_engine, build_session_factory
    from app.core.config import get_settings
    from sqlalchemy import insert, select, text
    import uuid
    
    settings = get_settings()
    engine = build_async_engine(settings)
    session_factory = build_session_factory(engine)
    
    icp_rules = {}
    if body.workflow_plan.icp_config_extracted:
        icp_rules.update(body.workflow_plan.icp_config_extracted)
    if body.overrides:
        icp_rules.update(body.overrides)
        
    async with session_factory() as session:
        # Save ICP config to DB (create simple structure if missing table setup here)
        icp_id = str(uuid.uuid4())
        await session.execute(
            text("""
                INSERT INTO icp_configs (id, tenant_id, name, rules_json, persona_json)
                VALUES (:id, :tenant, :name, :rules, :persona)
            """),
            {
                "id": icp_id,
                "tenant": tenant_id,
                "name": "Studio Generated Config",
                "rules": json.dumps(icp_rules),
                "persona": json.dumps({})
            }
        )
        
        # Create agent_run row
        run_id = str(uuid.uuid4())
        await session.execute(
            text("""
                INSERT INTO agent_runs (id, tenant_id, icp_config_id, status, max_companies, metadata)
                VALUES (:id, :tenant, :icp, :status, :max_comp, :metadata)
            """),
            {
                "id": run_id,
                "tenant": tenant_id,
                "icp": icp_id,
                "status": "pending",
                "max_comp": body.max_companies,
                "metadata": json.dumps({
                    "original_prompt": body.workflow_plan.intent_summary,
                    "plan": body.workflow_plan.model_dump()
                })
            }
        )
        await session.commit()
    
    # Dispatch to Planner Agent via Celery
    from app.tasks import run_pipeline
    run_pipeline.delay(run_id, tenant_id, icp_rules, body.selected_agent_ids)
    
    return {
        "run_id": run_id,
        "stream_url": f"/api/v1/stream/{run_id}"
    }


@router.get("/studio/agents", response_model=list[AgentDefinition])
async def get_agents(tenant_id: str = Depends(get_current_tenant)):
    return AGENT_REGISTRY


class BuildAgentRequest(BaseModel):
    name: str
    description: str
    inputs: list[str]
    outputs: list[str]
    tools_needed: list[str]

@router.post("/studio/build-custom-agent")
async def build_custom_agent(body: BuildAgentRequest) -> dict:
    import os
    import re
    # Simplified LLM interaction placeholder for building code
    snake_name = re.sub(r'[^a-z0-9]', '_', body.name.lower())
    
    worker_code = f'''
import asyncio
from typing import Dict, Any

async def {snake_name}_agent(inputs: Dict[str, Any]) -> Dict[str, Any]:
    """
    {body.description}
    """
    # Tools needed: {", ".join(body.tools_needed)}
    await asyncio.sleep(2)
    return {{"status": "completed", "result": "mock_data"}}
'''
    worker_path = os.path.join(os.path.dirname(__file__), "..", "..", "agents", "workers")
    os.makedirs(worker_path, exist_ok=True)
    with open(os.path.join(worker_path, f"{snake_name}.py"), "w") as f:
        f.write(worker_code)
        
    new_agent = AgentDefinition(
        agent_id=snake_name,
        name=body.name,
        description=body.description,
        capabilities=body.tools_needed,
        required_inputs=body.inputs,
        outputs=body.outputs,
        typical_duration_seconds=30,
        is_core=False,
        compatible_with=[],
        icon="ti-plug"
    )
    
    return {
        "files_created": [f"app/agents/workers/{snake_name}.py"],
        "agent_definition": new_agent.model_dump()
    }
