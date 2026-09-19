"""Weather agent: wave and wind data from ERA5 (gridded) and ASCAT (satellite winds)."""
from __future__ import annotations

from agents._common import build_query, grids_to_fields, status_warnings
from models.state import VoyageState
from services.data_service import DataService


def make_weather_agent(data: DataService):
    def weather_agent(state: VoyageState) -> dict:
        query = build_query(state["request"])
        results = [data.get("era5", query), data.get("ascat", query)]
        fields = grids_to_fields(results)
        return {
            "weather_results": results,
            "wave_field": fields.get("wave_height"),
            "wind_speed_field": fields.get("wind_speed"),
            "wind_from_field": fields.get("wind_from_deg"),
            "warnings": status_warnings(results),
            "trace": ["weather_agent: " + ", ".join(f"{r.provider}={r.status.value}" for r in results)
                      + f", grids={sorted(fields)}"],
        }

    return weather_agent
