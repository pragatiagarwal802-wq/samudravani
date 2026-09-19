"""Ocean agent: collects ocean state (SST, Chl-a and front metrics) from MOSDAC.

Sentinel has no provider in this codebase yet, so it is reported as unavailable
rather than silently skipped.
"""
from __future__ import annotations

from agents._common import build_query, grids_to_fields, status_warnings
from models.state import VoyageState
from services.data_service import DataService


def make_ocean_agent(data: DataService):
    def ocean_agent(state: VoyageState) -> dict:
        query = build_query(state["request"])
        results = [data.get("mosdac", query)]
        fields = grids_to_fields(results)
        return {
            "ocean_results": results,
            "sst_field": fields.get("sst"),
            "chl_field": fields.get("chl"),
            "warnings": status_warnings(results) + ["sentinel: no provider implemented"],
            "trace": [f"ocean_agent: mosdac={results[0].status.value}, grids={sorted(fields)}"],
        }

    return ocean_agent
