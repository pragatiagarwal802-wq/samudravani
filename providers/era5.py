"""ERA5 reanalysis provider (Copernicus CDS) for wind, waves and SST.

Credentials: CDSAPI_URL + CDSAPI_KEY, or the ~/.cdsapirc file the CDS website tells you to
create (the cdsapi client reads it). Values are spatially averaged over the bounding box,
one observation per variable per hourly timestamp.

ERA5 is a reanalysis: data appear about ERA5_LAG_DAYS (default 5) days after real time. Windows
that start later than that are answered NOT_AVAILABLE at once instead of sending CDS a request
that would queue and then fail; windows that straddle the limit are clipped to it. Live plans
therefore rely on the forecast provider; ERA5 serves past windows (trends, validation).
"""
from __future__ import annotations

import os
import pathlib
import tempfile
from datetime import datetime, timedelta, timezone
from typing import List

import numpy as np

from models.schemas import Observation, ProviderResult, ProviderStatus, RiskQuery
from providers._util import expand_netcdf, pick_var, to_datetime, to_utc_naive
from providers.base import DataProvider
from services.fields import GriddedField

DATASET = "reanalysis-era5-single-levels"
CDS_VARIABLES = [
    "10m_u_component_of_wind",
    "10m_v_component_of_wind",
    "significant_height_of_combined_wind_waves_and_swell",
    "sea_surface_temperature",
]


class Era5Provider(DataProvider):
    name = "era5"

    def __init__(self, half_width: float = 0.5):
        self.half_width = half_width

    def _request(self, query: RiskQuery) -> dict:
        box = query.region(self.half_width)
        start = to_utc_naive(query.window.start)
        end = to_utc_naive(query.window.end)
        days, d = [], start.date()
        while d <= end.date():
            days.append(d)
            d += timedelta(days=1)
        return {
            "product_type": ["reanalysis"],
            "variable": CDS_VARIABLES,
            "year": sorted({f"{x.year:04d}" for x in days}),
            "month": sorted({f"{x.month:02d}" for x in days}),
            "day": sorted({f"{x.day:02d}" for x in days}),
            "time": [f"{h:02d}:00" for h in range(24)],
            "area": [box.north, box.west, box.south, box.east],  # N, W, S, E
            "data_format": "netcdf",
            "download_format": "unarchived",
        }

    @staticmethod
    def _credentials():
        """(url, key) from the environment, or (None, None) when ~/.cdsapirc should be used."""
        return os.environ.get("CDSAPI_URL"), os.environ.get("CDSAPI_KEY")

    @staticmethod
    def _rc_file() -> pathlib.Path:
        return pathlib.Path(os.environ.get("CDSAPI_RC", pathlib.Path.home() / ".cdsapirc"))

    def _configured(self) -> bool:
        url, key = self._credentials()
        return bool(url and key) or self._rc_file().is_file()

    def fetch(self, query: RiskQuery) -> ProviderResult:
        if not self._configured():
            return ProviderResult(
                provider=self.name,
                status=ProviderStatus.NOT_AVAILABLE,
                message="CDSAPI_URL / CDSAPI_KEY (or ~/.cdsapirc) are not set.",
            )
        latest = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=float(os.environ.get("ERA5_LAG_DAYS", 5)))
        if to_utc_naive(query.window.start) > latest:
            return ProviderResult(
                provider=self.name, status=ProviderStatus.NOT_AVAILABLE,
                message=f"ERA5 is published about 5 days late; latest available is around {latest:%Y-%m-%d}.",
            )
        if to_utc_naive(query.window.end) > latest:
            query = query.model_copy(update={"window": query.window.model_copy(update={"end": latest})})
        url, key = self._credentials()
        try:
            import cdsapi
            import xarray as xr
        except ImportError as exc:
            return ProviderResult(provider=self.name, status=ProviderStatus.ERROR, message=f"Missing dependency: {exc}")

        try:
            target = os.path.join(tempfile.mkdtemp(prefix="era5_"), "era5.nc")
            client = cdsapi.Client(url=url, key=key, quiet=True) if url and key else cdsapi.Client(quiet=True)
            client.retrieve(DATASET, self._request(query), target)
            datasets = [xr.open_dataset(p) for p in expand_netcdf(target)]
            ds = xr.merge(datasets, compat="override").load()
            for d in datasets:
                d.close()
            obs = self._normalize(ds, query)
            grids = self._grids(ds, query)
        except Exception as exc:  # network, auth, queue and decode failures
            return ProviderResult(provider=self.name, status=ProviderStatus.ERROR, message=f"ERA5 request failed: {exc}")

        if not obs:
            return ProviderResult(
                provider=self.name, status=ProviderStatus.NOT_AVAILABLE,
                message="ERA5 returned no data inside the requested window.",
            )
        return ProviderResult(provider=self.name, status=ProviderStatus.OK, observations=obs, grids=grids)

    def health(self) -> dict:
        ok = self._configured()
        return {"configured": ok, "detail": "credentials present" if ok else "CDSAPI_URL/CDSAPI_KEY or ~/.cdsapirc not set"}

    def _grids(self, ds, query: RiskQuery) -> dict:
        """Worst-case (max over window) wave height and wind speed, mean wind-from direction."""
        tname = pick_var(ds, ["valid_time", "time"])
        vlat, vlon = pick_var(ds, ["latitude", "lat"]), pick_var(ds, ["longitude", "lon"])
        u, v, swh = pick_var(ds, ["u10"]), pick_var(ds, ["v10"]), pick_var(ds, ["swh"])
        start, end = to_utc_naive(query.window.start), to_utc_naive(query.window.end)
        idx = [i for i, t in enumerate(np.atleast_1d(ds[tname].values))
               if (ts := to_datetime(t)) is not None and start <= ts <= end]
        if not (idx and vlat and vlon):
            return {}
        sub = ds.isel({tname: idx})
        lat, lon = ds[vlat].values, ds[vlon].values
        grids = {}

        def cube(name):
            return sub[name].transpose(tname, vlat, vlon).values

        try:
            if swh:
                grids["wave_height"] = GriddedField(lat, lon, np.nanmax(cube(swh), axis=0), "wave_height", "m").to_payload()
            if u and v:
                cu, cv = cube(u), cube(v)
                grids["wind_speed"] = GriddedField(lat, lon, np.nanmax(np.hypot(cu, cv), axis=0), "wind_speed", "m/s").to_payload()
                from_deg = np.rad2deg(np.arctan2(-np.nanmean(cu, axis=0), -np.nanmean(cv, axis=0))) % 360.0
                grids["wind_from_deg"] = GriddedField(lat, lon, from_deg, "wind_from_deg", "deg").to_payload()
        except ValueError:  # degenerate grid (fewer than 2 points) or unexpected dims
            return {}
        return grids

    def _normalize(self, ds, query: RiskQuery) -> List[Observation]:
        tname = pick_var(ds, ["valid_time", "time"])
        u, v = pick_var(ds, ["u10"]), pick_var(ds, ["v10"])
        swh, sst = pick_var(ds, ["swh"]), pick_var(ds, ["sst"])
        start, end = to_utc_naive(query.window.start), to_utc_naive(query.window.end)

        def spatial_mean(name):
            da = ds[name]
            dims = [x for x in da.dims if x != tname]
            return da.mean(dim=dims, skipna=True).values

        series = {}
        if u and v:
            series["wind_speed"] = (np.hypot(spatial_mean(u), spatial_mean(v)), "m/s")
        if swh:
            series["wave_height"] = (spatial_mean(swh), "m")
        if sst:
            series["sea_surface_temp"] = (spatial_mean(sst) - 273.15, "degC")

        obs: List[Observation] = []
        for i, t in enumerate(np.atleast_1d(ds[tname].values)):
            ts = to_datetime(t)
            if ts is None or not (start <= ts <= end):
                continue
            for var, (vals, unit) in series.items():
                val = float(np.atleast_1d(vals)[i])
                obs.append(Observation(
                    variable=var, value=None if np.isnan(val) else val,
                    unit=unit, timestamp=ts, source=self.name,
                ))
        return obs
