"""MOSDAC (ISRO) provider: INSAT-3S sea-surface temperature (optionally a chlorophyll product).

API, as used by MOSDAC's official download client (mdapi.py, https://www.mosdac.gov.in/tools):
  search    GET  https://mosdac.gov.in/apios/datasets.json   datasetId, startTime, endTime (YYYY-MM-DD),
                 boundingBox (W,S,E,N), count  -> {"entries": [{"id", "identifier", "updated"}, ...]} newest first.
                 No login needed.
  token     POST https://mosdac.gov.in/download_api/gettoken  {"username", "password"} -> {"access_token", ...}
  download  GET  https://mosdac.gov.in/download_api/download  ?id=<entry id>, Authorization: Bearer <token>
  logout    POST https://mosdac.gov.in/download_api/logout    {"username"}

Credentials: MOSDAC_USERNAME / MOSDAC_PASSWORD (a MOSDAC SSO account). Datasets:
  MOSDAC_SST_DATASET  default 3SIMG_L2B_SST (INSAT-3S imager, half-hourly, full disk, cloud-free sea only)
  MOSDAC_CHL_DATASET  optional (no default): an ocean-colour chlorophyll product ID from the MOSDAC catalogue

Each scene is HDF5 with the field and Latitude/Longitude (1-D or 2-D). INSAT-3DS L2B SST files hold
SST_VAR (1D-Var retrieval, used), SST_REG (regression retrieval, fallback) and SST_FCT (the model
first guess, never used: it is not a satellite measurement), all in kelvin, on 2-D scaled int16
Latitude/Longitude. The newest scenes (up to
MOSDAC_MAX_SCENES, default 3) are clipped to the box, averaged onto a regular 0.05 deg grid (cells
without cloud-free data stay empty) and composited, which fills gaps one scene leaves.
"""
from __future__ import annotations

import os
import tempfile
import warnings
from datetime import timedelta
from typing import Dict, List, Optional, Tuple

import numpy as np

from models.schemas import GridPayload, Observation, ProviderResult, ProviderStatus, RiskQuery
from providers._util import to_utc_naive, wrap_lon
from providers.base import DataProvider
from services.fields import GriddedField

SEARCH_URL = "https://mosdac.gov.in/apios/datasets.json"
API_BASE = "https://mosdac.gov.in/download_api"
GRID_DEG = 0.05


def default_datasets() -> Dict[str, dict]:
    ds = {"sst": {"dataset": os.environ.get("MOSDAC_SST_DATASET", "3SIMG_L2B_SST"),
                  "names": ["SST_VAR", "SST_REG", "SST", "sea_surface_temperature"], "unit": "degC", "front": 0.03}}
    chl = os.environ.get("MOSDAC_CHL_DATASET")
    if chl:
        ds["chl"] = {"dataset": chl, "names": ["chlor_a", "CHL", "chl", "Chlorophyll", "chlorophyll_a"],
                     "unit": "mg/m3", "front": 0.01}
    return ds


class MosdacProvider(DataProvider):
    name = "mosdac"

    def __init__(self, half_width: float = 0.5, datasets: Optional[Dict[str, dict]] = None,
                 max_scenes: Optional[int] = None, lookback_days: int = 1, session=None):
        self.half_width = half_width
        self.datasets = datasets or default_datasets()
        self.max_scenes = int(max_scenes or os.environ.get("MOSDAC_MAX_SCENES", 3))
        self.lookback_days = lookback_days
        self._session = session  # test hook

    @staticmethod
    def _creds() -> Tuple[Optional[str], Optional[str]]:
        return os.environ.get("MOSDAC_USERNAME"), os.environ.get("MOSDAC_PASSWORD")

    def health(self) -> dict:
        ok = all(self._creds())
        return {"configured": ok, "detail": "credentials present" if ok else "MOSDAC_USERNAME/MOSDAC_PASSWORD not set"}

    # -- API -------------------------------------------------------------------
    def search(self, http, dataset: str, box, start, end) -> List[dict]:
        params = {"datasetId": dataset, "startTime": f"{start:%Y-%m-%d}", "endTime": f"{end:%Y-%m-%d}",
                  "boundingBox": f"{box.west},{box.south},{box.east},{box.north}", "count": self.max_scenes}
        r = http.get(SEARCH_URL, params=params, timeout=60)
        if r.status_code != 200:  # MOSDAC answers 500 "Data unavailable for given parameters" when empty
            return []
        entries = r.json().get("entries") or []
        return sorted(entries, key=lambda e: e.get("updated", ""), reverse=True)[: self.max_scenes]

    def token(self, http) -> str:
        user, pwd = self._creds()
        r = http.post(f"{API_BASE}/gettoken", json={"username": user, "password": pwd}, timeout=60)
        js = r.json() if r.content else {}
        if r.status_code != 200 or not js.get("access_token"):
            raise PermissionError(f"MOSDAC login failed: {js.get('error') or js.get('message') or r.status_code}")
        return js["access_token"]

    def download(self, http, token: str, entry: dict, folder: str) -> str:
        r = http.get(f"{API_BASE}/download", params={"id": entry["id"]},
                     headers={"Authorization": f"Bearer {token}"}, timeout=300, stream=True)
        if r.status_code != 200:
            raise RuntimeError(f"download {entry.get('identifier')}: HTTP {r.status_code}")
        path = os.path.join(folder, os.path.basename(entry.get("identifier") or f"{entry['id']}.h5"))
        with open(path, "wb") as fh:
            for chunk in r.iter_content(1 << 20):
                fh.write(chunk)
        return path

    def logout(self, http) -> None:
        try:
            http.post(f"{API_BASE}/logout", json={"username": self._creds()[0]}, timeout=10)
        except Exception:
            pass  # best effort; the session expires on its own

    # -- provider ----------------------------------------------------------------
    def fetch(self, query: RiskQuery) -> ProviderResult:
        if not all(self._creds()):
            return ProviderResult(provider=self.name, status=ProviderStatus.NOT_AVAILABLE,
                                  message="MOSDAC_USERNAME / MOSDAC_PASSWORD are not set.")
        try:
            import requests
        except ImportError as exc:
            return ProviderResult(provider=self.name, status=ProviderStatus.ERROR, message=f"Missing dependency: {exc}")

        box = query.region(self.half_width)
        end = to_utc_naive(query.window.end)
        start = to_utc_naive(query.window.start) - timedelta(days=self.lookback_days)
        obs: List[Observation] = []
        grids: Dict[str, GridPayload] = {}
        problems: List[str] = []
        http = self._session or requests.Session()
        token = None
        try:
            for key, spec in self.datasets.items():
                entries = self.search(http, spec["dataset"], box, start, end)
                if not entries:
                    problems.append(f"{key}: no {spec['dataset']} scene for the box/window")
                    continue
                token = token or self.token(http)
                fields = []
                with tempfile.TemporaryDirectory(prefix="mosdac_") as folder:
                    for e in entries:
                        try:
                            fields.append(regrid_scene(self.download(http, token, e, folder), spec["names"], box))
                        except Exception as exc:
                            problems.append(f"{e.get('identifier')}: {exc}")
                gf = composite(fields, key, spec, box)
                if gf is None:
                    problems.append(f"{key}: scenes had no cloud-free sea pixels in the box")
                    continue
                grids[key] = gf.to_payload()
                obs += metrics(gf, key, spec, self.name)
        except PermissionError as exc:
            return ProviderResult(provider=self.name, status=ProviderStatus.ERROR, message=str(exc))
        except Exception as exc:
            return ProviderResult(provider=self.name, status=ProviderStatus.ERROR, message=f"MOSDAC request failed: {exc}")
        finally:
            if token:
                self.logout(http)

        msg = "; ".join(problems) or None
        if not grids:
            return ProviderResult(provider=self.name, status=ProviderStatus.NOT_AVAILABLE,
                                  message=msg or "MOSDAC returned no usable scenes.")
        return ProviderResult(provider=self.name, status=ProviderStatus.PARTIAL if problems else ProviderStatus.OK,
                              observations=obs, grids=grids, message=msg)


# --- HDF5 reading and regridding --------------------------------------------------------------


def _read(f, candidates: List[str]) -> Optional[np.ndarray]:
    """First dataset whose (leaf) name matches a candidate, case-insensitively, with CF scaling applied."""
    wanted = [c.lower() for c in candidates]
    found = []
    f.visititems(lambda name, obj: found.append(obj) if hasattr(obj, "shape")
                 and name.split("/")[-1].lower() in wanted else None)
    if not found:
        return None
    ds = min(found, key=lambda d: wanted.index(d.name.split("/")[-1].lower()))
    a = np.asarray(ds[()], dtype="float64")
    attrs = {k.lower(): v for k, v in ds.attrs.items()}

    def attr(name):
        v = attrs.get(name)
        return None if v is None else float(np.ravel(v)[0])

    for fill in ("_fillvalue", "missing_value", "fill_value", "invalid_value"):
        v = attr(fill)
        if v is not None:
            a[a == v] = np.nan
    scale, offset = attr("scale_factor"), attr("add_offset")
    if scale is not None:
        a = a * scale
    if offset is not None:
        a = a + offset
    return np.squeeze(a)


def regrid_scene(path: str, names: List[str], box) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Scene -> (lat axis, lon axis, field) on a regular GRID_DEG grid over the box (NaN = no data)."""
    import h5py

    with h5py.File(path, "r") as f:
        field = _read(f, names)
        lat = _read(f, ["Latitude", "lat", "latitude"])
        lon = _read(f, ["Longitude", "lon", "longitude"])
    if field is None or lat is None or lon is None:
        raise ValueError("unrecognised MOSDAC file layout")
    if lat.ndim == 1 and lon.ndim == 1:
        lat, lon = np.meshgrid(lat, lon, indexing="ij")
    if field.shape != lat.shape:
        raise ValueError(f"field {field.shape} and coordinates {lat.shape} differ")
    lon = wrap_lon(lon)
    ok = (np.isfinite(field) & np.isfinite(lat) & np.isfinite(lon)
          & (lat >= box.south) & (lat <= box.north) & (lon >= box.west) & (lon <= box.east))
    la = np.round(np.arange(box.south, box.north + 1e-9, GRID_DEG), 4)
    lo = np.round(np.arange(box.west, box.east + 1e-9, GRID_DEG), 4)
    out = np.full((la.size, lo.size), np.nan)
    if ok.any():
        i = np.clip(np.rint((lat[ok] - box.south) / GRID_DEG).astype(int), 0, la.size - 1)
        j = np.clip(np.rint((lon[ok] - box.west) / GRID_DEG).astype(int), 0, lo.size - 1)
        total, count = np.zeros_like(out), np.zeros_like(out)
        np.add.at(total, (i, j), field[ok])
        np.add.at(count, (i, j), 1)
        with np.errstate(invalid="ignore"):
            out = np.where(count > 0, total / count, np.nan)
    return la, lo, out


def composite(scenes: List[Tuple[np.ndarray, np.ndarray, np.ndarray]], key: str, spec: dict, box) -> Optional[GriddedField]:
    """Per-cell mean of the scenes; SST converted to degC when stored in kelvin."""
    if not scenes:
        return None
    la, lo = scenes[0][0], scenes[0][1]
    stack = np.stack([s[2] for s in scenes])
    if not np.isfinite(stack).any():
        return None
    with warnings.catch_warnings():  # all-NaN cells (land, cloud) are expected
        warnings.simplefilter("ignore", RuntimeWarning)
        field = np.nanmean(stack, axis=0)
    if key == "sst" and np.nanmean(field) > 200:
        field = field - 273.15
    if key == "chl":
        field = np.where(field > 0, field, np.nan)
    return GriddedField(la, lo, field, key, spec["unit"])


def metrics(gf: GriddedField, key: str, spec: dict, source: str) -> List[Observation]:
    with np.errstate(invalid="ignore"):
        grad = gf.gradient_km(log10=key == "chl")
    valid = np.isfinite(grad)
    unit = spec["unit"]
    obs = [Observation(variable=f"{key}_mean", value=float(np.nanmean(gf.values)), unit=unit, source=source)]
    if valid.any():
        obs += [
            Observation(variable=f"{key}_front_gradient_max", value=float(np.nanmax(grad)),
                        unit=f"{'log10 ' if key == 'chl' else ''}{unit}/km", source=source),
            Observation(variable=f"{key}_front_fraction", value=float((grad[valid] > spec["front"]).mean()),
                        unit="fraction", source=source),
        ]
    return obs
