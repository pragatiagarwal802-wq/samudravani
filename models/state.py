"""Shared LangGraph state for the voyage-planning workflow.

The ocean and weather agents run in parallel, so each writes only its own keys.
`warnings` and `trace` are the only keys written by several nodes and use an
appending reducer.
"""
from __future__ import annotations

import operator
from typing import Annotated, List, Optional, TypedDict

from models.schemas import (
    CandidateRoute, FishingResult, ProviderResult, VoyagePlan, VoyageRequest, VoyageRiskAssessment,
)
from services.fields import GriddedField


class VoyageState(TypedDict, total=False):
    request: VoyageRequest

    # ocean_agent
    ocean_results: List[ProviderResult]
    sst_field: Optional[GriddedField]
    chl_field: Optional[GriddedField]

    # weather_agent
    weather_results: List[ProviderResult]
    wave_field: Optional[GriddedField]
    wind_speed_field: Optional[GriddedField]
    wind_from_field: Optional[GriddedField]

    # downstream agents
    fishing: FishingResult
    candidates: List[CandidateRoute]
    risk: VoyageRiskAssessment
    plan: VoyagePlan

    warnings: Annotated[List[str], operator.add]
    trace: Annotated[List[str], operator.add]
