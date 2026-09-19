"""End-to-end smoke tests on the Saurashtra coast (Veraval / Porbandar).

External services are replaced by fake providers that return synthetic but
physically shaped fields (a sharp SST/Chl-a front at 21.0N, NaN over land as real
satellite products have). The graph, cache, services, planner and localizer are real.
The land polygon is a coarse approximation for testing only, not a survey.
"""
from __future__ import annotations

from datetime import datetime

import numpy as np
import pytest

from graph.workflow import build_workflow
from models.schemas import (
    BoundingBox, Location, Observation, PlanStatus, ProviderResult, ProviderStatus, TimeWindow, VoyageRequest,
)
from providers.base import DataProvider
from services.data_service import DataService
from services.fields import GriddedField
from services.localization_service import LANGS, LocalizationService
from services.routing_service import PolygonLandMask

# Land lies north-east of the coast Dwarka - Porbandar - Veraval - Diu (lat, lon).
LAND = PolygonLandMask([[(22.5, 68.9), (21.64, 69.63), (20.91, 70.37), (20.71, 71.0), (20.71, 72.5), (22.5, 72.5)]])
LATS = np.round(np.arange(20.0, 22.0001, 0.05), 4)
LONS = np.round(np.arange(68.8, 71.0001, 0.05), 4)
LAT, LON = np.meshgrid(LATS, LONS, indexing="ij")
IS_LAND = np.vectorize(LAND.is_land)(LAT, LON)

VERAVAL = Location(lat=20.80, lon=70.25, name="Veraval (offshore approach)")
PORBANDAR = Location(lat=21.45, lon=69.45, name="Porbandar (offshore approach)")
WINDOW = TimeWindow(start=datetime(2026, 9, 20, 0), end=datetime(2026, 9, 21, 0))
AREA = BoundingBox(south=20.0, west=68.8, north=22.0, east=71.0)


class FakeProvider(DataProvider):
    def __init__(self, name: str, result: ProviderResult):
        self.name, self._result = name, result

    def fetch(self, query):
        return self._result


def _grid(name, unit, arr):
    return GriddedField(LATS, LONS, np.where(IS_LAND, np.nan, arr), name, unit).to_payload()


def _obs(provider, **vals):
    return [Observation(variable=k, value=v, source=provider) for k, v in vals.items()]


def make_service(tmp_path, wave=1.2, wind=6.0, data_ok=True) -> DataService:
    # one cache DB per scenario: the cache key does not include the (fake) data
    db = str(tmp_path / f"cache-{wave}-{wind}-{data_ok}.sqlite")
    if not data_ok:
        na = lambda n: FakeProvider(n, ProviderResult(provider=n, status=ProviderStatus.NOT_AVAILABLE, message="off"))
        return DataService([na("era5"), na("ascat"), na("mosdac")], db_path=db)
    era5 = ProviderResult(
        provider="era5", status=ProviderStatus.OK,
        observations=_obs("era5", wave_height=wave, wind_speed=wind),
        grids={"wave_height": _grid("wave_height", "m", np.full(LAT.shape, wave)),
               "wind_speed": _grid("wind_speed", "m/s", np.full(LAT.shape, wind)),
               "wind_from_deg": _grid("wind_from_deg", "deg", np.full(LAT.shape, 315.0))})
    ascat = ProviderResult(provider="ascat", status=ProviderStatus.OK, observations=_obs("ascat", wind_speed=wind))
    front = np.tanh((LAT - 21.0) / 0.1)
    mosdac = ProviderResult(
        provider="mosdac", status=ProviderStatus.OK,
        observations=_obs("mosdac", sst_mean=28.0),
        grids={"sst": _grid("sst", "degC", 28.0 + front),
               "chl": _grid("chl", "mg/m3", 10 ** (-0.5 + 0.3 * front))})
    return DataService([FakeProvider("era5", era5), FakeProvider("ascat", ascat), FakeProvider("mosdac", mosdac)],
                       db_path=db)


def run(service, **req):
    graph = build_workflow(service, land=LAND)
    final = graph.invoke({"request": VoyageRequest(window=WINDOW, bbox=AREA, **req), "warnings": [], "trace": []})
    return final


# --- pipeline ------------------------------------------------------------------

def test_veraval_fishing_trip_end_to_end(tmp_path):
    final = run(make_service(tmp_path), origin=VERAVAL, max_candidates=3)
    plan = final["plan"]

    assert plan.status in (PlanStatus.PROCEED, PlanStatus.PROCEED_WITH_CAUTION), plan.summary
    assert plan.risk.verdict.value == "SAFE"

    # zone coordinates come from cells of the SST/Chl grid, never invented
    z = plan.target_zone
    assert z is not None and 0.0 <= z.score <= 1.0
    i, j = z.source_cell
    assert (z.lat, z.lon) == (pytest.approx(LATS[i]), pytest.approx(LONS[j]))
    assert not IS_LAND[i, j]
    assert abs(z.lat - 21.0) <= 0.15  # sits on the synthetic front

    # route: found, fuel-aware, and never on land
    r = plan.route
    assert r.found and r.land_mask_used and r.conditions_used
    assert r.distance_nm >= r.straight_line_nm > 0
    assert r.fuel_l > 0 and r.duration_h > 0
    assert (r.waypoints[0].lat, r.waypoints[0].lon) == (VERAVAL.lat, VERAVAL.lon)
    assert all(not LAND.is_land(w.lat, w.lon) for w in r.waypoints)

    # both entry agents ran, and every agent left a trace
    trace = " ".join(final["trace"])
    for name in ("ocean_agent", "weather_agent", "fishing_agent", "route_agent", "risk_agent", "planner_agent"):
        assert name in trace


def test_porbandar_to_veraval_explicit_destination(tmp_path):
    final = run(make_service(tmp_path), origin=PORBANDAR, destination=VERAVAL)
    plan = final["plan"]
    assert plan.status in (PlanStatus.PROCEED, PlanStatus.PROCEED_WITH_CAUTION)
    assert plan.target_zone is None and plan.destination == VERAVAL
    assert plan.route.found and all(not LAND.is_land(w.lat, w.lon) for w in plan.route.waypoints)


def test_pipeline_is_deterministic(tmp_path):
    service = make_service(tmp_path)
    a = run(service, origin=VERAVAL)["plan"]
    b = run(service, origin=VERAVAL)["plan"]  # second run is served from the cache
    assert a.model_dump_json() == b.model_dump_json()


def test_high_waves_mean_no_voyage(tmp_path):
    plan = run(make_service(tmp_path, wave=7.0), origin=VERAVAL)["plan"]
    assert plan.status is PlanStatus.DO_NOT_VENTURE
    assert plan.route is None and plan.target_zone is None
    assert any(t.rule_id == "wave_stop" for t in plan.risk.triggered)
    assert any("overrides yield" in c for c in plan.conflicts_resolved)


def test_refuses_without_data(tmp_path):
    plan = run(make_service(tmp_path, data_ok=False), origin=VERAVAL)["plan"]
    assert plan.status is PlanStatus.REFUSED
    assert plan.route is None and plan.refusal_reason
    assert plan.risk.verdict.value == "INSUFFICIENT_DATA"


def test_fuel_budget_forces_refusal(tmp_path):
    plan = run(make_service(tmp_path), origin=VERAVAL, fuel_budget_l=1.0)["plan"]
    assert plan.status is PlanStatus.REFUSED
    assert any("budget" in c for c in plan.conflicts_resolved)


# --- localization ----------------------------------------------------------------

LOC = LocalizationService()


@pytest.mark.parametrize("lang", ["hi", "gu"])
def test_localized_plans_preserve_numbers_and_tags(tmp_path, lang):
    plans = [
        run(make_service(tmp_path), origin=VERAVAL)["plan"],
        run(make_service(tmp_path, wave=7.0), origin=VERAVAL)["plan"],
        run(make_service(tmp_path, data_ok=False), origin=VERAVAL)["plan"],
    ]
    for plan in plans:
        loc = LOC.localize_plan(plan, lang)
        assert loc.untranslated == [], loc.untranslated  # every planner sentence has a pattern
        assert loc.status_tag == plan.status.value and plan.status.value in loc.status_text
        pairs = [(plan.summary, loc.summary), (plan.risk.explanation, loc.risk_explanation)]
        pairs += list(zip(plan.explanation, loc.explanation)) + list(zip(plan.caveats, loc.caveats))
        pairs += list(zip(plan.conflicts_resolved, loc.conflicts_resolved))
        pairs += [(t.message, lt.message) for t, lt in zip(plan.risk.triggered, loc.triggered)]
        for src, out in pairs:
            assert LOC._invariants(src) == LOC._invariants(out), (src, out)
        assert any(out != src for src, out in pairs)  # something was actually translated


def test_localization_does_not_mutate_plan(tmp_path):
    plan = run(make_service(tmp_path), origin=VERAVAL)["plan"]
    before = plan.model_dump_json()
    LOC.localize_all(plan)
    assert plan.model_dump_json() == before


def test_unknown_sentence_falls_back_to_english():
    text = "A sentence the planner never emits, 42 nm."
    assert LOC.translate(text, "hi") == (text, False)


def test_translation_that_changes_a_number_is_rejected(monkeypatch):
    import services.localization_service as ls

    bad = [(rx, {"hi": t["hi"].replace("{d}", "999"), "gu": t["gu"]}) for rx, t in ls._PATTERNS]
    monkeypatch.setattr(ls, "_PATTERNS", bad)
    src = "Along the route: max wave 1.2 m, max headwind 3.4 m/s."
    assert LOC.translate(src, "hi")[1] is True  # this pattern has no {d}: unaffected
    src = "Route: 12.5 nm, 1.6 h, 30 L one-way (60 L round trip)."
    assert LOC.translate(src, "hi") == (src, False)  # altered number -> English original kept


def test_all_languages_supported():
    assert set(LANGS) == {"en", "hi", "gu"}


# --- API --------------------------------------------------------------------------

def test_api_refuses_cleanly_without_credentials(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    for var in ("CDSAPI_URL", "CDSAPI_KEY", "MOSDAC_USERNAME", "MOSDAC_PASSWORD", "ASCAT_DATA_DIR",
                "ASCAT_URL_TEMPLATE", "LAND_POLYGONS_GEOJSON"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("SAMUDRAVANI_CACHE_DB", str(tmp_path / "api.sqlite"))
    import main

    body = {"origin": {"lat": 20.80, "lon": 70.25}, "window": {"start": "2026-09-20T00:00:00", "end": "2026-09-21T00:00:00"}}
    with TestClient(main.app) as client:
        h = client.get("/health")
        assert h.status_code == 200 and h.json()["status"] == "degraded"
        r = client.post("/api/v1/voyage/plan", json=body)
        assert r.status_code == 200
        js = r.json()
        assert js["plan"]["status"] == "REFUSED"
        assert set(js["localized"]) == set(LANGS)
        bad = client.post("/api/v1/voyage/plan", json={**body, "window": {"start": "2026-09-21T00:00:00", "end": "2026-09-20T00:00:00"}})
        assert bad.status_code == 422
