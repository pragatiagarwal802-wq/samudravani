"""Deterministic fishing-suitability scoring from SST and Chl-a fronts.

Every returned coordinate is the centre of a grid cell of the input fields
(source_cell records its indices), and a cell only qualifies if it is a front
feature point: SST or log10(Chl-a) gradient above its configured threshold.
Nothing is interpolated, invented or geocoded.

Cell score = weighted mean of the available components in [0, 1]:
  sst_front, chl_front      gradient / saturation (clipped)
  sst_preference            1 inside the optimal SST band, linear falloff over sst_margin_c
  chl_preference            1 inside the optimal Chl-a band, log falloff over chl_margin_factor
Weights are renormalised over components that have data for that cell.
Selection: front cells with score >= min_score that are 3x3 local maxima, taken
best-first with a minimum separation. The optimal bands are species-dependent
config values, not universal constants.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional

import numpy as np

from models.schemas import FishingResult, FishingZone
from services.config import load_config
from services.fields import KM_PER_DEG, GriddedField


class FishingService:
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.c = (config or load_config())["fishing"]

    def score(self, sst: Optional[GriddedField], chl: Optional[GriddedField]) -> FishingResult:
        notes: List[str] = []
        if sst is None and chl is None:
            return FishingResult(notes=["No SST or Chl-a field supplied; no zones computed."])
        base = sst if sst is not None else chl
        lat, lon = base.lat, base.lon
        if sst is None:
            notes.append("SST unavailable; scored from Chl-a only.")
        if chl is None:
            notes.append("Chl-a unavailable; scored from SST only.")
        if sst is not None and chl is not None and (chl.lat.shape != lat.shape or chl.lon.shape != lon.shape
                                                   or not np.allclose(chl.lat, lat) or not np.allclose(chl.lon, lon)):
            chl = chl.resample_to(lat, lon)
            notes.append("Chl-a resampled (nearest cell) onto the SST grid.")

        c, w = self.c, self.c["weights"]
        comps: Dict[str, np.ndarray] = {}
        front_mask = np.zeros(base.values.shape, dtype=bool)
        if sst is not None:
            g = sst.gradient_km()
            comps["sst_front"] = np.clip(g / c["sst_front_saturation"], 0, 1)
            lo, hi = c["sst_optimal_c"]
            dist = np.maximum(np.maximum(lo - sst.values, sst.values - hi), 0.0)
            comps["sst_preference"] = np.clip(1.0 - dist / c["sst_margin_c"], 0, 1)
            with np.errstate(invalid="ignore"):
                front_mask |= g > c["sst_front_threshold"]
        if chl is not None:
            g = chl.gradient_km(log10=True)
            comps["chl_front"] = np.clip(g / c["chl_front_saturation"], 0, 1)
            lo, hi = c["chl_optimal_mgm3"]
            with np.errstate(invalid="ignore", divide="ignore"):
                lv = np.log10(np.where(chl.values > 0, chl.values, np.nan))
                dist = np.maximum(np.maximum(math.log10(lo) - lv, lv - math.log10(hi)), 0.0)
            comps["chl_preference"] = np.clip(1.0 - dist / math.log10(c["chl_margin_factor"]), 0, 1)
            with np.errstate(invalid="ignore"):
                front_mask |= g > c["chl_front_threshold"]

        num = np.zeros(base.values.shape)
        den = np.zeros(base.values.shape)
        for name, arr in comps.items():
            ok = np.isfinite(arr)
            num += np.where(ok, arr * w[name], 0.0)
            den += np.where(ok, w[name], 0.0)
        with np.errstate(invalid="ignore", divide="ignore"):
            total = np.where(den > 0, num / den, np.nan)

        cand = front_mask & np.isfinite(total) & (total >= c["min_score"])
        result = FishingResult(candidate_cells=int(cand.sum()), notes=notes)
        # local maxima over 3x3 (NaN-safe), best-first with separation
        padded = np.pad(np.where(np.isfinite(total), total, -np.inf), 1, constant_values=-np.inf)
        neigh = np.max([padded[1 + di: 1 + di + total.shape[0], 1 + dj: 1 + dj + total.shape[1]]
                        for di in (-1, 0, 1) for dj in (-1, 0, 1) if (di, dj) != (0, 0)], axis=0)
        peaks = cand & (total >= neigh)
        idx = np.argwhere(peaks)
        order = sorted(idx.tolist(), key=lambda ij: (-total[ij[0], ij[1]], ij[0], ij[1]))  # deterministic ties

        chosen: List[List[int]] = []
        for i, j in order:
            if len(chosen) >= c["top_n"]:
                break
            if all(self._km(lat[i], lon[j], lat[a], lon[b]) >= c["min_separation_km"] for a, b in chosen):
                chosen.append([i, j])
                result.zones.append(self._zone(i, j, lat, lon, total, comps, sst, chl))
        return result

    @staticmethod
    def _km(la1, lo1, la2, lo2) -> float:
        dy = (la2 - la1) * KM_PER_DEG
        dx = (lo2 - lo1) * KM_PER_DEG * math.cos(math.radians((la1 + la2) / 2))
        return math.hypot(dx, dy)

    def _zone(self, i, j, lat, lon, total, comps, sst, chl) -> FishingZone:
        c = self.c
        parts = {k: round(float(v[i, j]), 3) for k, v in comps.items() if np.isfinite(v[i, j])}
        reasons = []
        if parts.get("sst_front", 0) * c["sst_front_saturation"] > c["sst_front_threshold"]:
            reasons.append(f"SST front: gradient {parts['sst_front'] * c['sst_front_saturation']:.3f} degC/km")
        if parts.get("chl_front", 0) * c["chl_front_saturation"] > c["chl_front_threshold"]:
            reasons.append(f"Chl-a front: gradient {parts['chl_front'] * c['chl_front_saturation']:.3f} log10/km")
        if sst is not None and np.isfinite(sst.values[i, j]) and parts.get("sst_preference", 0) >= 1.0:
            reasons.append(f"SST {sst.values[i, j]:.1f} degC within preferred band")
        if chl is not None and np.isfinite(chl.values[i, j]) and parts.get("chl_preference", 0) >= 1.0:
            reasons.append(f"Chl-a {chl.values[i, j]:.2f} mg/m3 within preferred band")
        return FishingZone(lat=float(lat[i]), lon=float(lon[j]), score=round(float(total[i, j]), 4),
                           components=parts, reasons=reasons, source_cell=[int(i), int(j)])
