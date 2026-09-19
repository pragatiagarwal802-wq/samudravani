"""Deterministic voyage-risk classification from config/risk_config.yaml `voyage_rules`.

verdict = worst triggered rule (CAUTION < HIGH_RISK < DO_NOT_VENTURE), SAFE if
none triggered. Missing sensors never count as safe: if nothing triggered and
fewer than missing_data.min_variables_required distinct variables were
evaluated, the verdict is INSUFFICIENT_DATA. A triggered hazard is always
reported, even when data is otherwise thin.
"""
from __future__ import annotations

import operator
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Mapping, Optional

from models.schemas import ProviderResult, TriggeredRule, VoyageRisk, VoyageRiskAssessment
from services.config import load_config

_OPS = {">=": operator.ge, ">": operator.gt, "<=": operator.le, "<": operator.lt}
_RANK = {VoyageRisk.SAFE: 0, VoyageRisk.CAUTION: 1, VoyageRisk.HIGH_RISK: 2, VoyageRisk.DO_NOT_VENTURE: 3}


class RiskService:
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        cfg = config or load_config()
        self.rules: List[dict] = cfg["voyage_rules"]
        self.min_vars: int = cfg.get("missing_data", {}).get("min_variables_required", 1)
        for r in self.rules:
            if r["op"] not in _OPS:
                raise ValueError(f"rule {r['id']}: unsupported operator {r['op']!r}")
            if VoyageRisk(r["verdict"]) not in _RANK or r["verdict"] == "SAFE":
                raise ValueError(f"rule {r['id']}: verdict must be CAUTION, HIGH_RISK or DO_NOT_VENTURE")

    def worst_case_readings(self, results: Iterable[ProviderResult]) -> Dict[str, float]:
        """Collapse provider observations to one value per variable: the worst case
        (min for variables whose rules trigger on low values, else max)."""
        low_is_bad = {r["variable"] for r in self.rules if r["op"] in ("<", "<=")}
        vals: Dict[str, List[float]] = defaultdict(list)
        for res in results:
            for o in res.observations:
                if o.value is not None:
                    vals[o.variable].append(o.value)
        return {k: (min(v) if k in low_is_bad else max(v)) for k, v in vals.items()}

    def assess(self, readings: Mapping[str, Optional[float]]) -> VoyageRiskAssessment:
        wanted = sorted({r["variable"] for r in self.rules})
        evaluated = sorted(v for v in wanted if readings.get(v) is not None)
        missing = [v for v in wanted if v not in evaluated]

        triggered: List[TriggeredRule] = []
        for r in self.rules:
            val = readings.get(r["variable"])
            if val is not None and _OPS[r["op"]](val, r["threshold"]):
                triggered.append(TriggeredRule(
                    rule_id=r["id"], variable=r["variable"], value=float(val), op=r["op"],
                    threshold=float(r["threshold"]), verdict=VoyageRisk(r["verdict"]),
                    message=r["message"].format(value=val, threshold=r["threshold"]),
                ))

        if triggered:
            verdict = max((t.verdict for t in triggered), key=_RANK.__getitem__)
            top = [t for t in triggered if t.verdict == verdict]
            explanation = f"{verdict.value}: " + " ".join(t.message for t in top)
        elif len(evaluated) < self.min_vars:
            verdict = VoyageRisk.INSUFFICIENT_DATA
            explanation = (f"INSUFFICIENT_DATA: only {len(evaluated)} of the required {self.min_vars} "
                           f"variables available (missing: {', '.join(missing)}).")
        else:
            verdict = VoyageRisk.SAFE
            explanation = "SAFE: no rule triggered for " + ", ".join(evaluated) + "."
            if missing:
                explanation += f" Not evaluated (no data): {', '.join(missing)}."
        return VoyageRiskAssessment(verdict=verdict, triggered=triggered, evaluated_variables=evaluated,
                                    missing_variables=missing, explanation=explanation)
