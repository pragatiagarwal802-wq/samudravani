"""Route agent: fuel-aware routes from the origin to the destination, or to the top fishing zones."""
from __future__ import annotations

from models.schemas import CandidateRoute, Location
from models.state import VoyageState
from services.routing_service import GriddedConditions, NauticalRouter


def make_route_agent(base_router: NauticalRouter):
    def route_agent(state: VoyageState) -> dict:
        req = state["request"]
        router = NauticalRouter(
            {"routing": base_router.r, "vessel": base_router.v},
            land=base_router.land,
            conditions=GriddedConditions(state.get("wave_field"), state.get("wind_speed_field"),
                                         state.get("wind_from_field")),
        )
        if req.destination is not None:
            targets = [(None, req.destination)]
        else:
            zones = state["fishing"].zones[: req.max_candidates] if "fishing" in state else []
            targets = [(z, Location(lat=z.lat, lon=z.lon)) for z in zones]

        origin = (req.origin.lat, req.origin.lon)
        candidates, warnings = [], []
        for zone, dest in targets:
            try:
                route = router.route(origin, (dest.lat, dest.lon))
            except ValueError as exc:  # grid too large / antimeridian
                warnings.append(f"route to ({dest.lat:.3f}, {dest.lon:.3f}) failed: {exc}")
                continue
            candidates.append(CandidateRoute(zone=zone, destination=dest, route=route))
        return {
            "candidates": candidates,
            "warnings": warnings,
            "trace": [f"route_agent: {sum(c.route.found for c in candidates)}/{len(targets)} targets routable"],
        }

    return route_agent
