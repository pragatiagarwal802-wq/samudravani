"""Open-Meteo forecast provider: wind, gusts, rain, visibility, waves, currents and SST.

ERA5 is reanalysis published about five days late, so it cannot describe a voyage
window that starts now. Open-Meteo serves hourly forecasts (weather up to 16 days,
marine up to ~8 days, plus recent past days) from national weather models
(ECMWF, NCEP, Meteo-France WAM ...), with no API key.

  weather  https://api.open-meteo.com/v1/forecast
  marine   https://marine-api.open-meteo.com/v1/marine

The free API is for non-commercial use; production/commercial use needs an
Open-Meteo subscription (set OPENMETEO_API_KEY and the customer-* base URLs via
OPENMETEO_WEATHER_URL / OPENMETEO_MARINE_URL).

The provider samples the query box on a regular grid (OPENMETEO_GRID_DEG, default
0.5 deg, close to the wave model's resolution) and returns:
  observations  hourly box means of each variable (the risk agent takes the worst hour)
  grids         wave_height and wind_speed as the per-cell maximum over the window,
                wind_from_deg as the per-cell vector mean (same shape as ERA5's grids),
                sst as the per-cell mean (a coarse fallback when no satellite SST is configured)
"""
from __future__ import annotations

import os
import warnings
from datetime import datetime
from typing import Dict, List, Optional, Sequence

import numpy as np

from models.schemas import Observation, ProviderResult, ProviderStatus, RiskQuery
from providers._util import to_utc_naive
from providers.base import DataProvider
from services.fields import GriddedField

WEATHER_VARS = ["wind_speed_10m", "wind_direction_10m", "wind_gusts_10m", "precipitation", "visibility"]
MARINE_VARS = ["wave_height", "wave_direction", "wave_period", "ocean_current_velocity", "sea_surface_temperature"]
BATCH = 50           # locations per request; large batches time out
MAX_POINTS = 300     # grid is coarsened beyond this (each location counts against the rate limit)


def _urls():
    return (os.environ.get("OPENMETEO_WEATHER_URL", "https://api.open-meteo.com/v1/forecast"),
            os.environ.get("OPENMETEO_MARINE_URL", "https://marine-api.open-meteo.com/v1/marine"))


def fetch_hourly(lats: Sequence[float], lons: Sequence[float], start: datetime, end: datetime,
                 session=None, timeout: float = 60) -> Dict[str, object]:
    """Hourly series for each (lat, lon) pair, UTC, clipped to [start, end].

    Returns {"time": [datetime...], var: ndarray (n_points, n_hours), ...} using the output
    names and units below. Missing values are NaN.
      wind_speed m/s, wind_from_deg deg, wind_gust m/s, precipitation mm/h, visibility km,
      wave_height m, wave_from_deg deg, wave_period s, current_speed m/s, sst degC
    """
    import requests

    http = session or requests
    weather_url, marine_url = _urls()
    key = os.environ.get("OPENMETEO_API_KEY")
    common = {"timezone": "GMT", "start_date": f"{start:%Y-%m-%d}", "end_date": f"{end:%Y-%m-%d}"}
    if key:
        common["apikey"] = key

    def get(url, variables, extra):
        rows = []
        for i in range(0, len(lats), BATCH):
            params = {**common, **extra, "hourly": ",".join(variables),
                      "latitude": ",".join(f"{x:.4f}" for x in lats[i:i + BATCH]),
                      "longitude": ",".join(f"{x:.4f}" for x in lons[i:i + BATCH])}
            for attempt in (1, 2):  # one retry: the free API occasionally stalls
                try:
                    r = http.get(url, params=params, timeout=timeout)
                    break
                except requests.exceptions.Timeout:
                    if attempt == 2:
                        raise
            if r.status_code != 200:
                raise RuntimeError(f"{url} HTTP {r.status_code}: {r.text[:200]}")
            js = r.json()
            rows += js if isinstance(js, list) else [js]
        return rows

    weather = get(weather_url, WEATHER_VARS, {"wind_speed_unit": "ms"})
    marine = get(marine_url, MARINE_VARS, {"cell_selection": "sea"})

    times = [datetime.fromisoformat(t) for t in weather[0]["hourly"]["time"]]
    keep = [i for i, t in enumerate(times) if start <= t <= end]

    def cube(rows, name, scale=1.0):
        out = np.full((len(rows), len(keep)), np.nan)
        for p, row in enumerate(rows):
            series = row.get("hourly", {}).get(name) or []
            idx = {t: k for k, t in enumerate(row.get("hourly", {}).get("time", []))}
            for c, i in enumerate(keep):
                k = idx.get(weather[0]["hourly"]["time"][i])
                v = series[k] if k is not None and k < len(series) else None
                out[p, c] = np.nan if v is None else float(v) * scale
        return out

    return {
        "time": [times[i] for i in keep],
        "wind_speed": cube(weather, "wind_speed_10m"),
        "wind_from_deg": cube(weather, "wind_direction_10m"),
        "wind_gust": cube(weather, "wind_gusts_10m"),
        "precipitation": cube(weather, "precipitation"),
        "visibility": cube(weather, "visibility", 1 / 1000.0),
        "wave_height": cube(marine, "wave_height"),
        "wave_from_deg": cube(marine, "wave_direction"),
        "wave_period": cube(marine, "wave_period"),
        "current_speed": cube(marine, "ocean_current_velocity", 1 / 3.6),  # km/h -> m/s
        "sst": cube(marine, "sea_surface_temperature"),
    }


def _nanmean(a, axis):
    with warnings.catch_warnings():  # all-NaN slices (e.g. land cells) are expected
        warnings.simplefilter("ignore", RuntimeWarning)
        return np.nanmean(a, axis=axis)


def _nanmax(a, axis):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        return np.nanmax(a, axis=axis)


class OpenMeteoProvider(DataProvider):
    name = "openmeteo"

    # output name -> (observation variable, unit); only these feed the risk agent
    OBS = {
        "wave_height": ("wave_height", "m"),
        "wind_speed": ("wind_speed", "m/s"),
        "wind_gust": ("wind_gust", "m/s"),
        "visibility": ("visibility", "km"),
        "current_speed": ("current_speed", "m/s"),
        "precipitation": ("precipitation", "mm/h"),
        "sst": ("sea_surface_temp", "degC"),
    }

    def __init__(self, half_width: float = 0.5, grid_deg: Optional[float] = None, session=None):
        self.half_width = half_width
        self.grid_deg = float(grid_deg or os.environ.get("OPENMETEO_GRID_DEG", 0.5))
        self._session = session  # test hook

    @staticmethod
    def enabled() -> bool:
        return os.environ.get("OPENMETEO_ENABLED", "1") != "0"

    def health(self) -> dict:
        ok = self.enabled()
        return {"configured": ok, "detail": "public API, no key needed" if ok else "disabled (OPENMETEO_ENABLED=0)"}

    def _axes(self, box):
        step = self.grid_deg
        while True:
            lat = np.round(np.arange(box.south, box.north + 1e-9, step), 4)
            lon = np.round(np.arange(box.west, box.east + 1e-9, step), 4)
            if lat.size * lon.size <= MAX_POINTS:
                break
            step *= 1.5
        if lat.size < 2:
            lat = np.array([box.south, box.north]) if box.north > box.south else np.array([box.south - step, box.south])
        if lon.size < 2:
            lon = np.array([box.west, box.east]) if box.east > box.west else np.array([box.west, box.west + step])
        return lat, lon

    def fetch(self, query: RiskQuery) -> ProviderResult:
        if not self.enabled():
            return ProviderResult(provider=self.name, status=ProviderStatus.NOT_AVAILABLE,
                                  message="Open-Meteo is disabled (OPENMETEO_ENABLED=0).")
        box = query.region(self.half_width)
        start, end = to_utc_naive(query.window.start), to_utc_naive(query.window.end)
        lat, lon = self._axes(box)
        la2, lo2 = np.meshgrid(lat, lon, indexing="ij")
        try:
            data = fetch_hourly(la2.ravel().tolist(), lo2.ravel().tolist(), start, end, session=self._session)
        except Exception as exc:  # network, HTTP and decode failures
            return ProviderResult(provider=self.name, status=ProviderStatus.ERROR, message=f"Open-Meteo request failed: {exc}")
        times: List[datetime] = data["time"]
        if not times:
            return ProviderResult(provider=self.name, status=ProviderStatus.NOT_AVAILABLE,
                                  message="Open-Meteo returned no hours inside the requested window.")

        obs: List[Observation] = []
        for name, (var, unit) in self.OBS.items():
            means = _nanmean(data[name], axis=0)  # box mean per hour
            for t, v in zip(times, means):
                if np.isfinite(v):
                    obs.append(Observation(variable=var, value=float(v), unit=unit, timestamp=t, source=self.name))
        if not obs:
            return ProviderResult(provider=self.name, status=ProviderStatus.NOT_AVAILABLE,
                                  message="Open-Meteo returned no values for the box.")

        shape = (lat.size, lon.size)
        grids = {}
        try:
            wave = _nanmax(data["wave_height"], axis=1).reshape(shape)
            wind = _nanmax(data["wind_speed"], axis=1).reshape(shape)
            rad = np.deg2rad(data["wind_from_deg"])
            from_deg = (np.rad2deg(np.arctan2(_nanmean(np.sin(rad), 1), _nanmean(np.cos(rad), 1))) % 360.0).reshape(shape)
            grids["wave_height"] = GriddedField(lat, lon, wave, "wave_height", "m").to_payload()
            grids["wind_speed"] = GriddedField(lat, lon, wind, "wind_speed", "m/s").to_payload()
            grids["wind_from_deg"] = GriddedField(lat, lon, from_deg, "wind_from_deg", "deg").to_payload()
            if np.isfinite(data["sst"]).any():  # coarse fallback for the ocean agent's front detection
                grids["sst"] = GriddedField(lat, lon, _nanmean(data["sst"], 1).reshape(shape), "sst", "degC").to_payload()
        except ValueError:
            grids = {}
        missing = [n for n in ("wave_height", "wind_speed") if not np.isfinite(data[n]).any()]
        return ProviderResult(
            provider=self.name, status=ProviderStatus.PARTIAL if missing else ProviderStatus.OK,
            observations=obs, grids=grids,
            message=(f"no {', '.join(missing)} in the box" if missing else None),
        )
