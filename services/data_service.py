"""Central data access with a shared SQLite cache.

Agents call DataService.get()/get_all() instead of providers directly. The
query bbox is snapped outward to a fixed grid of tiles and the window to whole
hours, so nearby requests resolve to the same cache key and are fetched once.
Concurrent identical requests are serialised by a per-key lock.
Only OK/PARTIAL results are cached; NOT_AVAILABLE and ERROR are always retried.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import sqlite3
import threading
import time
from datetime import timedelta
from typing import Dict, Iterable, List, Optional

from models.schemas import BoundingBox, ProviderResult, ProviderStatus, RiskQuery, TimeWindow
from providers.base import DataProvider

_SCHEMA = """
CREATE TABLE IF NOT EXISTS cache (
    key TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    created_at REAL NOT NULL,
    payload TEXT NOT NULL
)
"""


class DataService:
    def __init__(self, providers: Iterable[DataProvider], db_path: str = "cache/samudravani.sqlite",
                 ttl_seconds: float = 3600.0, tile_deg: float = 0.25):
        self.providers: Dict[str, DataProvider] = {p.name: p for p in providers}
        self.db_path = db_path
        self.ttl = ttl_seconds
        self.tile_deg = tile_deg
        self._locks: Dict[str, threading.Lock] = {}
        self._guard = threading.Lock()
        os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
        with self._db() as db:
            db.execute(_SCHEMA)

    # -- cache plumbing ------------------------------------------------------
    def _db(self) -> sqlite3.Connection:
        # a connection per call keeps this safe across threads
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _lock_for(self, key: str) -> threading.Lock:
        with self._guard:
            return self._locks.setdefault(key, threading.Lock())

    def _snap(self, query: RiskQuery) -> RiskQuery:
        t = self.tile_deg
        b = query.region()
        box = BoundingBox(
            south=max(-90.0, math.floor(b.south / t) * t),
            north=min(90.0, math.ceil(b.north / t) * t),
            west=max(-180.0, math.floor(b.west / t) * t),
            east=min(180.0, math.ceil(b.east / t) * t),
        )
        s, e = query.window.start, query.window.end
        s = s.replace(minute=0, second=0, microsecond=0)
        e_floor = e.replace(minute=0, second=0, microsecond=0)
        e = e_floor if e_floor == e else e_floor + timedelta(hours=1)
        return query.model_copy(update={"bbox": box, "window": TimeWindow(start=s, end=e)})

    @staticmethod
    def _key(provider: str, q: RiskQuery) -> str:
        b, w = q.bbox, q.window
        raw = json.dumps([provider, b.south, b.west, b.north, b.east, w.start.isoformat(), w.end.isoformat()])
        return hashlib.sha256(raw.encode()).hexdigest()

    def _read(self, key: str) -> Optional[ProviderResult]:
        with self._db() as db:
            row = db.execute("SELECT created_at, payload FROM cache WHERE key=?", (key,)).fetchone()
        if row and time.time() - row[0] <= self.ttl:
            return ProviderResult.model_validate_json(row[1])
        return None

    def _write(self, key: str, result: ProviderResult) -> None:
        with self._db() as db:
            db.execute(
                "INSERT OR REPLACE INTO cache (key, provider, created_at, payload) VALUES (?,?,?,?)",
                (key, result.provider, time.time(), result.model_dump_json()),
            )

    # -- public API ----------------------------------------------------------
    def get(self, provider_name: str, query: RiskQuery, refresh: bool = False) -> ProviderResult:
        provider = self.providers.get(provider_name)
        if provider is None:
            return ProviderResult(provider=provider_name, status=ProviderStatus.NOT_AVAILABLE,
                                  message=f"Provider '{provider_name}' is not registered.")
        snapped = self._snap(query)
        key = self._key(provider_name, snapped)
        with self._lock_for(key):
            if not refresh:
                hit = self._read(key)
                if hit is not None:
                    return hit
            try:
                result = provider.fetch(snapped)
            except Exception as exc:
                result = ProviderResult(provider=provider_name, status=ProviderStatus.ERROR, message=str(exc))
            if result.status in (ProviderStatus.OK, ProviderStatus.PARTIAL):
                self._write(key, result)
            return result

    def get_all(self, query: RiskQuery, names: Optional[List[str]] = None) -> List[ProviderResult]:
        return [self.get(n, query) for n in (names or list(self.providers))]

    def purge_expired(self) -> int:
        with self._db() as db:
            return db.execute("DELETE FROM cache WHERE created_at < ?", (time.time() - self.ttl,)).rowcount


def build_default_service(**kwargs) -> DataService:
    """DataService wired with every provider; missing credentials surface as NOT_AVAILABLE."""
    from providers.ascat import AscatProvider
    from providers.era5 import Era5Provider
    from providers.era6 import Era6Provider
    from providers.mosdac import MosdacProvider

    return DataService([Era5Provider(), AscatProvider(), MosdacProvider(), Era6Provider()], **kwargs)
