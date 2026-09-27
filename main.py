"""SamudraVani API.  Run: uvicorn main:app

Environment: CDSAPI_URL/CDSAPI_KEY (ERA5), MOSDAC_USERNAME/MOSDAC_PASSWORD,
COPERNICUSMARINE_SERVICE_USERNAME/COPERNICUSMARINE_SERVICE_PASSWORD or COPERNICUS_DATA_DIR
(Copernicus Marine SST + Chl-a; optional COPERNICUS_LOOKBACK_DAYS, default 5),
ASCAT_DATA_DIR or ASCAT_URL_TEMPLATE, OPENMETEO_ENABLED (default 1; forecasts, no key needed),
LAND_POLYGONS_GEOJSON (coastline for routing; default data/land_west_india.geojson, "" = none),
SAMUDRAVANI_CACHE_DB (default cache/samudravani.sqlite), PREFETCH (default 1: refresh the ports in
config/risk_config.yaml at startup and hourly).
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query

from graph.workflow import build_workflow
from datetime import datetime, timedelta, timezone

from models.schemas import (
    AskRequest, AskResponse, ForecastResponse, TimeWindow, VoyagePlanResponse, VoyageRequest,
)
from services.ask_service import AskService
from services.data_service import build_default_service
from providers._util import prefer_ipv4
from services import prefetch
from services.config import load_config
from services.forecast_service import ForecastService
from services.localization_service import LocalizationService
from services.risk_service import RiskService
from services.routing_service import load_geojson_land_mask

_localizer = LocalizationService()
DEFAULT_LAND = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "land_west_india.geojson")


@asynccontextmanager
async def lifespan(app: FastAPI):
    prefer_ipv4()  # see providers._util.prefer_ipv4: avoids ~21 s IPv6 timeouts per MOSDAC connection
    app.state.data = build_default_service(db_path=os.environ.get("SAMUDRAVANI_CACHE_DB", "cache/samudravani.sqlite"))
    land_path = os.environ.get("LAND_POLYGONS_GEOJSON", DEFAULT_LAND)
    app.state.land = load_geojson_land_mask(land_path) if land_path else None
    app.state.graph = build_workflow(app.state.data, land=app.state.land)
    app.state.forecast = ForecastService(RiskService(), _localizer)
    app.state.ask = AskService(forecast=lambda lat, lon: app.state.forecast.forecast(lat, lon, 5), plan=_plan_for_ask)
    if os.environ.get("PREFETCH", "1") != "0":
        ports = [(p["name"], p["lat"], p["lon"]) for p in load_config().get("ports", [])]
        prefetch.start(ports, plan=_plan_for_ask, forecast=lambda lat, lon: app.state.forecast.forecast(lat, lon, 5))
    yield


app = FastAPI(title="SamudraVani", version="0.4.0", lifespan=lifespan)


@app.post("/api/v1/voyage/plan", response_model=VoyagePlanResponse)
def plan_voyage(req: VoyageRequest) -> VoyagePlanResponse:
    """Runs the agent graph. Sync on purpose: FastAPI runs it in a worker thread, since
    provider calls (notably ERA5 queueing) can take minutes. A refusal is a normal 200
    response with plan.status == REFUSED."""
    if req.window.end <= req.window.start:
        raise HTTPException(status_code=422, detail="window.end must be after window.start")
    final = app.state.graph.invoke({"request": req, "warnings": [], "trace": []})
    plan = final["plan"]
    fishing = final.get("fishing")
    return VoyagePlanResponse(
        plan=plan,
        fishing_zones=fishing.zones if fishing else [],
        localized=_localizer.localize_all(plan),  # all languages at once so the UI can toggle without re-planning
        warnings=final.get("warnings", []),
        trace=final.get("trace", []),
    )


@app.get("/api/v1/forecast", response_model=ForecastResponse)
def forecast(lat: float = Query(ge=-90, le=90), lon: float = Query(ge=-180, le=180),
             days: int = Query(5, ge=1, le=7)) -> ForecastResponse:
    """Hourly conditions at a point and a voyage-rule verdict per local day (Asia/Kolkata).
    Used by the app's weather and alerts screens; 503 when the forecast source is unreachable."""
    from providers.openmeteo import OpenMeteoProvider

    if not OpenMeteoProvider.enabled():
        raise HTTPException(status_code=503, detail="forecast source disabled (OPENMETEO_ENABLED=0)")
    try:
        return app.state.forecast.forecast(lat, lon, days)
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"forecast unavailable: {exc}")


def _plan_for_ask(lat: float, lon: float, name: str) -> VoyagePlanResponse:
    """Fishing plan for the next 24 hours from a point, as the app requests it."""
    from models.schemas import Location

    now = datetime.now(timezone.utc).replace(tzinfo=None, minute=0, second=0, microsecond=0)
    req = VoyageRequest(origin=Location(lat=lat, lon=lon, name=name),
                        window=TimeWindow(start=now, end=now + timedelta(hours=24)), search_radius_deg=1.0)
    return plan_voyage(req)


@app.post("/api/v1/ask", response_model=AskResponse)
def ask(req: AskRequest) -> AskResponse:
    """Answer a fisher's question (typed or spoken) from the live forecast and voyage plan.
    Rules mode by default; Claude writes the answer when ANTHROPIC_API_KEY is set."""
    place = req.origin.name or f"{req.origin.lat:.2f}, {req.origin.lon:.2f}"
    a = app.state.ask.ask(req.question, req.lang, req.origin.lat, req.origin.lon, place)
    return AskResponse(answer=a.answer, lang=req.lang, intent=a.intent, mode=a.mode)


@app.get("/health")
def health():
    """Local checks only: provider configuration and cache/graph readiness. It does not call
    upstream services, so 'configured' means credentials/sources are set, not that they are reachable."""
    providers = {name: p.health() for name, p in app.state.data.providers.items()}
    try:
        with app.state.data._db() as db:
            db.execute("SELECT 1")
        cache_ok = True
    except Exception:
        cache_ok = False
    graph_ok = getattr(app.state, "graph", None) is not None
    body = {
        "ask_mode": app.state.ask.mode,
        "status": "ok" if cache_ok and graph_ok and all(v["configured"] for k, v in providers.items() if k != "era6")
        else "degraded" if cache_ok and graph_ok else "unhealthy",
        "cache": cache_ok,
        "graph": graph_ok,
        "land_mask": app.state.land is not None,
        "providers": providers,
    }
    if not (cache_ok and graph_ok):
        raise HTTPException(status_code=503, detail=body)
    return body
