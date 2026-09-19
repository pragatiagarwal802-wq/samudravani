"""MOSDAC (ISRO) provider: high-resolution SST and Chlorophyll-a plus front metrics.

Credentials: MOSDAC_USERNAME / MOSDAC_PASSWORD. Endpoints are relative to
MOSDAC_API_BASE (default https://mosdac.gov.in/download_api). The token,
search and download paths and the response field names below follow the
MOSDAC download API as understood at authoring time and are overridable
via constructor arguments, because the API is not versioned; verify them
against a live account before relying on this in production.

Fronts are detected as gradient magnitude of the field (SST in degC/km,
Chl-a as log10 gradient per km); we report the peak gradient and the
fraction of pixels above a front threshold.
"""
from __future__ import annotations

import os
import tempfile
from typing import Dict, List, Optional

import numpy as np

from models.schemas import Observation, ProviderResult, ProviderStatus, RiskQuery
from providers._util import in_bbox, pick_var, to_utc_naive
from providers.base import DataProvider

KM_PER_DEG = 111.0

# variable -> (dataset id, candidate netCDF names, unit, front threshold per km)
DEFAULT_DATASETS: Dict[str, dict] = {
    "sst": {"dataset": "3DIMG_L2B_SST", "names": ["SST", "sst", "sea_surface_temperature"], "unit": "degC", "front": 0.05},
    "chl": {"dataset": "OCM_L2_CHL", "names": ["chlor_a", "chl", "CHL", "chlorophyll_a"], "unit": "mg/m3", "front": 0.02},
}


class MosdacProvider(DataProvider):
    name = "mosdac"

    def __init__(self, half_width: float = 0.5, datasets: Optional[Dict[str, dict]] = None,
                 token_path: str = "/gettoken", search_path: str = "/search", download_path: str = "/download",
                 max_files: int = 8):
        self.half_width = half_width
        self.datasets = datasets or DEFAULT_DATASETS
        self.base = os.environ.get("MOSDAC_API_BASE", "https://mosdac.gov.in/download_api").rstrip("/")
        self.token_path, self.search_path, self.download_path = token_path, search_path, download_path
        self.max_files = max_files
        self._token: Optional[str] = None

    # -- API -----------------------------------------------------------------
    def authenticate(self, session) -> None:
        user, pwd = os.environ.get("MOSDAC_USERNAME"), os.environ.get("MOSDAC_PASSWORD")
        if not user or not pwd:
            raise PermissionError("MOSDAC_USERNAME / MOSDAC_PASSWORD are not set.")
        r = session.post(self.base + self.token_path, json={"username": user, "password": pwd}, timeout=60)
        r.raise_for_status()
        token = r.json().get("access_token")
        if not token:
            raise PermissionError("MOSDAC login returned no access_token.")
        self._token = token
        session.headers["Authorization"] = f"Bearer {token}"

    def search(self, session, dataset: str, query: RiskQuery) -> List[str]:
        box = query.region(self.half_width)
        params = {
            "datasetId": dataset,
            "startTime": to_utc_naive(query.window.start).strftime("%Y-%m-%d"),
            "endTime": to_utc_naive(query.window.end).strftime("%Y-%m-%d"),
            "boundingBox": f"{box.west},{box.south},{box.east},{box.north}",
            "count": self.max_files,
        }
        r = session.get(self.base + self.search_path, params=params, timeout=60)
        r.raise_for_status()
        js = r.json()
        entries = js.get("entries") or js.get("results") or []
        ids = [e.get("id") or e.get("identifier") for e in entries]
        return [i for i in ids if i][: self.max_files]

    def download(self, session, product_id: str, folder: str) -> str:
        r = session.get(self.base + self.download_path, params={"id": product_id}, timeout=300)
        r.raise_for_status()
        path = os.path.join(folder, f"{abs(hash(product_id))}.h5")
        with open(path, "wb") as fh:
            fh.write(r.content)
        return path

    # -- provider ------------------------------------------------------------
    def fetch(self, query: RiskQuery) -> ProviderResult:
        if not (os.environ.get("MOSDAC_USERNAME") and os.environ.get("MOSDAC_PASSWORD")):
            return ProviderResult(
                provider=self.name, status=ProviderStatus.NOT_AVAILABLE,
                message="MOSDAC_USERNAME / MOSDAC_PASSWORD are not set.",
            )
        try:
            import requests
            import xarray as xr
        except ImportError as exc:
            return ProviderResult(provider=self.name, status=ProviderStatus.ERROR, message=f"Missing dependency: {exc}")

        box = query.region(self.half_width)
        obs: List[Observation] = []
        problems: List[str] = []
        try:
            with requests.Session() as session:
                self.authenticate(session)
                folder = tempfile.mkdtemp(prefix="mosdac_")
                for key, spec in self.datasets.items():
                    for pid in self.search(session, spec["dataset"], query):
                        try:
                            path = self.download(session, pid, folder)
                            with xr.open_dataset(path) as ds:
                                obs += self._normalize(ds, key, spec, box)
                        except Exception as exc:
                            problems.append(f"{spec['dataset']}/{pid}: {exc}")
        except PermissionError as exc:
            return ProviderResult(provider=self.name, status=ProviderStatus.ERROR, message=str(exc))
        except Exception as exc:
            return ProviderResult(provider=self.name, status=ProviderStatus.ERROR, message=f"MOSDAC request failed: {exc}")

        msg = "; ".join(problems) or None
        if not obs:
            return ProviderResult(provider=self.name, status=ProviderStatus.NOT_AVAILABLE,
                                  message=msg or "MOSDAC search returned no usable products.")
        return ProviderResult(provider=self.name, status=ProviderStatus.PARTIAL if problems else ProviderStatus.OK,
                              observations=obs, message=msg)

    def _normalize(self, ds, key: str, spec: dict, box) -> List[Observation]:
        vname = pick_var(ds, spec["names"])
        vlat, vlon = pick_var(ds, ["lat", "latitude", "Latitude"]), pick_var(ds, ["lon", "longitude", "Longitude"])
        if not (vname and vlat and vlon):
            raise ValueError("unrecognised MOSDAC file layout")
        lat, lon = np.asarray(ds[vlat].values, dtype="float64"), np.asarray(ds[vlon].values, dtype="float64")
        field = np.squeeze(np.asarray(ds[vname].values, dtype="float64"))
        if lat.ndim == 1 and lon.ndim == 1:
            lat2, lon2 = np.meshgrid(lat, lon, indexing="ij")
        else:
            lat2, lon2 = lat, lon
        if field.shape != lat2.shape:
            raise ValueError("field/coordinate shape mismatch")

        fill = ds[vname].attrs.get("_FillValue")
        if fill is not None:
            field = np.where(field == fill, np.nan, field)
        if key == "sst" and np.nanmean(field) > 200:  # Kelvin -> degC
            field = field - 273.15
        if key == "chl":
            field = np.where(field > 0, field, np.nan)

        inside = in_bbox(lat2, lon2, box)
        if not (inside & np.isfinite(field)).any():
            return []
        f = np.where(inside, field, np.nan)

        # gradient per km on the (assumed regular) grid; chl in log10 space
        g_field = np.log10(f) if key == "chl" else f
        if lat.ndim == 1 and lon.ndim == 1 and lat.size > 1 and lon.size > 1:
            dy = abs(float(np.median(np.diff(lat)))) * KM_PER_DEG
            mean_lat = float(np.nanmean(lat2[inside]))
            dx = abs(float(np.median(np.diff(lon)))) * KM_PER_DEG * np.cos(np.deg2rad(mean_lat))
            gy, gx = np.gradient(g_field, dy, dx)
            grad = np.hypot(gx, gy)
        else:
            raise ValueError("front detection needs a regular 1-D lat/lon grid")

        valid = np.isfinite(grad)
        if not valid.any():
            return []
        thr = spec["front"]
        src = self.name
        return [
            Observation(variable=f"{key}_mean", value=float(np.nanmean(f)), unit=spec["unit"], source=src),
            Observation(variable=f"{key}_front_gradient_max", value=float(np.nanmax(grad)),
                        unit=f"{'log10 ' if key == 'chl' else ''}{spec['unit']}/km", source=src),
            Observation(variable=f"{key}_front_fraction", value=float((grad[valid] > thr).mean()),
                        unit="fraction", source=src),
        ]
