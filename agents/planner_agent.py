"""Planner agent: deterministic synthesis of the final voyage plan.

No LLM is involved, so every statement in the plan traces to a service output.
Policy, in order:
  1. Refuse if the risk assessment is missing or INSUFFICIENT_DATA.
  2. Safety overrides yield: DO_NOT_VENTURE -> no voyage; HIGH_RISK -> not recommended.
  3. Otherwise pick among routable targets: drop routes not checked against land
     (unless allow_unmasked_route) and routes over the round-trip fuel budget,
     then take the highest fishing score, tie-break on lower fuel.
  4. Refuse if nothing usable remains. Every override is listed in conflicts_resolved.
Fuel is one-way; the return leg is assumed symmetric (round trip = 2x).
"""
from __future__ import annotations

from typing import List, Optional

from models.schemas import (
    CandidateRoute, PlanStatus, VoyagePlan, VoyageRisk, VoyageRiskAssessment,
)
from models.state import VoyageState


def _label(c: CandidateRoute) -> str:
    if c.zone is not None:
        return f"zone ({c.zone.lat:.3f}, {c.zone.lon:.3f}) score {c.zone.score:.2f}"
    return f"destination ({c.destination.lat:.3f}, {c.destination.lon:.3f})"


def planner_agent(state: VoyageState) -> dict:
    req = state["request"]
    risk: Optional[VoyageRiskAssessment] = state.get("risk")
    cands: List[CandidateRoute] = list(state.get("candidates", []))
    fishing = state.get("fishing")
    results = list(state.get("ocean_results", [])) + list(state.get("weather_results", []))
    data_status = {r.provider: r.status.value for r in results}
    conflicts: List[str] = []
    caveats: List[str] = []

    def done(status: PlanStatus, summary: str, **kw) -> dict:
        plan = VoyagePlan(status=status, summary=summary, risk=risk, data_status=data_status,
                          conflicts_resolved=conflicts, caveats=caveats, **kw)
        return {"plan": plan, "trace": [f"planner_agent: {status.value}"]}

    def refuse(reason: str) -> dict:
        return done(PlanStatus.REFUSED, f"Cannot produce a voyage plan: {reason}", refusal_reason=reason,
                    explanation=[reason])

    # 1. data sufficiency
    if risk is None or risk.verdict is VoyageRisk.INSUFFICIENT_DATA:
        return refuse(risk.explanation if risk else "no risk assessment was produced")

    # 2. safety overrides yield
    if risk.verdict in (VoyageRisk.DO_NOT_VENTURE, VoyageRisk.HIGH_RISK):
        if cands or (fishing and fishing.zones):
            conflicts.append("Fishing/route options were computed but ignored: safety verdict overrides yield.")
        status = PlanStatus.DO_NOT_VENTURE if risk.verdict is VoyageRisk.DO_NOT_VENTURE else PlanStatus.NOT_RECOMMENDED
        verb = "Do not venture out" if status is PlanStatus.DO_NOT_VENTURE else "Voyage not recommended"
        return done(status, f"{verb}. {risk.explanation}", explanation=[t.message for t in risk.triggered])

    # 3. choose a target
    if not cands:
        why = ("no destination was given and " + "; ".join(fishing.notes or ["no front-derived fishing zone met the score threshold"])
               if fishing and req.destination is None else "no routable target")
        return refuse(why)
    viable = [c for c in cands if c.route.found]
    for c in cands:
        if not c.route.found:
            conflicts.append(f"Dropped {_label(c)}: {c.route.reason}.")
    if not req.allow_unmasked_route:
        for c in [c for c in viable if not c.route.land_mask_used]:
            conflicts.append(f"Dropped {_label(c)}: route not checked against a land mask.")
        viable = [c for c in viable if c.route.land_mask_used]
        if not viable and any(c.route.found for c in cands):
            return refuse("no land mask configured (set LAND_POLYGONS_GEOJSON); routes cannot be certified "
                          "land-safe. Set allow_unmasked_route only for development.")
    if req.fuel_budget_l is not None:
        over = [c for c in viable if 2 * c.route.fuel_l > req.fuel_budget_l]
        for c in over:
            conflicts.append(f"Dropped {_label(c)}: round trip needs {2 * c.route.fuel_l:.0f} L "
                             f"> budget {req.fuel_budget_l:.0f} L.")
        viable = [c for c in viable if c not in over]
    if not viable:
        return refuse("no candidate target is reachable within the constraints. " + " ".join(conflicts))

    viable.sort(key=lambda c: (-(c.zone.score if c.zone else 0.0), c.route.fuel_l))
    best = viable[0]
    if cands[0] is not best:
        conflicts.append(f"Top-ranked {_label(cands[0])} was not usable; chose {_label(best)} instead.")

    r = best.route
    status = PlanStatus.PROCEED if risk.verdict is VoyageRisk.SAFE else PlanStatus.PROCEED_WITH_CAUTION
    explanation = [f"Target: {_label(best)}."]
    if best.zone:
        explanation.append("Why this zone: " + "; ".join(best.zone.reasons or ["front-derived cell"]) + ".")
    explanation.append(f"Route: {r.distance_nm:.1f} nm, {r.duration_h:.1f} h, {r.fuel_l:.0f} L one-way "
                       f"({2 * r.fuel_l:.0f} L round trip).")
    if r.max_wave_m is not None:
        explanation.append(f"Along the route: max wave {r.max_wave_m:.1f} m, max headwind {r.max_headwind_ms:.1f} m/s.")
    explanation.append(risk.explanation)
    if not r.land_mask_used:
        caveats.append("Route was NOT checked against land. Do not navigate by it.")
    if not r.conditions_used or r.cells_without_data:
        caveats.append(f"Weather missing for {r.cells_without_data or 'all'} route legs; they were costed as calm.")
    if risk.missing_variables:
        caveats.append("Not evaluated (no data): " + ", ".join(risk.missing_variables) + ".")
    caveats += [f"{p} data status {s}." for p, s in data_status.items() if s != "OK"]

    summary = f"{status.value}: {_label(best)}, {r.distance_nm:.0f} nm, ~{r.fuel_l:.0f} L one-way."
    return done(status, summary, target_zone=best.zone, destination=best.destination, route=r,
                alternates=[c for c in viable[1:]], explanation=explanation)
