"""Helpers shared by agents."""
from __future__ import annotations

from typing import Dict, List, Optional

from models.schemas import BoundingBox, ProviderResult, ProviderStatus, RiskQuery, VoyageRequest
from services.fields import GriddedField


def build_query(req: VoyageRequest) -> RiskQuery:
    """Data query for the operating area: explicit bbox, else origin +/- search_radius_deg."""
    box = req.bbox or RiskQuery(location=req.origin, window=req.window).region(req.search_radius_deg)
    return RiskQuery(location=req.origin, window=req.window, bbox=box)


def grids_to_fields(results: List[ProviderResult]) -> Dict[str, GriddedField]:
    out: Dict[str, GriddedField] = {}
    for r in results:
        for name, payload in r.grids.items():
            out.setdefault(name, GriddedField.from_payload(payload))
    return out


def status_warnings(results: List[ProviderResult]) -> List[str]:
    return [f"{r.provider}: {r.status.value}" + (f" - {r.message}" if r.message else "")
            for r in results if r.status is not ProviderStatus.OK]
