"""Regular lat/lon grids shared by routing and fishing services."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np

from models.schemas import GridPayload

KM_PER_DEG = 111.0


@dataclass
class GriddedField:
    """values[i, j] at (lat[i], lon[j]); lat and lon are 1-D and strictly monotonic."""

    lat: np.ndarray
    lon: np.ndarray
    values: np.ndarray
    name: str = ""
    unit: str = ""
    _cache: dict = field(default_factory=dict, repr=False, compare=False)

    def __post_init__(self):
        self.lat = np.asarray(self.lat, dtype="float64")
        self.lon = np.asarray(self.lon, dtype="float64")
        self.values = np.asarray(self.values, dtype="float64")
        if self.values.shape != (self.lat.size, self.lon.size):
            raise ValueError(f"values shape {self.values.shape} != ({self.lat.size}, {self.lon.size})")
        for ax in (self.lat, self.lon):
            d = np.diff(ax)
            if ax.size < 2 or not (np.all(d > 0) or np.all(d < 0)):
                raise ValueError("lat/lon must be strictly monotonic with at least 2 points")

    def to_payload(self) -> GridPayload:
        rows = [[None if not np.isfinite(v) else float(v) for v in row] for row in self.values]
        return GridPayload(name=self.name, unit=self.unit, lat=self.lat.tolist(), lon=self.lon.tolist(), values=rows)

    @classmethod
    def from_payload(cls, p: GridPayload) -> "GriddedField":
        vals = np.array([[np.nan if v is None else v for v in row] for row in p.values], dtype="float64")
        return cls(np.array(p.lat), np.array(p.lon), vals, p.name, p.unit)

    @staticmethod
    def _nearest_idx(axis: np.ndarray, x: float) -> Optional[int]:
        i = int(np.argmin(np.abs(axis - x)))
        step = abs(float(np.median(np.diff(axis))))
        return i if abs(axis[i] - x) <= step else None  # outside the grid extent

    def nearest(self, lat: float, lon: float) -> float:
        """Nearest-cell value; NaN when outside the grid or the cell has no data."""
        i, j = self._nearest_idx(self.lat, lat), self._nearest_idx(self.lon, lon)
        return float("nan") if i is None or j is None else float(self.values[i, j])

    def resample_to(self, lat: np.ndarray, lon: np.ndarray) -> "GriddedField":
        out = np.full((len(lat), len(lon)), np.nan)
        ii = [self._nearest_idx(self.lat, x) for x in lat]
        jj = [self._nearest_idx(self.lon, x) for x in lon]
        for a, i in enumerate(ii):
            if i is None:
                continue
            for b, j in enumerate(jj):
                if j is not None:
                    out[a, b] = self.values[i, j]
        return GriddedField(np.asarray(lat), np.asarray(lon), out, self.name, self.unit)

    def gradient_km(self, log10: bool = False) -> np.ndarray:
        """Gradient magnitude per km (NaN-propagating)."""
        f = self.values
        if log10:
            with np.errstate(invalid="ignore", divide="ignore"):
                f = np.where(f > 0, np.log10(f), np.nan)
        cos_lat = np.clip(np.cos(np.deg2rad(self.lat)), 1e-6, None)[:, None]
        dy = np.gradient(self.lat)[:, None] * KM_PER_DEG
        dx = np.gradient(self.lon)[None, :] * KM_PER_DEG * cos_lat
        gy = np.gradient(f, axis=0) / dy
        gx = np.gradient(f, axis=1) / dx
        return np.hypot(gx, gy)
