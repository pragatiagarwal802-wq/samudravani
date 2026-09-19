"""Helpers shared by providers."""
from __future__ import annotations

import os
import tempfile
import zipfile
from datetime import datetime, timezone
from typing import Iterator, List, Optional

import numpy as np

from models.schemas import BoundingBox


def to_utc_naive(dt: datetime) -> datetime:
    """Normalise to naive UTC so comparisons/serialisation are consistent."""
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def to_datetime(value) -> Optional[datetime]:
    """numpy datetime64 -> naive-UTC datetime (None for NaT)."""
    ts = np.datetime64(value, "s")
    if np.isnat(ts):
        return None
    return datetime.utcfromtimestamp(int(ts.astype("int64")))


def wrap_lon(lon):
    """Wrap longitudes to [-180, 180)."""
    return (np.asarray(lon) + 180.0) % 360.0 - 180.0


def in_bbox(lat, lon, bbox: BoundingBox):
    lon = wrap_lon(lon)
    return (lat >= bbox.south) & (lat <= bbox.north) & (lon >= bbox.west) & (lon <= bbox.east)


def pick_var(ds, candidates: List[str]) -> Optional[str]:
    """First candidate present in ds (case-insensitive)."""
    names = {str(n).lower(): n for n in list(ds.data_vars) + list(ds.coords)}
    for c in candidates:
        if c.lower() in names:
            return names[c.lower()]
    return None


def expand_netcdf(path: str) -> Iterator[str]:
    """Yield data file paths; unpack a zip (CDS may return one) into a temp dir."""
    if zipfile.is_zipfile(path):
        out = tempfile.mkdtemp(prefix="samudravani_")
        with zipfile.ZipFile(path) as zf:
            zf.extractall(out)
        for name in sorted(os.listdir(out)):
            yield os.path.join(out, name)
    else:
        yield path
