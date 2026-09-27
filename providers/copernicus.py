"""Copernicus Marine (CMEMS) provider: daily gridded SST and Chlorophyll-a.

Datasets (both global, daily, gap-free L4 so fronts are not broken by cloud):
  sst  METOFFICE-GLO-SST-L4-NRT-OBS-SST-V2                        analysed_sst (K)   0.05 deg
       product SST_GLO_SST_L4_NRT_OBSERVATIONS_010_001
  chl  cmems_obs-oc_glo_bgc-plankton_nrt_l4-gapfree-multi-4km_P1D  CHL (mg m-3)       ~4 km
       product OCEANCOLOUR_GLO_BGC_L4_NRT_009_102

Sources, in order:
  * COPERNICUS_DATA_DIR - directory of NetCDF files already downloaded with
    `copernicusmarine subset` (scanned recursively; a file is used for every
    variable it contains). No network access or account is needed.
  * otherwise the Copernicus Marine Toolbox streams a lazy subset. Credentials
    come from COPERNICUSMARINE_SERVICE_USERNAME / COPERNICUSMARINE_SERVICE_PASSWORD
    or the file written by `copernicusmarine login`.

These are observation products published with a lag of about a day, while voyage
windows usually start now or later. The provider therefore looks back
COPERNICUS_LOOKBACK_DAYS (default 5) before the window start and uses the most
recent day with data in the box. The day used is the observation timestamp and
is named in the result message, so stale data is never silently passed off as current.

Streaming requests fetch a whole region and keep it in memory for COPERNICUS_CACHE_HOURS (default 3),
so ports share one download and the toolbox's ~20 s catalogue lookup is paid once per region and day.
The region is COPERNICUS_REGION ("south,west,north,east", default the Gujarat coast 18,66,24,74) when
it contains the query box, otherwise the box snapped outward to REGION_DEG tiles.
"""
from __future__ import annotations

import math
import os
import pathlib
import threading
import time
from datetime import datetime, timedelta
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np

from models.schemas import GridPayload, Observation, ProviderResult, ProviderStatus, RiskQuery
from providers._util import pick_var, to_datetime, to_utc_naive, wrap_lon
from providers.base import DataProvider
from services.fields import GriddedField

# key -> dataset id, variable, output unit, front threshold per km (SST degC/km, Chl-a log10/km;
# same values as the fishing config's front thresholds)
DEFAULT_DATASETS: Dict[str, dict] = {
    "sst": {"dataset": "METOFFICE-GLO-SST-L4-NRT-OBS-SST-V2", "variable": "analysed_sst",
            "unit": "degC", "front": 0.03},
    "chl": {"dataset": "cmems_obs-oc_glo_bgc-plankton_nrt_l4-gapfree-multi-4km_P1D", "variable": "CHL",
            "unit": "mg/m3", "front": 0.01},
}


REGION_DEG = 2.0
_REGION_CACHE: Dict[tuple, Tuple[float, object]] = {}
_REGION_LOCK = threading.Lock()
_KEY_LOCKS: Dict[tuple, threading.Lock] = {}


def _region(box):
    """(south, west, north, east) to download for the box: the configured coast region if it contains
    the box, else the box snapped outward to REGION_DEG tiles."""
    s, w, n, e = (float(x) for x in os.environ.get("COPERNICUS_REGION", "18,66,24,74").split(","))
    if s <= box.south and w <= box.west and box.north <= n and box.east <= e:
        return s, w, n, e
    t = REGION_DEG
    return (math.floor(box.south / t) * t, math.floor(box.west / t) * t,
            math.ceil(box.north / t) * t, math.ceil(box.east / t) * t)


def _credentials_file() -> pathlib.Path:
    base = os.environ.get("COPERNICUSMARINE_CREDENTIALS_DIRECTORY")
    return (pathlib.Path(base) if base else pathlib.Path.home()) / ".copernicusmarine" / ".copernicusmarine-credentials"


class CopernicusMarineProvider(DataProvider):
    name = "copernicus"

    def __init__(self, half_width: float = 0.5, datasets: Optional[Dict[str, dict]] = None,
                 lookback_days: Optional[int] = None, data_dir: Optional[str] = None,
                 opener: Optional[Callable[..., object]] = None):
        self.half_width = half_width
        self.datasets = datasets or DEFAULT_DATASETS
        self.lookback_days = int(lookback_days if lookback_days is not None
                                 else os.environ.get("COPERNICUS_LOOKBACK_DAYS", 5))
        self.data_dir = data_dir or os.environ.get("COPERNICUS_DATA_DIR")
        self._opener = opener  # test hook: opener(spec, box, start, end) -> xarray.Dataset

    # -- configuration -------------------------------------------------------
    @staticmethod
    def _env_credentials() -> Tuple[Optional[str], Optional[str]]:
        return os.environ.get("COPERNICUSMARINE_SERVICE_USERNAME"), os.environ.get("COPERNICUSMARINE_SERVICE_PASSWORD")

    def _local(self) -> bool:
        return bool(self.data_dir and os.path.isdir(self.data_dir))

    def _remote(self) -> bool:
        user, pwd = self._env_credentials()
        return bool(user and pwd) or _credentials_file().is_file()

    def health(self) -> dict:
        if self._opener is not None or self._local():
            return {"configured": True, "detail": "local files" if self._local() else "custom opener"}
        ok = self._remote()
        return {"configured": ok, "detail": "credentials present" if ok else
                "COPERNICUSMARINE_SERVICE_USERNAME/PASSWORD, `copernicusmarine login` or COPERNICUS_DATA_DIR not set"}

    # -- data access ---------------------------------------------------------
    def _open(self, spec: dict, box, start: datetime, end: datetime):
        if self._opener is not None:
            return self._opener(spec, box, start, end)
        if self._local():
            return self._open_local(spec, box, start, end)
        return self._open_region(spec, box, start, end)

    def _open_region(self, spec: dict, box, start: datetime, end: datetime):
        """In-memory subset for the tile-snapped region around the box, fetched once per region/day."""
        import copernicusmarine

        south, west, north, east = _region(box)
        key = (spec["dataset"], spec["variable"], south, west, north, east, start.date(), end.date())
        ttl = float(os.environ.get("COPERNICUS_CACHE_HOURS", 3)) * 3600
        with _REGION_LOCK:
            lock = _KEY_LOCKS.setdefault(key, threading.Lock())
        with lock:
            hit = _REGION_CACHE.get(key)
            if hit is None or time.time() - hit[0] > ttl:
                user, pwd = self._env_credentials()
                ds = copernicusmarine.open_dataset(
                    dataset_id=spec["dataset"], variables=[spec["variable"]],
                    minimum_longitude=west, maximum_longitude=east,
                    minimum_latitude=south, maximum_latitude=north,
                    start_datetime=start, end_datetime=end,
                    coordinates_selection_method="inside",  # clips to what exists, e.g. a window ending in the future
                    username=user or None, password=pwd or None,
                ).load()
                with _REGION_LOCK:
                    for k in [k for k, (t0, _) in _REGION_CACHE.items() if time.time() - t0 > ttl]:
                        del _REGION_CACHE[k]
                    _REGION_CACHE[key] = (time.time(), ds)
                hit = _REGION_CACHE[key]
        return hit[1].copy()  # _normalize clips to the exact box

    def _open_local(self, spec: dict, box, start: datetime, end: datetime):
        """All files holding the variable, loaded and joined along time (one file per day is fine)."""
        import xarray as xr

        parts = []
        for root, _, names in os.walk(self.data_dir):
            for n in sorted(names):
                if n.endswith((".nc", ".nc4")):
                    with xr.open_dataset(os.path.join(root, n)) as ds:
                        v = pick_var(ds, [spec["variable"]])
                        if v:
                            parts.append(ds[[v]].load())
        if not parts:
            raise FileNotFoundError(f"no file with '{spec['variable']}' in {self.data_dir}")
        if len(parts) == 1 or "time" not in parts[0].dims:
            return parts[-1]
        return xr.concat(parts, dim="time").sortby("time")

    # -- provider ------------------------------------------------------------
    def fetch(self, query: RiskQuery) -> ProviderResult:
        if not (self._opener is not None or self._local() or self._remote()):
            return ProviderResult(
                provider=self.name, status=ProviderStatus.NOT_AVAILABLE,
                message="Copernicus Marine credentials (COPERNICUSMARINE_SERVICE_USERNAME/PASSWORD "
                        "or `copernicusmarine login`) or COPERNICUS_DATA_DIR are not set.",
            )
        try:
            import xarray  # noqa: F401
            if self._opener is None and not self._local():
                import copernicusmarine  # noqa: F401
        except ImportError as exc:
            return ProviderResult(provider=self.name, status=ProviderStatus.ERROR, message=f"Missing dependency: {exc}")

        box = query.region(self.half_width)
        end = to_utc_naive(query.window.end)
        start = to_utc_naive(query.window.start) - timedelta(days=self.lookback_days)
        obs: List[Observation] = []
        grids: Dict[str, GridPayload] = {}
        used: List[str] = []
        problems: List[str] = []
        for key, spec in self.datasets.items():
            try:
                ds = self._open(spec, box, start, end)
                try:
                    o, grid, day = self._normalize(ds, key, spec, box, start, end)
                finally:
                    ds.close()
                if grid is None:
                    problems.append(f"{key}: no data in the box between {start:%Y-%m-%d} and {end:%Y-%m-%d}")
                    continue
                obs += o
                grids[key] = grid
                used.append(f"{key} {spec['dataset']} @ {day:%Y-%m-%d}")
            except Exception as exc:  # network, auth, catalogue and decode failures
                problems.append(f"{key} ({spec['dataset']}): {type(exc).__name__}: {exc}".rstrip(": "))

        msg = "; ".join(used + problems) or None
        if not grids:
            status = ProviderStatus.NOT_AVAILABLE if all("no data" in p for p in problems) else ProviderStatus.ERROR
            return ProviderResult(provider=self.name, status=status, message=msg)
        return ProviderResult(provider=self.name, status=ProviderStatus.PARTIAL if problems else ProviderStatus.OK,
                              observations=obs, grids=grids, message=msg)

    def _normalize(self, ds, key: str, spec: dict, box, start: datetime, end: datetime):
        """Latest day in [start, end] with data in the box -> (observations, grid, day)."""
        vname = pick_var(ds, [spec["variable"]])
        vlat, vlon = pick_var(ds, ["latitude", "lat"]), pick_var(ds, ["longitude", "lon"])
        vt = pick_var(ds, ["time"])
        if not (vname and vlat and vlon):
            raise ValueError("unrecognised Copernicus file layout")
        da = ds[vname]
        for extra in [d for d in da.dims if d not in (vlat, vlon, vt)]:  # e.g. a length-1 depth axis
            da = da.isel({extra: 0})
        da = da.assign_coords({vlon: wrap_lon(da[vlon].values)}).sortby([vlat, vlon])
        da = da.sel({vlat: slice(box.south, box.north), vlon: slice(box.west, box.east)})
        if da.sizes[vlat] < 2 or da.sizes[vlon] < 2:
            return [], None, None

        times = [to_datetime(t) for t in np.atleast_1d(da[vt].values)] if vt in da.dims else [None]
        order = sorted((i for i, t in enumerate(times) if t is None or start <= t <= end),
                       key=lambda i: times[i] or datetime.min, reverse=True)
        for i in order:
            field = np.asarray((da.isel({vt: i}) if vt in da.dims else da).values, dtype="float64")
            if not np.isfinite(field).any():
                continue
            units = str(da.attrs.get("units", "")).lower()
            if key == "sst" and (units in ("k", "kelvin") or np.nanmean(field) > 200):
                field = field - 273.15
            if key == "chl":
                field = np.where(field > 0, field, np.nan)
            gf = GriddedField(da[vlat].values, da[vlon].values, field, key, spec["unit"])
            return self._metrics(gf, key, spec, times[i]), gf.to_payload(), times[i]
        return [], None, None

    def _metrics(self, gf: GriddedField, key: str, spec: dict, ts: Optional[datetime]) -> List[Observation]:
        with np.errstate(invalid="ignore"):
            grad = gf.gradient_km(log10=key == "chl")
        valid = np.isfinite(grad)
        src, unit = self.name, spec["unit"]
        obs = [Observation(variable=f"{key}_mean", value=float(np.nanmean(gf.values)), unit=unit, timestamp=ts, source=src)]
        if valid.any():
            obs += [
                Observation(variable=f"{key}_front_gradient_max", value=float(np.nanmax(grad)),
                            unit=f"{'log10 ' if key == 'chl' else ''}{unit}/km", timestamp=ts, source=src),
                Observation(variable=f"{key}_front_fraction", value=float((grad[valid] > spec["front"]).mean()),
                            unit="fraction", timestamp=ts, source=src),
            ]
        return obs
