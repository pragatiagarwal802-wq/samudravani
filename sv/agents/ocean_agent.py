"""Ocean agent: collects ocean state (SST, Chl-a and front metrics).

Sources, in priority order per field: Copernicus Marine (global daily L4 SST and
gap-free Chl-a), then MOSDAC. A field missing from Copernicus (e.g. Chl-a fetch
failed) is filled from MOSDAC when it has one.

Sentinel has no dedicated provider in this codebase yet, so it is reported as
unavailable rather than silently skipped.
"""
from __future__ import annotations

from agents._common import build_query, grids_to_fields, status_warnings
from models.state import VoyageState
from services.data_service import DataService

SOURCES = ["copernicus", "mosdac"]  # grids_to_fields keeps the first provider's grid per name


def make_ocean_agent(data: DataService):
    def ocean_agent(state: VoyageState) -> dict:
        query = build_query(state["request"])
        results = [data.get(name, query) for name in SOURCES]
        fields = grids_to_fields(results)
        origin = {k: next(r.provider for r in results if k in r.grids) for k in fields}
        return {
            "ocean_results": results,
            "sst_field": fields.get("sst"),
            "chl_field": fields.get("chl"),
            "warnings": status_warnings(results) + ["sentinel: no provider implemented"],
            "trace": ["ocean_agent: " + ", ".join(f"{r.provider}={r.status.value}" for r in results)
                      + f", grids={ {k: origin[k] for k in sorted(origin)} }"],
        }

    return ocean_agent
