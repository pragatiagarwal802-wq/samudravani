"""Pipeline state passed between processing steps (LangGraph-compatible TypedDict)."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, TypedDict

from models.schemas import ProviderResult, RiskAssessment, RiskQuery


class SamudraState(TypedDict, total=False):
    query: RiskQuery
    config: Dict[str, Any]
    provider_results: List[ProviderResult]
    assessment: Optional[RiskAssessment]
    errors: List[str]
