"""
agent_core.py
=============
Shared helpers used by all three agents.
Pure functions — no I/O, no side effects.
"""
from __future__ import annotations
import numpy as np
import pandas as pd
from typing import Any


# ---------------------------------------------------------------------------
# Priority scoring
# ---------------------------------------------------------------------------

_SEVERITY_WEIGHT = {"red": 3, "orange": 2, "green": 1}


def priority_score(severity: str, financial_impact: float, max_financial: float, conflict: bool) -> float:
    """
    Returns a 0–100 priority score.
    conflict_bonus adds one full severity tier when signals collide on the same SKU.
    """
    sw       = _SEVERITY_WEIGHT.get(severity, 1)
    fin_norm = financial_impact / (max_financial or 1)
    bonus    = 1.0 if conflict else 0.0
    raw      = (sw + bonus) * fin_norm
    return round(min(raw / 4.0 * 100, 100), 1)


# ---------------------------------------------------------------------------
# Dedupe / merge by key
# ---------------------------------------------------------------------------

def dedupe_by_key(items: list[dict], key_fields: tuple[str, ...]) -> list[dict]:
    """
    Merge duplicate items that share the same composite key.
    Later items' signal_types are unioned into the first occurrence.
    """
    index: dict[tuple, dict] = {}
    for item in items:
        key = tuple(item.get(f) for f in key_fields)
        if key not in index:
            index[key] = dict(item)
            if "signal_types" in item and not isinstance(item["signal_types"], list):
                index[key]["signal_types"] = [item["signal_types"]]
        else:
            existing = index[key]
            new_signals = item.get("signal_types", [])
            if isinstance(new_signals, str):
                new_signals = [new_signals]
            for s in new_signals:
                if s not in existing.get("signal_types", []):
                    existing.setdefault("signal_types", []).append(s)
            existing["financial_impact_usd"] = max(
                existing.get("financial_impact_usd", 0),
                item.get("financial_impact_usd", 0),
            )
    return list(index.values())


# ---------------------------------------------------------------------------
# Trim helper (mirrors decision_hub_service._trim)
# ---------------------------------------------------------------------------

def trim(rows: list[dict], keys: list[str]) -> list[dict]:
    return [{k: r.get(k) for k in keys} for r in rows]


# ---------------------------------------------------------------------------
# Divergence math
# ---------------------------------------------------------------------------

def divergence_magnitude(cluster_score: float, global_score: float) -> float:
    return round(abs(cluster_score - global_score), 4)


# ---------------------------------------------------------------------------
# Percentile normalization
# ---------------------------------------------------------------------------

def pct_normalize(series: pd.Series) -> pd.Series:
    lo, hi = series.min(), series.max()
    if hi == lo:
        return pd.Series([0.5] * len(series), index=series.index)
    return (series - lo) / (hi - lo)


# ---------------------------------------------------------------------------
# Score band → decision label
# ---------------------------------------------------------------------------

def score_to_decision(delist_score: float) -> str:
    if delist_score >= 0.6:
        return "Delist"
    if delist_score >= 0.4:
        return "Watch"
    return "Continue"
