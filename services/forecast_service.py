"""Point forecast for the app's weather and alerts screens.

Hourly conditions at one location from Open-Meteo, grouped into local days (IST by
default), each day classified with the same RiskService voyage rules as the planner
(worst hour of the day per variable). The best day is the earliest day with the
lowest verdict, tie-broken on the lowest peak wave height.

Results are cached in memory per (rounded location, days) for `ttl_seconds`,
because forecasts only update a few times a day.
"""
from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Callable, Dict, List, Optional, Tuple

import numpy as np

from models.schemas import (
    DayOutlook, ForecastHour, ForecastResponse, Location, LocalizedRule, VoyageRisk,
)
from providers.openmeteo import fetch_hourly
from services.localization_service import LANGS, LocalizationService
from services.risk_service import RiskService

_RANK = {VoyageRisk.SAFE: 0, VoyageRisk.CAUTION: 1, VoyageRisk.HIGH_RISK: 2, VoyageRisk.DO_NOT_VENTURE: 3,
         VoyageRisk.INSUFFICIENT_DATA: 4}
IST = timezone(timedelta(hours=5, minutes=30))


def _f(x) -> Optional[float]:
    return None if x is None or not np.isfinite(x) else round(float(x), 2)


class ForecastService:
    def __init__(self, risk: RiskService, localizer: Optional[LocalizationService] = None,
                 fetch: Callable = fetch_hourly, ttl_seconds: float = 1800.0, tz: timezone = IST):
        self.risk, self.loc, self._fetch = risk, localizer or LocalizationService(), fetch
        self.ttl, self.tz = ttl_seconds, tz
        self._cache: Dict[Tuple, Tuple[float, ForecastResponse]] = {}
        self._lock = threading.Lock()

    def forecast(self, lat: float, lon: float, days: int = 5, now: Optional[datetime] = None) -> ForecastResponse:
        key = (round(lat, 2), round(lon, 2), days)
        with self._lock:
            hit = self._cache.get(key)
            if now is None and hit and time.time() - hit[0] <= self.ttl:
                return hit[1]
        resp = self._build(lat, lon, days, now or datetime.now(timezone.utc).replace(tzinfo=None))
        with self._lock:
            self._cache[key] = (time.time(), resp)
        return resp

    def _build(self, lat: float, lon: float, days: int, now: datetime) -> ForecastResponse:
        start = now.replace(minute=0, second=0, microsecond=0)
        # whole local days: from local midnight today to the end of the last day, in UTC
        local0 = start.replace(tzinfo=timezone.utc).astimezone(self.tz).replace(hour=0)
        end = (local0 + timedelta(days=days)).astimezone(timezone.utc).replace(tzinfo=None) - timedelta(hours=1)
        begin = local0.astimezone(timezone.utc).replace(tzinfo=None)
        d = self._fetch([lat], [lon], begin, end)

        hours: List[ForecastHour] = []
        for i, t in enumerate(d["time"]):
            v = {k: d[k][0, i] for k in d if k != "time"}
            hours.append(ForecastHour(
                time=t, wind_speed=_f(v["wind_speed"]), wind_gust=_f(v["wind_gust"]), wind_from_deg=_f(v["wind_from_deg"]),
                wave_height=_f(v["wave_height"]), wave_from_deg=_f(v["wave_from_deg"]), wave_period=_f(v["wave_period"]),
                rain_mm=_f(v["precipitation"]), visibility_km=_f(v["visibility"]),
                current_speed=_f(v["current_speed"]), sst=_f(v["sst"]),
            ))

        by_day: Dict[str, List[ForecastHour]] = {}
        for h in hours:
            day = h.time.replace(tzinfo=timezone.utc).astimezone(self.tz).date().isoformat()
            by_day.setdefault(day, []).append(h)

        outlook = [self._day(day, hs) for day, hs in by_day.items()]
        ranked = [o for o in outlook if o.verdict is not VoyageRisk.INSUFFICIENT_DATA]
        best = min(ranked, key=lambda o: (_RANK[o.verdict], o.max_wave_m if o.max_wave_m is not None else 99, o.date),
                   default=None)
        return ForecastResponse(
            location=Location(lat=lat, lon=lon), generated_at=now, timezone="Asia/Kolkata",
            hours=[h for h in hours if h.time >= start], days=outlook,
            best_day=best.date if best else None, source="open-meteo",
        )

    def _day(self, day: str, hs: List[ForecastHour]) -> DayOutlook:
        def worst(attr, fn=max):
            vals = [getattr(h, attr) for h in hs if getattr(h, attr) is not None]
            return fn(vals) if vals else None

        readings = {"wave_height": worst("wave_height"), "wind_speed": worst("wind_speed"),
                    "visibility": worst("visibility_km", min), "current_speed": worst("current_speed")}
        a = self.risk.assess(readings)
        rain = [h.rain_mm for h in hs if h.rain_mm is not None]
        messages = {lang: [LocalizedRule(rule_id=t.rule_id, variable=t.variable, verdict=t.verdict.value,
                                         message=self.loc.translate(t.message, lang)[0] if lang != "en" else t.message)
                           for t in a.triggered] for lang in LANGS}
        return DayOutlook(
            date=day, verdict=a.verdict, triggered=a.triggered, messages=messages,
            max_wave_m=_f(readings["wave_height"]), max_wind_ms=_f(readings["wind_speed"]),
            max_gust_ms=_f(worst("wind_gust")), rain_mm=_f(sum(rain)) if rain else None,
            min_visibility_km=_f(readings["visibility"]), max_current_ms=_f(readings["current_speed"]),
        )
