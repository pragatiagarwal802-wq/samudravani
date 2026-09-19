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


class VoyageRisk(str, Enum):
    SAFE = "SAFE"
    CAUTION = "CAUTION"
    HIGH_RISK = "HIGH_RISK"
    DO_NOT_VENTURE = "DO_NOT_VENTURE"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class TriggeredRule(BaseModel):
    rule_id: str
    variable: str
    value: float
    op: str
    threshold: float
    verdict: VoyageRisk
    message: str


class VoyageRiskAssessment(BaseModel):
    verdict: VoyageRisk
    triggered: List[TriggeredRule] = Field(default_factory=list)
    evaluated_variables: List[str] = Field(default_factory=list)
    missing_variables: List[str] = Field(default_factory=list)
    explanation: str


class Waypoint(BaseModel):
    lat: float
    lon: float


class RouteResult(BaseModel):
    found: bool
    reason: Optional[str] = None
    waypoints: List[Waypoint] = Field(default_factory=list)
    distance_nm: float = 0.0
    straight_line_nm: float = 0.0
    duration_h: float = 0.0
    fuel_l: float = 0.0
    max_wave_m: Optional[float] = None
    max_headwind_ms: Optional[float] = None
    land_mask_used: bool = False
    conditions_used: bool = False
    cells_without_data: int = 0


class FishingZone(BaseModel):
    lat: float
    lon: float
    score: float = Field(ge=0.0, le=1.0)
    components: Dict[str, float]
    reasons: List[str]
    # Grid indices of the source cell, so the coordinate can be traced to data.
    source_cell: List[int]


class FishingResult(BaseModel):
    zones: List[FishingZone] = Field(default_factory=list)
    candidate_cells: int = 0
    notes: List[str] = Field(default_factory=list)


class Location(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    name: Optional[str] = None


class TimeWindow(BaseModel):
    start: datetime
    end: datetime


class BoundingBox(BaseModel):
    south: float = Field(ge=-90, le=90)
    west: float = Field(ge=-180, le=180)
    north: float = Field(ge=-90, le=90)
    east: float = Field(ge=-180, le=180)


class RiskQuery(BaseModel):
    location: Location
    window: TimeWindow
    bbox: Optional[BoundingBox] = None

    def region(self, half_width: float = 0.5) -> BoundingBox:
        """Explicit bbox if given, else a box of +/- half_width degrees around the location."""
        if self.bbox is not None:
            return self.bbox
        lat, lon = self.location.lat, self.location.lon
        return BoundingBox(
            south=max(-90.0, lat - half_width),
            north=min(90.0, lat + half_width),
            west=max(-180.0, lon - half_width),
            east=min(180.0, lon + half_width),
        )


class Observation(BaseModel):
    """A single variable reading. `value` is None when the source lacks it."""

    variable: str
    value: Optional[float] = None
    unit: Optional[str] = None
    timestamp: Optional[datetime] = None
    source: str


class GridPayload(BaseModel):
    """Serialisable lat/lon grid; values[i][j] at (lat[i], lon[j]), None = no data."""

    name: str
    unit: str = ""
    lat: List[float]
    lon: List[float]
    values: List[List[Optional[float]]]


class ProviderResult(BaseModel):
    provider: str
    status: ProviderStatus
    observations: List[Observation] = Field(default_factory=list)
    grids: Dict[str, GridPayload] = Field(default_factory=dict)
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


# --- voyage planning -------------------------------------------------------


class VoyageRequest(BaseModel):
    origin: Location
    destination: Optional[Location] = None
    window: TimeWindow
    bbox: Optional[BoundingBox] = None
    search_radius_deg: float = Field(default=2.0, gt=0, le=10)
    max_candidates: int = Field(default=3, ge=1, le=5)
    fuel_budget_l: Optional[float] = Field(default=None, gt=0)  # round-trip budget
    allow_unmasked_route: bool = False  # dev only: accept routes not checked against land


class CandidateRoute(BaseModel):
    zone: Optional[FishingZone] = None
    destination: Location
    route: RouteResult


class PlanStatus(str, Enum):
    PROCEED = "PROCEED"
    PROCEED_WITH_CAUTION = "PROCEED_WITH_CAUTION"
    NOT_RECOMMENDED = "NOT_RECOMMENDED"
    DO_NOT_VENTURE = "DO_NOT_VENTURE"
    REFUSED = "REFUSED"


class VoyagePlan(BaseModel):
    status: PlanStatus
    summary: str
    refusal_reason: Optional[str] = None
    risk: Optional[VoyageRiskAssessment] = None
    target_zone: Optional[FishingZone] = None
    destination: Optional[Location] = None
    route: Optional[RouteResult] = None
    alternates: List[CandidateRoute] = Field(default_factory=list)
    conflicts_resolved: List[str] = Field(default_factory=list)
    caveats: List[str] = Field(default_factory=list)
    explanation: List[str] = Field(default_factory=list)
    data_status: Dict[str, str] = Field(default_factory=dict)


class VoyagePlanResponse(BaseModel):
    plan: VoyagePlan
    warnings: List[str] = Field(default_factory=list)
    trace: List[str] = Field(default_factory=list)
