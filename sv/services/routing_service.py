"""Deterministic grid A* nautical router.

Nodes sit on a regular lat/lon grid and connect to their 8 neighbours. An edge
costs its great-circle length (nm) times a weather multiplier:

    1 + wave_weight * (Hs / max_wave)^2 + headwind_weight * headwind / headwind_ref

Edges into land, or through cells with Hs >= max_wave, are impassable. Cost is
never below distance, so the great-circle heuristic is admissible and the route
is optimal on the grid. Same inputs always give the same route (fixed neighbour
order and insertion-order tie-breaking).

Land and weather are injected. With no LandMask the router cannot avoid land and
says so in the result (land_mask_used=False); supply a mask for real use.
Land is tested at edge endpoints and midpoint, so features narrower than about
half a grid step can be missed: pick a resolution finer than the coastline detail.
"""
from __future__ import annotations

import heapq
import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Protocol, Sequence, Tuple

import numpy as np

from models.schemas import RouteResult, Waypoint
from services.config import load_config
from services.fields import GriddedField

EARTH_RADIUS_NM = 3440.065
LatLon = Tuple[float, float]


def haversine_nm(a: LatLon, b: LatLon) -> float:
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * EARTH_RADIUS_NM * math.asin(min(1.0, math.sqrt(h)))


def bearing_deg(a: LatLon, b: LatLon) -> float:
    la1, la2, dlo = math.radians(a[0]), math.radians(b[0]), math.radians(b[1] - a[1])
    y = math.sin(dlo) * math.cos(la2)
    x = math.cos(la1) * math.sin(la2) - math.sin(la1) * math.cos(la2) * math.cos(dlo)
    return math.degrees(math.atan2(y, x)) % 360.0


@dataclass(frozen=True)
class Conditions:
    wave_height_m: float = 0.0
    wind_speed_ms: float = 0.0
    wind_from_deg: float = 0.0  # meteorological: direction the wind blows FROM


class ConditionField(Protocol):
    def at(self, lat: float, lon: float) -> Optional[Conditions]: ...


class LandMask(Protocol):
    def is_land(self, lat: float, lon: float) -> bool: ...


class NoLandMask:
    def is_land(self, lat: float, lon: float) -> bool:
        return False


class PolygonLandMask:
    """Land as polygons of (lat, lon) vertices (ray casting, no holes)."""

    def __init__(self, polygons: Sequence[Sequence[LatLon]]):
        self.polygons = [list(p) for p in polygons]
        self._bounds = [
            (min(v[0] for v in p), max(v[0] for v in p), min(v[1] for v in p), max(v[1] for v in p))
            for p in self.polygons
        ]

    def is_land(self, lat: float, lon: float) -> bool:
        for poly, (s, n, w, e) in zip(self.polygons, self._bounds):
            if not (s <= lat <= n and w <= lon <= e):
                continue
            inside = False
            j = len(poly) - 1
            for i in range(len(poly)):
                yi, xi = poly[i]
                yj, xj = poly[j]
                if (yi > lat) != (yj > lat) and lon < (xj - xi) * (lat - yi) / (yj - yi) + xi:
                    inside = not inside
                j = i
            if inside:
                return True
        return False


def load_geojson_land_mask(path: str) -> PolygonLandMask:
    """Land polygons from GeoJSON (Polygon/MultiPolygon; exterior rings only, holes ignored)."""
    import json

    with open(path, "r", encoding="utf-8") as fh:
        gj = json.load(fh)
    feats = gj["features"] if gj.get("type") == "FeatureCollection" else [gj]
    polys: List[List[LatLon]] = []
    for f in feats:
        g = f.get("geometry", f)
        if g["type"] == "Polygon":
            rings = [g["coordinates"][0]]
        elif g["type"] == "MultiPolygon":
            rings = [p[0] for p in g["coordinates"]]
        else:
            continue
        polys += [[(pt[1], pt[0]) for pt in r] for r in rings]  # GeoJSON is (lon, lat)
    return PolygonLandMask(polys)


class GridLandMask:
    """Land from a GriddedField where values > 0.5 mean land (NaN = sea)."""

    def __init__(self, field: GriddedField):
        self.field = field

    def is_land(self, lat: float, lon: float) -> bool:
        v = self.field.nearest(lat, lon)
        return bool(v > 0.5) if not math.isnan(v) else False


class GriddedConditions:
    """Nearest-cell weather from gridded fields; returns None where all are missing."""

    def __init__(self, wave_height: Optional[GriddedField] = None, wind_speed: Optional[GriddedField] = None,
                 wind_from_deg: Optional[GriddedField] = None):
        self.wave, self.speed, self.direction = wave_height, wind_speed, wind_from_deg

    @staticmethod
    def _v(f: Optional[GriddedField], lat: float, lon: float) -> float:
        return float("nan") if f is None else f.nearest(lat, lon)

    def at(self, lat: float, lon: float) -> Optional[Conditions]:
        w, s, d = self._v(self.wave, lat, lon), self._v(self.speed, lat, lon), self._v(self.direction, lat, lon)
        if math.isnan(w) and math.isnan(s):
            return None
        nz = lambda x: 0.0 if math.isnan(x) else x
        return Conditions(nz(w), nz(s), nz(d))


_NEIGHBOURS = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]


class NauticalRouter:
    def __init__(self, config: Optional[Dict[str, Any]] = None, land: Optional[LandMask] = None,
                 conditions: Optional[ConditionField] = None):
        cfg = config or load_config()
        self.r, self.v = cfg["routing"], cfg["vessel"]
        self.land = land
        self.conditions = conditions

    # -- edge model -----------------------------------------------------------
    def _edge(self, a: LatLon, b: LatLon):
        """(distance_nm, multiplier, wave_m, headwind_ms, had_data) or None if impassable."""
        mid = ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)
        if self.land and (self.land.is_land(*b) or self.land.is_land(*mid)):
            return None
        dist = haversine_nm(a, b)
        wave = head = 0.0
        has = False
        c = self.conditions.at(*mid) if self.conditions else None
        if c is not None:
            has = True
            wave = c.wave_height_m
            if wave >= self.r["max_wave_m"]:
                return None
            head = c.wind_speed_ms * math.cos(math.radians(bearing_deg(a, b) - c.wind_from_deg))
        mult = (1.0 + self.r["wave_weight"] * (wave / self.r["max_wave_m"]) ** 2
                + self.r["headwind_weight"] * max(0.0, head) / self.r["headwind_ref_ms"])
        return dist, mult, wave, head, has

    # -- search ----------------------------------------------------------------
    def route(self, start: LatLon, goal: LatLon) -> RouteResult:
        res, margin = self.r["grid_resolution_deg"], self.r["margin_deg"]
        if abs(start[1] - goal[1]) > 180:
            raise ValueError("routes crossing the antimeridian are not supported")
        base = dict(land_mask_used=self.land is not None, conditions_used=self.conditions is not None,
                    straight_line_nm=haversine_nm(start, goal))

        lat0 = max(-90.0, min(start[0], goal[0]) - margin)
        lon0 = max(-180.0, min(start[1], goal[1]) - margin)
        nlat = int(round((min(90.0, max(start[0], goal[0]) + margin) - lat0) / res)) + 1
        nlon = int(round((min(180.0, max(start[1], goal[1]) + margin) - lon0) / res)) + 1
        if nlat * nlon > self.r["max_nodes"]:
            raise ValueError(f"grid of {nlat * nlon} nodes exceeds max_nodes; coarsen grid_resolution_deg")

        ll = lambda n: (lat0 + n[0] * res, lon0 + n[1] * res)
        snap = lambda p: (min(nlat - 1, max(0, round((p[0] - lat0) / res))),
                          min(nlon - 1, max(0, round((p[1] - lon0) / res))))
        s_node, g_node = snap(start), snap(goal)
        for label, n in (("start", s_node), ("goal", g_node)):
            if self.land and self.land.is_land(*ll(n)):
                return RouteResult(found=False, reason=f"{label} snaps to a land cell", **base)

        goal_ll = ll(g_node)
        g_cost: Dict[Tuple[int, int], float] = {s_node: 0.0}
        parent: Dict[Tuple[int, int], Tuple[int, int]] = {}
        closed = set()
        counter = 0
        heap: List[Tuple[float, int, Tuple[int, int]]] = [(haversine_nm(ll(s_node), goal_ll), 0, s_node)]
        while heap:
            _, _, cur = heapq.heappop(heap)
            if cur in closed:
                continue
            closed.add(cur)
            if cur == g_node:
                break
            for di, dj in _NEIGHBOURS:
                nb = (cur[0] + di, cur[1] + dj)
                if not (0 <= nb[0] < nlat and 0 <= nb[1] < nlon) or nb in closed:
                    continue
                e = self._edge(ll(cur), ll(nb))
                if e is None:
                    continue
                cost = g_cost[cur] + e[0] * e[1]
                if cost < g_cost.get(nb, math.inf):
                    g_cost[nb] = cost
                    parent[nb] = cur
                    counter += 1
                    heapq.heappush(heap, (cost + haversine_nm(ll(nb), goal_ll), counter, nb))
        else:
            return RouteResult(found=False, reason="no passable route on the grid", **base)

        path = [g_node]
        while path[-1] != s_node:
            path.append(parent[path[-1]])
        path.reverse()
        return self._summarise(path, ll, start, goal, base)

    def _summarise(self, path, ll, start: LatLon, goal: LatLon, base: dict) -> RouteResult:
        speed = self.v["cruise_speed_kn"]
        rate = self.v["fuel_rate_lph_at_design"] * (speed / self.v["design_speed_kn"]) ** 3
        dist = fuel = 0.0
        max_wave = max_head = None
        missing = 0
        for a, b in zip(path, path[1:]):
            d, mult, wave, head, has = self._edge(ll(a), ll(b))
            dist += d
            fuel += (d / speed) * rate * (1.0 + self.v["fuel_penalty_share"] * (mult - 1.0))
            if has:
                max_wave = wave if max_wave is None else max(max_wave, wave)
                max_head = head if max_head is None else max(max_head, head)
            else:
                missing += 1
        # legs between the true endpoints and their snapped grid nodes (no weather model)
        for p, q in ((start, ll(path[0])), (ll(path[-1]), goal)):
            d = haversine_nm(p, q)
            dist += d
            fuel += (d / speed) * rate
        pts = [start] + [ll(n) for n in path] + [goal]
        return RouteResult(
            found=True,
            waypoints=[Waypoint(lat=p[0], lon=p[1]) for p in pts],
            distance_nm=dist, duration_h=dist / speed, fuel_l=fuel,
            max_wave_m=max_wave, max_headwind_ms=max_head, cells_without_data=missing, **base,
        )
