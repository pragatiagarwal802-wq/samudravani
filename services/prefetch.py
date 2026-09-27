"""Background refresh of the home ports, so app requests are answered from warm caches.

Runs once at startup and then shortly after every hour boundary (plans use hour-aligned windows,
so a new hour means new cache keys). Each port's plan and forecast are computed exactly as the
app requests them. Failures are logged and retried at the next run; they never stop the server.
Set PREFETCH=0 to disable.
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timezone
from typing import Callable, Iterable, List, Tuple

log = logging.getLogger(__name__)

Port = Tuple[str, float, float]  # name, lat, lon


def warm_once(ports: Iterable[Port], plan: Callable[[float, float, str], object],
              forecast: Callable[[float, float], object]) -> List[str]:
    """Compute every port's forecast and plan; returns the names that failed."""
    failed = []
    for name, lat, lon in ports:
        t0 = time.time()
        try:
            forecast(lat, lon)
            plan(lat, lon, name)
            log.info("prefetch %s: %.0f s", name, time.time() - t0)
        except Exception:
            log.exception("prefetch %s failed", name)
            failed.append(name)
    return failed


def seconds_to_next_run(now: datetime, offset_s: int = 60) -> float:
    """Seconds until `offset_s` past the next hour boundary."""
    into_hour = now.minute * 60 + now.second + now.microsecond / 1e6
    return 3600 - into_hour + offset_s if into_hour >= offset_s else offset_s - into_hour


def start(ports: List[Port], plan, forecast) -> threading.Thread:
    def loop():
        while True:
            warm_once(ports, plan, forecast)
            time.sleep(seconds_to_next_run(datetime.now(timezone.utc)))

    t = threading.Thread(target=loop, name="prefetch", daemon=True)
    t.start()
    return t
