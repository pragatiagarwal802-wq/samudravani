"""Fishing agent: ranks candidate zones with FishingService (front-derived cells only)."""
from __future__ import annotations

from models.state import VoyageState
from services.fishing_service import FishingService


def make_fishing_agent(service: FishingService):
    def fishing_agent(state: VoyageState) -> dict:
        result = service.score(state.get("sst_field"), state.get("chl_field"))
        return {
            "fishing": result,
            "trace": [f"fishing_agent: {len(result.zones)} zones from {result.candidate_cells} candidate cells"],
        }

    return fishing_agent
