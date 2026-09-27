"""Open-Meteo provider and point-forecast service, offline (fake HTTP / fake fetch)."""
from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np

from models.schemas import BoundingBox, Location, ProviderStatus, RiskQuery, TimeWindow, VoyageRisk
from providers.openmeteo import OpenMeteoProvider
from services.forecast_service import ForecastService
from services.localization_service import LocalizationService
from services.risk_service import RiskService

START = datetime(2026, 9, 27, 0)
HOURS = [START + timedelta(hours=h) for h in range(48)]


class FakeResponse:
    def __init__(self, js):
        self.status_code, self._js, self.text = 200, js, ""

    def json(self):
        return self._js


class FakeSession:
    """Answers both Open-Meteo endpoints for any list of locations; waves grow with latitude."""

    def __init__(self):
        self.calls = 0

    def get(self, url, params, timeout):
        self.calls += 1
        lats = [float(x) for x in params["latitude"].split(",")]
        times = [t.strftime("%Y-%m-%dT%H:%M") for t in HOURS]
        rows = []
        for lat in lats:
            if "marine" in url:
                hourly = {"wave_height": [1.0 + (lat - 20.0)] * 48, "wave_direction": [240] * 48, "wave_period": [7] * 48,
                          "ocean_current_velocity": [1.8] * 48, "sea_surface_temperature": [28.0 + (lat - 20.0)] * 48}
            else:
                hourly = {"wind_speed_10m": [6.0] * 48, "wind_direction_10m": [250] * 48, "wind_gusts_10m": [9.0] * 48,
                          "precipitation": [0.0] * 48, "visibility": [15000] * 48}
            rows.append({"hourly": {"time": times, **hourly}})
        return FakeResponse(rows if len(rows) > 1 else rows[0])


def test_provider_builds_grids_and_hourly_observations(monkeypatch):
    monkeypatch.delenv("OPENMETEO_ENABLED", raising=False)
    session = FakeSession()
    q = RiskQuery(location=Location(lat=20.8, lon=70.25), window=TimeWindow(start=START, end=START + timedelta(hours=23)),
                  bbox=BoundingBox(south=20.0, west=69.5, north=21.5, east=71.0))
    res = OpenMeteoProvider(session=session).fetch(q)
    assert res.status is ProviderStatus.OK, res.message
    assert set(res.grids) == {"wave_height", "wind_speed", "wind_from_deg", "sst"}
    wave = np.array(res.grids["wave_height"].values)
    assert wave.shape == (4, 4) and wave[-1, 0] > wave[0, 0]  # rows follow latitude
    kinds = {o.variable for o in res.observations}
    assert {"wave_height", "wind_speed", "visibility", "current_speed"} <= kinds
    vis = [o.value for o in res.observations if o.variable == "visibility"]
    cur = [o.value for o in res.observations if o.variable == "current_speed"]
    assert vis[0] == 15.0 and abs(cur[0] - 0.5) < 1e-9  # m -> km, km/h -> m/s
    assert len([o for o in res.observations if o.variable == "wind_speed"]) == 24  # window clipped


def test_provider_can_be_disabled(monkeypatch):
    monkeypatch.setenv("OPENMETEO_ENABLED", "0")
    q = RiskQuery(location=Location(lat=20.8, lon=70.25), window=TimeWindow(start=START, end=START + timedelta(hours=6)))
    assert OpenMeteoProvider(session=FakeSession()).fetch(q).status is ProviderStatus.NOT_AVAILABLE


def fake_fetch(waves):
    """fetch_hourly stand-in: per-hour wave heights `waves(t)` at one point."""
    def fetch(lats, lons, start, end):
        ts = [t for t in (start + timedelta(hours=h) for h in range(24 * 8)) if t <= end]
        col = lambda f: np.array([[f(t) for t in ts]])
        return {"time": ts, "wind_speed": col(lambda t: 6.0), "wind_from_deg": col(lambda t: 250.0),
                "wind_gust": col(lambda t: 9.0), "precipitation": col(lambda t: 0.0), "visibility": col(lambda t: 15.0),
                "wave_height": col(waves), "wave_from_deg": col(lambda t: 240.0), "wave_period": col(lambda t: 7.0),
                "current_speed": col(lambda t: 0.4), "sst": col(lambda t: 28.5)}
    return fetch


def test_daily_outlook_flags_rough_day_and_picks_best_day():
    # rough sea (3 m) on the second local day, calmest (0.8 m) on the fourth
    def waves(t):
        day = (t + timedelta(hours=5, minutes=30)).date() - datetime(2026, 9, 27).date()
        return {1: 3.0, 3: 0.8}.get(day.days, 1.2)

    svc = ForecastService(RiskService(), LocalizationService(), fetch=fake_fetch(waves))
    f = svc.forecast(20.8, 70.25, days=5, now=datetime(2026, 9, 27, 3, 0))
    assert [d.date for d in f.days] == ["2026-09-27", "2026-09-28", "2026-09-29", "2026-09-30", "2026-10-01"]
    rough = f.days[1]
    assert rough.verdict is VoyageRisk.CAUTION and rough.max_wave_m == 3.0
    assert rough.triggered[0].rule_id == "wave_caution"
    assert rough.messages["hi"][0].message != rough.messages["en"][0].message  # translated
    assert "3.0" in rough.messages["hi"][0].message  # numbers preserved
    assert f.best_day == "2026-09-30"
    assert f.hours[0].time == datetime(2026, 9, 27, 3, 0)  # past hours of today dropped
