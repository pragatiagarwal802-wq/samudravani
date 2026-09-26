"""Copernicus Marine SST / Chl-a provider.

Synthetic datasets reproduce the CMEMS layouts (time/latitude/longitude, SST in
kelvin as `analysed_sst`, Chl-a as `CHL` in mg m-3, NaN over land) so no
network or account is needed.
"""
from __future__ import annotations

from datetime import datetime

import numpy as np
import pandas as pd
import pytest
import xarray as xr

from models.schemas import ProviderResult, ProviderStatus, RiskQuery
from providers.copernicus import DEFAULT_DATASETS, CopernicusMarineProvider
from services.data_service import DataService
from tests.test_pipeline import (
    AREA, IS_LAND, LAND, LAT, LATS, LONS, VERAVAL, WINDOW, FakeProvider, make_service, run,
)

DAYS = pd.date_range("2026-09-16", "2026-09-19", freq="D")  # the product lags the 2026-09-20 window
FRONT = np.tanh((LAT - 21.0) / 0.1)


def cmems(var: str, daily: np.ndarray, units: str, blank_last_day=False) -> xr.Dataset:
    cube = np.repeat(np.where(IS_LAND, np.nan, daily)[None], len(DAYS), axis=0)
    if blank_last_day:
        cube[-1] = np.nan  # e.g. the newest file is not processed yet over this area
    return xr.Dataset({var: (("time", "latitude", "longitude"), cube, {"units": units})},
                      coords={"time": DAYS, "latitude": LATS, "longitude": LONS})


SST = cmems("analysed_sst", 273.15 + 28.0 + FRONT, "kelvin", blank_last_day=True)
CHL = cmems("CHL", 10 ** (-0.5 + 0.3 * FRONT), "milligram m-3")
QUERY = RiskQuery(location=VERAVAL, window=WINDOW, bbox=AREA)


def opener(spec, box, start, end):
    return {"analysed_sst": SST, "CHL": CHL}[spec["variable"]].copy()


def test_normalises_sst_and_chl_from_latest_day_with_data():
    res = CopernicusMarineProvider(opener=opener).fetch(QUERY)
    assert res.status is ProviderStatus.OK, res.message
    assert set(res.grids) == {"sst", "chl"}

    sst = np.array([[np.nan if v is None else v for v in row] for row in res.grids["sst"].values])
    assert res.grids["sst"].unit == "degC" and 26.5 < np.nanmin(sst) and np.nanmax(sst) < 29.5  # kelvin converted
    assert np.isnan(sst[IS_LAND]).all()

    obs = {o.variable: o for o in res.observations}
    assert obs["sst_mean"].timestamp == datetime(2026, 9, 18)  # 09-19 is blank -> previous day
    assert obs["chl_mean"].timestamp == datetime(2026, 9, 19)
    assert obs["sst_front_fraction"].value > 0 and obs["chl_front_gradient_max"].value > 0
    assert "sst METOFFICE-GLO-SST-L4-NRT-OBS-SST-V2 @ 2026-09-18" in res.message


def test_lookback_limits_how_stale_data_may_be():
    res = CopernicusMarineProvider(opener=opener, lookback_days=0).fetch(QUERY)
    assert res.status is ProviderStatus.NOT_AVAILABLE and not res.grids
    assert "no data in the box" in res.message


def test_partial_when_one_dataset_fails():
    def half(spec, box, start, end):
        if spec["variable"] == "CHL":
            raise ConnectionError("catalogue unreachable")
        return SST.copy()

    res = CopernicusMarineProvider(opener=half).fetch(QUERY)
    assert res.status is ProviderStatus.PARTIAL and set(res.grids) == {"sst"}
    assert "catalogue unreachable" in res.message


def test_not_available_without_credentials_or_files(tmp_path, monkeypatch):
    for var in ("COPERNICUSMARINE_SERVICE_USERNAME", "COPERNICUSMARINE_SERVICE_PASSWORD", "COPERNICUS_DATA_DIR"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("COPERNICUSMARINE_CREDENTIALS_DIRECTORY", str(tmp_path))
    p = CopernicusMarineProvider()
    assert p.health()["configured"] is False
    assert p.fetch(QUERY).status is ProviderStatus.NOT_AVAILABLE


def test_dataset_ids_match_the_catalogue():
    assert DEFAULT_DATASETS["sst"]["dataset"] == "METOFFICE-GLO-SST-L4-NRT-OBS-SST-V2"
    assert DEFAULT_DATASETS["chl"]["dataset"] == "cmems_obs-oc_glo_bgc-plankton_nrt_l4-gapfree-multi-4km_P1D"


# --- through the agent graph ------------------------------------------------------

def write_daily_files(folder):
    """One file per product per day, as `copernicusmarine subset` would produce."""
    for ds, name in ((SST, "sst"), (CHL, "chl")):
        for i, day in enumerate(DAYS):
            ds.isel(time=[i]).to_netcdf(folder / f"{name}_{day:%Y%m%d}.nc")


def service_with_copernicus(tmp_path, mosdac: ProviderResult = None) -> DataService:
    base = make_service(tmp_path)  # fake ERA5/ASCAT/MOSDAC from the pipeline tests
    data_dir = tmp_path / "cmems"
    data_dir.mkdir()
    write_daily_files(data_dir)
    providers = [base.providers["era5"], base.providers["ascat"], CopernicusMarineProvider(data_dir=str(data_dir))]
    providers.append(FakeProvider("mosdac", mosdac or ProviderResult(provider="mosdac", status=ProviderStatus.NOT_AVAILABLE)))
    return DataService(providers, db_path=str(tmp_path / "cmems.sqlite"))


def test_pipeline_plans_fishing_trip_from_copernicus_files(tmp_path):
    final = run(service_with_copernicus(tmp_path), origin=VERAVAL)
    plan = final["plan"]
    assert plan.status.value in ("PROCEED", "PROCEED_WITH_CAUTION"), plan.summary
    assert plan.data_status["copernicus"] == "OK" and plan.data_status["mosdac"] == "NOT_AVAILABLE"

    z = plan.target_zone
    i, j = z.source_cell
    assert (z.lat, z.lon) == (pytest.approx(LATS[i]), pytest.approx(LONS[j]))
    assert abs(z.lat - 21.0) <= 0.15 and not IS_LAND[i, j]  # on the front, at sea
    assert plan.route.found and all(not LAND.is_land(w.lat, w.lon) for w in plan.route.waypoints)
    assert "'sst': 'copernicus'" in " ".join(final["trace"])


def test_mosdac_fills_a_field_copernicus_lacks(tmp_path):
    mosdac = make_service(tmp_path).providers["mosdac"].fetch(None)  # has both sst and chl
    service = service_with_copernicus(tmp_path, mosdac=mosdac)
    for f in (tmp_path / "cmems").glob("chl_*.nc"):
        f.unlink()
    final = run(service, origin=VERAVAL)
    trace = " ".join(final["trace"])
    assert "copernicus=PARTIAL" in trace
    assert "'chl': 'mosdac'" in trace and "'sst': 'copernicus'" in trace
