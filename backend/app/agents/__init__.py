"""Specialised agent registry.

Ten agents, each with a single responsibility, orchestrated by LangGraph in
:mod:`app.agents.graph`.
"""

from app.agents.analysis_agents import CropSuitabilityAgent, KnowledgeRetrievalAgent, MLForecastAgent
from app.agents.base import AgentContext, AgentResult, BaseAgent, evidence_from_measurement, run_coroutine
from app.agents.context_agents import FarmFieldProfileAgent, SoilNutrientAgent, WeatherClimateAgent
from app.agents.decision_agents import (
    ActivityPlannerAgent,
    AdvisoryNarrativeAgent,
    CropRiskAdvisoryAgent,
    IrrigationAgent,
)
from app.agents.graph import (
    AGENT_ORDER,
    SensorTelemetryAgent,
    TelemetryBridgeAgent,
    agent_catalogue,
    build_graph,
    get_graph,
    run_workflow,
)

__all__ = [
    "AGENT_ORDER",
    "ActivityPlannerAgent",
    "AdvisoryNarrativeAgent",
    "AgentContext",
    "AgentResult",
    "BaseAgent",
    "CropRiskAdvisoryAgent",
    "CropSuitabilityAgent",
    "FarmFieldProfileAgent",
    "IrrigationAgent",
    "KnowledgeRetrievalAgent",
    "MLForecastAgent",
    "SensorTelemetryAgent",
    "SoilNutrientAgent",
    "TelemetryBridgeAgent",
    "WeatherClimateAgent",
    "agent_catalogue",
    "build_graph",
    "evidence_from_measurement",
    "get_graph",
    "run_coroutine",
    "run_workflow",
]
