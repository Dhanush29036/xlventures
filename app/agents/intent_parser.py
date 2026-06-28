from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any

class WorkflowPlan(BaseModel):
    intent_summary: str = Field(..., description="Summary of the user's intent")
    recommended_agents: list[str] = Field(..., description="List of recommended agent IDs")
    icp_config_extracted: dict | None = Field(None, description="Any extracted ICP rules")
    suggested_steps: list[str] = Field(..., description="Steps the workflow will take")

class IntentParser:
    """
    Parses natural language prompts to generate an Agent Studio workflow plan.
    """
    def __init__(self):
        pass

    async def parse(self, prompt: str, context: dict | None = None) -> WorkflowPlan:
        # Since we're using a mock/simple implementation for the purpose of the platform check
        # In a real setup, this would call claude-3-5-sonnet to parse the intent.
        
        prompt_lower = prompt.lower()
        recommended_agents = ["company_icp_agent"]
        icp_rules = {}
        
        if "monitor" in prompt_lower or "news" in prompt_lower or "signals" in prompt_lower:
            recommended_agents.insert(0, "trigger_monitor")
            
        if "validate" in prompt_lower or "confidence" in prompt_lower:
            recommended_agents.append("validation_agent")
            
        if "persona" in prompt_lower or "decision maker" in prompt_lower or "vp" in prompt_lower or "director" in prompt_lower:
            recommended_agents.append("persona_finder")
            
        if "contact" in prompt_lower or "email" in prompt_lower or "phone" in prompt_lower:
            recommended_agents.append("contact_enrichment")
            
        if "report" in prompt_lower or "summary" in prompt_lower:
            recommended_agents.append("summary_agent")

        # Mock extracting some ICP rules
        if "series" in prompt_lower or "funding" in prompt_lower:
            icp_rules["funding_stage"] = "Series A/B"
        if "headcount" in prompt_lower or "employees" in prompt_lower:
            icp_rules["min_headcount"] = 50

        steps = [f"Run {agent_id}" for agent_id in recommended_agents]

        return WorkflowPlan(
            intent_summary=f"Parsed workflow to execute: {', '.join(recommended_agents)}",
            recommended_agents=recommended_agents,
            icp_config_extracted=icp_rules,
            suggested_steps=steps
        )
