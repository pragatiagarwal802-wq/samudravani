"""Compiled LangGraph workflow.

    START -> ocean_agent  --\
    START -> weather_agent --+-> fishing_agent -> route_agent -> risk_agent -> planner_agent -> END

ocean_agent and weather_agent run in the same superstep (in parallel);
fishing_agent waits for both.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from langgraph.graph import END, START, StateGraph

from agents.fishing_agent import make_fishing_agent
from agents.ocean_agent import make_ocean_agent
from agents.planner_agent import planner_agent
from agents.risk_agent import make_risk_agent
from agents.route_agent import make_route_agent
from agents.weather_agent import make_weather_agent
from models.state import VoyageState
from services.config import load_config
from services.data_service import DataService
from services.fishing_service import FishingService
from services.risk_service import RiskService
from services.routing_service import LandMask, NauticalRouter


def build_workflow(data: DataService, land: Optional[LandMask] = None, config: Optional[Dict[str, Any]] = None):
    cfg = config or load_config()
    g = StateGraph(VoyageState)
    g.add_node("ocean_agent", make_ocean_agent(data))
    g.add_node("weather_agent", make_weather_agent(data))
    g.add_node("fishing_agent", make_fishing_agent(FishingService(cfg)))
    g.add_node("route_agent", make_route_agent(NauticalRouter(cfg, land=land)))
    g.add_node("risk_agent", make_risk_agent(RiskService(cfg)))
    g.add_node("planner_agent", planner_agent)

    g.add_edge(START, "ocean_agent")
    g.add_edge(START, "weather_agent")
    g.add_edge(["ocean_agent", "weather_agent"], "fishing_agent")  # join: waits for both
    g.add_edge("fishing_agent", "route_agent")
    g.add_edge("route_agent", "risk_agent")
    g.add_edge("risk_agent", "planner_agent")
    g.add_edge("planner_agent", END)
    return g.compile()
