"""
rca.py
======
Lightweight Root Cause Analysis (RCA) for "Stock-out Risk" items surfaced by
the Watchdog agent. For each Store_ID x SKU_ID flagged at risk, scores four
candidate causes and returns the single strongest one (Core Rule: exactly
one primary root cause per item):

  Forecast Accuracy   — forecast error (MAE) relative to the SKU's typical
                        weekly demand. Real data: Outputs/Forecast_Validation.csv.
  Safety Stock        — inventory buffer thin vs. a formula-based safety
                        stock target. Real+derived data: see
                        Backend/pipelines/inventory_planning/safety_stock_supplier.py.
  Heavy Sales         — recent actual demand spiked above the SKU's own
                        trailing baseline. Real data: weekly_demand_output.csv.
  Supplier Fill Rate  — the SKU's supplier has a below-average 3-month
                        trailing fill rate. Derived data: see
                        safety_stock_supplier.py (Supplier_Fill_Rate_Pct_3M).

Each raw signal is percentile-ranked (0-1, higher = stronger case) across
the *current pool* of Stock-out Risk items, so the flagged cause always
reflects "worse than peers among today's at-risk SKUs" rather than an
arbitrary absolute cutoff — consistent with the adaptive-percentile approach
already used in delisting_recommendations' band classification.
"""
from __future__ import annotations

import os
import sys
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)
from database.connection import read_table_or_csv

_PROJ = Path(_BACKEND_DIR).parent
_OUT  = _PROJ / "Outputs"

RECENT_WEEKS = 4  # "recent" window used to detect a Heavy Sales spike

# Priority order used only to break exact ties between signal scores.
_CAUSE_PRIORITY = ["Forecast Accuracy", "Safety Stock", "Heavy Sales", "Supplier Fill Rate"]


# ---------------------------------------------------------------------------
# Loaders (cached — refreshed on process restart, mirrors decision_hub_service)
# ---------------------------------------------------------------------------
@lru_cache(maxsize=1)
def _safety_supplier() -> pd.DataFrame:
    df = read_table_or_csv(
        "safety_stock_supplier_scores", _OUT / "safety_stock_supplier_scores.csv"
    )
    for c in ["Weekly_Demand_Mean", "Safety_Stock_Units", "Safety_Stock_Gap_Units",
              "Supplier_Fill_Rate_Pct_3M"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


@lru_cache(maxsize=1)
def _forecast_validation() -> pd.DataFrame:
    df = read_table_or_csv("forecast_validation", _OUT / "Forecast_Validation.csv")
    if "LightGBM_MAE" in df.columns:
        df["LightGBM_MAE"] = pd.to_numeric(df["LightGBM_MAE"], errors="coerce")
    return df


@lru_cache(maxsize=1)
def _weekly_demand() -> pd.DataFrame:
    df = read_table_or_csv("weekly_demand_output", _OUT / "weekly_demand_output.csv")
    df["Quantity_Sold"] = pd.to_numeric(df["Quantity_Sold"], errors="coerce").fillna(0)
    return df


def _heavy_sales_signal() -> pd.DataFrame:
    """Sales_Spike_Pct = recent-window avg vs. the SKU's own prior-window avg."""
    dm = _weekly_demand()
    weeks  = sorted(dm["Year_WK"].unique())
    recent = weeks[-RECENT_WEEKS:]
    prior  = weeks[:-RECENT_WEEKS] if len(weeks) > RECENT_WEEKS else weeks

    recent_avg = (dm[dm["Year_WK"].isin(recent)]
                  .groupby(["Store_ID", "SKU_ID"])["Quantity_Sold"].mean()
                  .rename("recent_avg"))
    prior_avg  = (dm[dm["Year_WK"].isin(prior)]
                  .groupby(["Store_ID", "SKU_ID"])["Quantity_Sold"].mean()
                  .rename("prior_avg"))

    out = pd.concat([recent_avg, prior_avg], axis=1).reset_index()
    out["prior_avg"] = out["prior_avg"].replace(0, np.nan)
    out["Sales_Spike_Pct"] = (
        (out["recent_avg"] - out["prior_avg"]) / out["prior_avg"] * 100
    ).fillna(0)
    return out[["Store_ID", "SKU_ID", "Sales_Spike_Pct"]]


# ---------------------------------------------------------------------------
# Detail narrative per cause
# ---------------------------------------------------------------------------
def _detail(row: pd.Series, network_fill_rate: float) -> str:
    cause = row["root_cause"]
    if cause == "Forecast Accuracy":
        mae = row.get("LightGBM_MAE") or 0
        pct = row.get("_fc_error_ratio", 0) * 100
        return (f"Forecast error (MAE {mae:,.0f} units/wk) is {pct:.0f}% of typical weekly "
                 f"demand — among the least accurate forecasts of today's at-risk SKUs.")
    if cause == "Safety Stock":
        gap = row.get("Safety_Stock_Gap_Units") or 0
        ss  = row.get("Safety_Stock_Units") or 0
        return (f"Inventory buffer is {abs(gap):,.0f} units below the {ss:,.0f}-unit "
                 f"safety-stock target needed to absorb this SKU's demand volatility.")
    if cause == "Heavy Sales":
        spike = row.get("Sales_Spike_Pct") or 0
        return (f"Actual sales over the last {RECENT_WEEKS} weeks are running "
                 f"{spike:+.0f}% vs. this SKU's own baseline — demand outpaced the plan.")
    if cause == "Supplier Fill Rate":
        fr  = row.get("Supplier_Fill_Rate_Pct_3M")
        sup = row.get("Supplier") or "Supplier"
        fr_s = f"{fr:.0%}" if pd.notna(fr) else "n/a"
        return (f"{sup}'s 3-month trailing fill rate is {fr_s}, below the "
                 f"{network_fill_rate:.0%} network average — replenishment has lagged.")
    return "Insufficient signal to isolate a single dominant cause."


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------
def compute_root_causes(candidates: pd.DataFrame) -> dict[tuple, dict]:
    """
    candidates: DataFrame with at least Store_ID, SKU_ID for the current
    pool of Stock-out Risk items.

    Returns {(store_id, sku_id): {"root_cause": str, "root_cause_detail": str,
                                   "scores": {cause: 0-1, ...}}}
    """
    if candidates.empty:
        return {}

    df = candidates[["Store_ID", "SKU_ID"]].drop_duplicates().copy()

    ss = _safety_supplier()[[
        "Store_ID", "SKU_ID", "Weekly_Demand_Mean", "Safety_Stock_Units",
        "Safety_Stock_Gap_Units", "Supplier", "Supplier_Fill_Rate_Pct_3M",
    ]]
    df = df.merge(ss, on=["Store_ID", "SKU_ID"], how="left")

    fv = _forecast_validation()
    fv_cols = ["Store_ID", "SKU_ID", "LightGBM_MAE"] if {"Store_ID", "SKU_ID", "LightGBM_MAE"}.issubset(fv.columns) else None
    df = df.merge(fv[fv_cols], on=["Store_ID", "SKU_ID"], how="left") if fv_cols else df.assign(LightGBM_MAE=np.nan)

    df = df.merge(_heavy_sales_signal(), on=["Store_ID", "SKU_ID"], how="left")

    # --- Raw badness values (higher = stronger case for that root cause) ---
    demand_base = df["Weekly_Demand_Mean"].replace(0, np.nan)
    df["_fc_error_ratio"] = (df["LightGBM_MAE"] / demand_base).fillna(0)
    df["_ss_gap_ratio"]   = (-df["Safety_Stock_Gap_Units"] / df["Safety_Stock_Units"].replace(0, np.nan)) \
                              .fillna(0).clip(lower=0)
    df["_sales_spike"]    = df["Sales_Spike_Pct"].clip(lower=0).fillna(0)
    df["_fill_rate_gap"]  = (1 - df["Supplier_Fill_Rate_Pct_3M"]).fillna(0)

    n = len(df)
    score_map = {
        "Forecast Accuracy":  ("_fc_error_ratio",  "score_forecast_accuracy"),
        "Safety Stock":       ("_ss_gap_ratio",    "score_safety_stock"),
        "Heavy Sales":        ("_sales_spike",      "score_heavy_sales"),
        "Supplier Fill Rate": ("_fill_rate_gap",    "score_supplier_fill_rate"),
    }
    for raw, score in score_map.values():
        df[score] = df[raw].rank(pct=True, method="average") if n > 1 else 0.5
        df[score] = df[score].fillna(0.5)

    def _pick(row) -> str:
        best_cause, best_score = _CAUSE_PRIORITY[0], -1.0
        for cause in _CAUSE_PRIORITY:
            s = row[score_map[cause][1]]
            if s > best_score:
                best_cause, best_score = cause, s
        return best_cause

    df["root_cause"] = df.apply(_pick, axis=1)

    network_fill_rate = float(_safety_supplier()["Supplier_Fill_Rate_Pct_3M"].mean() or 0)
    df["root_cause_detail"] = df.apply(lambda r: _detail(r, network_fill_rate), axis=1)

    result = {}
    for _, r in df.iterrows():
        key = (r["Store_ID"], r["SKU_ID"])
        result[key] = {
            "root_cause":        r["root_cause"],
            "root_cause_detail": r["root_cause_detail"],
            "scores": {
                cause: round(float(r[score_map[cause][1]]), 3) for cause in _CAUSE_PRIORITY
            },
        }
    return result
