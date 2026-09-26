"""Risk agent: worst-case sensor readings over the window evaluated by RiskService rules."""
from __future__ import annotations

from models.state import VoyageState
from services.risk_service import RiskService


def make_risk_agent(service: RiskService):
    def risk_agent(state: VoyageState) -> dict:
        results = list(state.get("ocean_results", [])) + list(state.get("weather_results", []))
        assessment = service.assess(service.worst_case_readings(results))
        return {"risk": assessment, "trace": [f"risk_agent: {assessment.verdict.value}"]}

    return risk_agent
