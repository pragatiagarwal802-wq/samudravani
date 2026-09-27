"""MOSDAC (official API flow, HDF5 regridding) and the ERA5 publication-lag guard, offline."""
from __future__ import annotations

import io
from datetime import datetime, timedelta

import h5py
import numpy as np
import pytest

from models.schemas import BoundingBox, Location, ProviderStatus, RiskQuery, TimeWindow
from providers.era5 import Era5Provider
from providers.mosdac import API_BASE, SEARCH_URL, MosdacProvider

BOX = BoundingBox(south=20.3, west=69.7, north=21.3, east=70.8)
NOW = datetime(2026, 9, 27, 6)
QUERY = RiskQuery(location=Location(lat=20.8, lon=70.25), window=TimeWindow(start=NOW, end=NOW + timedelta(hours=24)), bbox=BOX)


def insat_scene(cloud_rows=slice(0, 0)) -> bytes:
    """Same layout as a real INSAT-3DS L2B SST file: 2-D int16 Latitude/Longitude (scale 0.01, fill
    32767), SST_VAR/SST_REG/SST_FCT as float32 kelvin (fill -999) with a leading time axis. Has a
    front at 20.8 N, a cloud band, and pixels far outside the box. SST_FCT is off by 5 K so using
    it would be caught."""
    lat1 = np.linspace(19.0, 23.0, 161)
    lon1 = np.linspace(68.0, 72.5, 181)
    lat, lon = np.meshgrid(lat1, lon1, indexing="ij")
    sst_k = (273.15 + 28.0 + np.tanh((lat - 20.8) / 0.08)).astype("float32")
    sst_k[cloud_rows] = -999.0
    buf = io.BytesIO()
    with h5py.File(buf, "w") as f:
        for name, field in (("SST_VAR", sst_k), ("SST_REG", sst_k), ("SST_FCT", np.where(sst_k > 0, sst_k + 5, sst_k))):
            d = f.create_dataset(name, data=field[None])
            d.attrs["_FillValue"] = np.float32(-999.0)
            d.attrs["units"] = b"K"
        for name, v in (("Latitude", lat), ("Longitude", lon)):
            d = f.create_dataset(name, data=np.round(v / 0.01).astype("int16"))
            d.attrs["_FillValue"], d.attrs["scale_factor"], d.attrs["add_offset"] = np.int16(32767), np.float32(0.01), np.float32(0.0)
    return buf.getvalue()


class Resp:
    def __init__(self, status=200, js=None, content=b""):
        self.status_code, self._js, self.content = status, js, content or (b"{}" if js is not None else b"")

    def json(self):
        return self._js

    def iter_content(self, n):
        for i in range(0, len(self.content), n):
            yield self.content[i:i + n]


class FakeMosdac:
    """Serves the documented endpoints; two scenes, the newer one partly cloudy."""

    def __init__(self, login_ok=True):
        self.calls, self.login_ok = [], login_ok
        self.files = {"2": insat_scene(cloud_rows=slice(60, 100)), "1": insat_scene()}

    def get(self, url, params=None, headers=None, timeout=None, stream=False):
        self.calls.append(("GET", url, params, headers))
        if url == SEARCH_URL:
            return Resp(js={"entries": [
                {"id": "1", "identifier": "3SIMG_27SEP2026_0530_L2B_SST_V01R00.h5", "updated": "2026-09-27T05:30:00Z"},
                {"id": "2", "identifier": "3SIMG_27SEP2026_0600_L2B_SST_V01R00.h5", "updated": "2026-09-27T06:00:00Z"},
            ]})
        if url == f"{API_BASE}/download":
            assert headers["Authorization"] == "Bearer tok"
            return Resp(content=self.files[params["id"]])
        return Resp(404, {})

    def post(self, url, json=None, timeout=None):
        self.calls.append(("POST", url, json, None))
        if url.endswith("/gettoken"):
            return Resp(js={"access_token": "tok", "refresh_token": "r"}) if self.login_ok else \
                Resp(400, {"error": "Bad Input: Invalid Username/Email."})
        return Resp(js={"message": "logged out"})


@pytest.fixture
def creds(monkeypatch):
    monkeypatch.setenv("MOSDAC_USERNAME", "fisher")
    monkeypatch.setenv("MOSDAC_PASSWORD", "secret")
    monkeypatch.delenv("MOSDAC_CHL_DATASET", raising=False)


def test_mosdac_downloads_regrids_and_composites_scenes(creds):
    http = FakeMosdac()
    res = MosdacProvider(session=http).fetch(QUERY)
    assert res.status is ProviderStatus.OK, res.message
    sst = res.grids["sst"]
    vals = np.array([[np.nan if v is None else v for v in row] for row in sst.values])
    assert abs(sst.lat[1] - sst.lat[0] - 0.05) < 1e-9 and sst.lat[0] == BOX.south
    assert 26.5 < np.nanmin(vals) and np.nanmax(vals) < 29.5  # kelvin -> degC, fill values dropped
    assert np.isfinite(vals).mean() > 0.95  # the clear scene fills the other's cloud band
    obs = {o.variable: o.value for o in res.observations}
    assert obs["sst_front_fraction"] > 0 and obs["sst_front_gradient_max"] > 0.03
    # official flow: search (no auth) -> token -> downloads (newest first) -> logout
    kinds = [(m, u.rsplit("/", 1)[-1]) for m, u, *_ in http.calls]
    assert kinds[0] == ("GET", "datasets.json") and kinds[1] == ("POST", "gettoken") and kinds[-1] == ("POST", "logout")
    assert [c[2]["id"] for c in http.calls if c[1].endswith("/download")] == ["2", "1"]
    search = http.calls[0][2]
    assert search["datasetId"] == "3SIMG_L2B_SST" and search["boundingBox"] == "69.7,20.3,70.8,21.3"


def test_mosdac_bad_login_is_an_error(creds):
    res = MosdacProvider(session=FakeMosdac(login_ok=False)).fetch(QUERY)
    assert res.status is ProviderStatus.ERROR and "Invalid Username" in res.message


def test_mosdac_without_credentials(monkeypatch):
    monkeypatch.delenv("MOSDAC_USERNAME", raising=False)
    monkeypatch.delenv("MOSDAC_PASSWORD", raising=False)
    assert MosdacProvider().fetch(QUERY).status is ProviderStatus.NOT_AVAILABLE


def test_era5_skips_windows_it_cannot_have_yet(monkeypatch, tmp_path):
    monkeypatch.setenv("CDSAPI_URL", "https://cds.example/api")
    monkeypatch.setenv("CDSAPI_KEY", "k")
    now = datetime.utcnow()
    q = RiskQuery(location=Location(lat=20.8, lon=70.25), window=TimeWindow(start=now, end=now + timedelta(hours=24)))
    res = Era5Provider().fetch(q)  # would otherwise queue a CDS request for the future
    assert res.status is ProviderStatus.NOT_AVAILABLE and "5 days" in res.message


def test_era5_reads_cdsapirc(monkeypatch, tmp_path):
    monkeypatch.delenv("CDSAPI_URL", raising=False)
    monkeypatch.delenv("CDSAPI_KEY", raising=False)
    rc = tmp_path / ".cdsapirc"
    monkeypatch.setenv("CDSAPI_RC", str(rc))
    assert Era5Provider().health()["configured"] is False
    rc.write_text("url: https://cds.climate.copernicus.eu/api\nkey: abc\n")
    assert Era5Provider().health()["configured"] is True
