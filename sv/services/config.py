"""Config loading shared by the computational services."""
from __future__ import annotations

import os
from typing import Any, Dict, Optional

import yaml

DEFAULT_CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "risk_config.yaml")


def load_config(path: Optional[str] = None) -> Dict[str, Any]:
    with open(path or DEFAULT_CONFIG_PATH, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)
