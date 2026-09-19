"""SamudraVani API.  Run: uvicorn main:app

Environment: CDSAPI_URL/CDSAPI_KEY (ERA5), MOSDAC_USERNAME/MOSDAC_PASSWORD,
ASCAT_DATA_DIR or ASCAT_URL_TEMPLATE, LAND_POLYGONS_GEOJSON (coastline for routing),
SAMUDRAVANI_CACHE_DB (default cache/samudravani.sqlite).
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException

from graph.workflow import build_workflow
from models.schemas import VoyagePlanResponse, VoyageRequest
from services.data_service import build_default_service
from services.localization_service import LocalizationService
from services.routing_service import load_geojson_land_mask

_localizer = LocalizationService()


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.data = build_default_service(db_path=os.environ.get("SAMUDRAVANI_CACHE_DB", "cache/samudravani.sqlite"))
    land_path = os.environ.get("LAND_POLYGONS_GEOJSON")
    app.state.land = load_geojson_land_mask(land_path) if land_path else None
    app.state.graph = build_workflow(app.state.data, land=app.state.land)
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
