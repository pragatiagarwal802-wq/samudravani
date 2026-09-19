"""ASCAT near-real-time scatterometer wind provider.

ASCAT swath products (EUMETSAT/KNMI OSI SAF L2 coastal/25 km, or CMEMS L3 NRT)
are NetCDF files. Files are taken from:
  * ASCAT_DATA_DIR      - directory of NetCDF files (scanned recursively), and/or
  * ASCAT_URL_TEMPLATE  - URL with {date} (YYYYMMDD), downloaded per day (optional
                          ASCAT_AUTH_USER / ASCAT_AUTH_PASSWORD for basic auth).
Each swath file is clipped to the bbox/window, QC-filtered and reduced to one
wind_speed mean, wind_speed max and wind_direction (vector mean) observation.
"""
from __future__ import annotations

import os
import tempfile
from datetime import datetime, timedelta
from typing import List, Optional

import numpy as np

from models.schemas import Observation, ProviderResult, ProviderStatus, RiskQuery
from providers._util import in_bbox, pick_var, to_datetime, to_utc_naive
from providers.base import DataProvider


class AscatProvider(DataProvider):
    name = "ascat"

    def __init__(self, half_width: float = 0.5, data_dir: Optional[str] = None, url_template: Optional[str] = None):
        self.half_width = half_width
        self.data_dir = data_dir or os.environ.get("ASCAT_DATA_DIR")
        self.url_template = url_template or os.environ.get("ASCAT_URL_TEMPLATE")

    def _files(self, start: datetime, end: datetime) -> List[str]:
        files: List[str] = []
        if self.data_dir and os.path.isdir(self.data_dir):
            for root, _, names in os.walk(self.data_dir):
                files += [os.path.join(root, n) for n in names if n.endswith((".nc", ".nc4"))]
        if self.url_template:
            import requests

            auth = None
            if os.environ.get("ASCAT_AUTH_USER"):
                auth = (os.environ["ASCAT_AUTH_USER"], os.environ.get("ASCAT_AUTH_PASSWORD", ""))
            tmp = tempfile.mkdtemp(prefix="ascat_")
            d = start.date()
            while d <= end.date():
                url = self.url_template.format(date=d.strftime("%Y%m%d"))
                r = requests.get(url, auth=auth, timeout=120)
                if r.status_code == 200:
                    path = os.path.join(tmp, f"{d:%Y%m%d}.nc")
                    with open(path, "wb") as fh:
                        fh.write(r.content)
                    files.append(path)
                d += timedelta(days=1)
        return files

    def fetch(self, query: RiskQuery) -> ProviderResult:
        if not (self.data_dir or self.url_template):
            return ProviderResult(
                provider=self.name, status=ProviderStatus.NOT_AVAILABLE,
                message="Neither ASCAT_DATA_DIR nor ASCAT_URL_TEMPLATE is configured.",
            )
        try:
            import xarray as xr
        except ImportError as exc:
            return ProviderResult(provider=self.name, status=ProviderStatus.ERROR, message=f"Missing dependency: {exc}")

        box = query.region(self.half_width)
        start, end = to_utc_naive(query.window.start), to_utc_naive(query.window.end)
        obs: List[Observation] = []
        skipped = 0
        try:
            for path in self._files(start, end):
                try:
                    with xr.open_dataset(path, decode_times=True) as ds:
                        obs += self._normalize(ds, box, start, end)
                except Exception:
                    skipped += 1
        except Exception as exc:
            return ProviderResult(provider=self.name, status=ProviderStatus.ERROR, message=f"ASCAT ingest failed: {exc}")

        if not obs:
            return ProviderResult(
                provider=self.name, status=ProviderStatus.NOT_AVAILABLE,
                message="No ASCAT swath covers the bbox/window." + (f" {skipped} file(s) unreadable." if skipped else ""),
            )
        status = ProviderStatus.PARTIAL if skipped else ProviderStatus.OK
        return ProviderResult(
            provider=self.name, status=status, observations=obs,
            message=f"{skipped} file(s) unreadable." if skipped else None,
        )

    def _normalize(self, ds, box, start, end) -> List[Observation]:
        vs = pick_var(ds, ["wind_speed", "wind_speed_10m", "ws"])
        vd = pick_var(ds, ["wind_dir", "wind_direction", "wind_to_dir", "wd"])
        vlat, vlon = pick_var(ds, ["lat", "latitude"]), pick_var(ds, ["lon", "longitude"])
        vt = pick_var(ds, ["time", "measurement_time"])
        if not (vs and vlat and vlon and vt):
            raise ValueError("unrecognised ASCAT file layout")

        speed = np.asarray(ds[vs].values, dtype="float64")
        lat = np.broadcast_to(np.asarray(ds[vlat].values, dtype="float64"), speed.shape) if ds[vlat].ndim == speed.ndim else None
        lon = np.broadcast_to(np.asarray(ds[vlon].values, dtype="float64"), speed.shape) if ds[vlon].ndim == speed.ndim else None
        if lat is None or lon is None:  # 1-D lat/lon grid (L3): build a mesh
            lat, lon = np.meshgrid(ds[vlat].values, ds[vlon].values, indexing="ij")
            speed = speed.reshape(lat.shape) if speed.size == lat.size else np.squeeze(speed)
        times = np.asarray(ds[vt].values)
        if times.shape != speed.shape:
            try:
                times = np.broadcast_to(times.reshape(times.shape + (1,) * (speed.ndim - times.ndim)), speed.shape)
            except ValueError:
                times = np.full(speed.shape, times.flat[0])

        mask = in_bbox(lat, lon, box) & np.isfinite(speed) & (speed >= 0)
        qc = pick_var(ds, ["wvc_quality_flag", "quality_flag", "wind_quality"])
        if qc and ds[qc].shape == speed.shape:
            mask &= np.asarray(ds[qc].values) == 0  # conservative: any flag bit set -> drop
        t_ok = (times >= np.datetime64(start)) & (times <= np.datetime64(end))
        mask &= t_ok
        if not mask.any():
            return []

        sel = speed[mask]
        ts = to_datetime(np.sort(times[mask])[mask.sum() // 2])
        out = [
            Observation(variable="wind_speed", value=float(sel.mean()), unit="m/s", timestamp=ts, source=self.name),
            Observation(variable="wind_speed_max", value=float(sel.max()), unit="m/s", timestamp=ts, source=self.name),
        ]
        if vd:
            rad = np.deg2rad(np.asarray(ds[vd].values, dtype="float64")[mask])
            rad = rad[np.isfinite(rad)]
            if rad.size:
                deg = float(np.rad2deg(np.arctan2(np.sin(rad).mean(), np.cos(rad).mean())) % 360.0)
                out.append(Observation(variable="wind_direction", value=deg, unit="deg", timestamp=ts, source=self.name))
        return out
