"""Pydantic schemas shared across SamudraVani."""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class ProviderStatus(str, Enum):
    OK = "OK"
    PARTIAL = "PARTIAL"
    NOT_AVAILABLE = "NOT_AVAILABLE"
    ERROR = "ERROR"


class RiskLevel(str, Enum):
    LOW = "LOW"
    MODERATE = "MODERATE"
    HIGH = "HIGH"
    SEVERE = "SEVERE"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class Location(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    name: Optional[str] = None


class TimeWindow(BaseModel):
    start: datetime
    end: datetime


class RiskQuery(BaseModel):
    location: Location
    window: TimeWindow


class Observation(BaseModel):
    """A single variable reading. `value` is None when the source lacks it."""

    variable: str
    value: Optional[float] = None
    unit: Optional[str] = None
    timestamp: Optional[datetime] = None
    source: str


class ProviderResult(BaseModel):
    provider: str
    status: ProviderStatus
    observations: List[Observation] = Field(default_factory=list)
    message: Optional[str] = None


class VariableScore(BaseModel):
    variable: str
    value: float
    score: float = Field(ge=0.0, le=1.0)
    weight: float = Field(ge=0.0, le=1.0)


class RiskAssessment(BaseModel):
    query: RiskQuery
    level: RiskLevel
    score: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    variable_scores: List[VariableScore] = Field(default_factory=list)
    provider_statuses: Dict[str, ProviderStatus] = Field(default_factory=dict)
    notes: List[str] = Field(default_factory=list)
