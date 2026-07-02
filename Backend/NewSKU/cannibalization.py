"""
cannibalization.py
Estimates demand cannibalization when a new SKU is introduced.

Algorithm
---------
1. Find competing existing SKUs (same sub-category, high similarity)
2. Per competing SKU, estimate a cannibalization coefficient:
      cannib_coef = 0.50 × similarity
                  + 0.25 × price_proximity
                  + 0.25 × basket_substitution
3. Convert coefficient to demand transfer rate (normalised, capped at 0.90)
4. Estimate cannibalized units, incremental units, and net category effect
5. Rank impacted SKUs by transfer volume

Inputs (files)
--------------
  Outputs/new_sku_similarity_scores.csv
  Outputs/sku_basket_insights.csv
  Outputs/demand_transfer_matrix.csv
  Raw_Input/SKU_Master.csv
"""

from __future__ import annotations
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from ..db import read_table_or_csv

_ROOT = Path(__file__).resolve().parent.parent.parent
_OUT  = _ROOT / "Outputs"
_RAW  = _ROOT / "Raw_Input"

_cache: dict[str, pd.DataFrame] = {}

def _load(key: str, path: Path) -> pd.DataFrame:
    if key not in _cache:
        _cache[key] = read_table_or_csv(path.stem.lower(), path)
    return _cache[key]

def _sim()      -> pd.DataFrame: return _load("sim",   _OUT / "new_sku_similarity_scores.csv")
def _basket()   -> pd.DataFrame: return _load("bsk",   _OUT / "sku_basket_insights.csv")
def _transfer() -> pd.DataFrame: return _load("dtm",   _OUT / "demand_transfer_matrix.csv")
def _sku_master() -> pd.DataFrame: return _load("sm",  _RAW / "SKU_Master.csv")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _price_proximity(price_new: float, price_existing: float, max_range: float = 20.0) -> float:
    """1.0 = same price, 0.0 = very different price."""
    if price_new <= 0 or price_existing <= 0:
        return 0.5
    diff = abs(price_new - price_existing)
    return float(np.clip(1 - diff / max_range, 0, 1))


def _basket_substitution_score(sku_id: str) -> float:
    """Pull substitution_score from sku_basket_insights for an existing SKU."""
    bsk = _basket()
    if bsk.empty or "substitution_score" not in bsk.columns:
        return 0.5
    col_id = "SKU_ID" if "SKU_ID" in bsk.columns else bsk.columns[0]
    row = bsk[bsk[col_id] == sku_id]
    if row.empty:
        return 0.5
    return float(row["substitution_score"].iloc[0])


def _transfer_matrix_rate(new_sku_id: str, existing_sku_id: str) -> float:
    """
    If demand_transfer_matrix has a record for (existing → new_sku_id),
    return transfer_confidence. Otherwise 0.
    The matrix captures historical substitution behaviour.
    """
    dtm = _transfer()
    if dtm.empty:
        return 0.0
    # Check both directions: new replacing existing
    col_from = "from_sku" if "from_sku" in dtm.columns else dtm.columns[0]
    col_to   = "to_sku"   if "to_sku"   in dtm.columns else dtm.columns[1]
    row = dtm[(dtm[col_from] == existing_sku_id)]
    if row.empty:
        return 0.0
    return float(row["transfer_confidence"].iloc[0]) if "transfer_confidence" in row else 0.0


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def estimate_cannibalization(
    new_sku_id: str,
    new_sku_attrs: dict,
    forecast_units_total: float,   # total units forecast for new SKU across all stores/weeks
    top_n: int = 10,
) -> dict[str, Any]:
    """
    Returns:
      cannibalization_rate     : float  0–1  (fraction of new demand that is stolen)
      incrementality_rate      : float  0–1  (fraction that is genuinely new to category)
      cannibalized_units       : float
      incremental_units        : float
      impacted_skus            : list of dicts ranked by transfer_volume
      cannibalization_score    : float  0–1  composite risk score
      category_net_effect      : str   "Positive" / "Neutral" / "Negative"
      risk_level               : str   "High" / "Medium" / "Low"
      summary_nl               : str   business-language narrative
    """
    sim = _sim()
    sm  = _sku_master()

    if sim.empty:
        return {"error": "Similarity scores not found. Run similarity.py first."}

    col_new = "New_SKU_ID" if "New_SKU_ID" in sim.columns else sim.columns[0]
    col_ex  = "Existing_SKU_ID" if "Existing_SKU_ID" in sim.columns else sim.columns[1]

    rows = sim[sim[col_new] == new_sku_id].copy()
    if rows.empty:
        return {"error": f"No similarity records for new_sku_id='{new_sku_id}'"}

    # Filter to same sub-category — highest competition zone
    new_sub_cat = new_sku_attrs.get("Sub_Category", "")
    if new_sub_cat and "Existing_Sub_Category" in rows.columns:
        same_cat = rows[rows["Existing_Sub_Category"] == new_sub_cat]
        if same_cat.empty:
            same_cat = rows  # fallback to all
    else:
        same_cat = rows

    # Use top-N most similar
    if "Final_Similarity_Score" in same_cat.columns:
        same_cat = same_cat.nlargest(top_n, "Final_Similarity_Score")
    else:
        same_cat = same_cat.head(top_n)

    # Price range for normalization
    new_price = float(new_sku_attrs.get("List_Price_USD", 0) or 0)
    if not sm.empty and "List_Price_USD" in sm.columns:
        price_range = float(sm["List_Price_USD"].max() - sm["List_Price_USD"].min())
        price_range = max(price_range, 5.0)
    else:
        price_range = 20.0

    impacted = []
    total_cannib_coef = 0.0

    for _, row in same_cat.iterrows():
        sku_id = str(row.get(col_ex, ""))
        sim_score = float(row.get("Final_Similarity_Score", 0))

        # Existing SKU price
        ex_price = 0.0
        if not sm.empty and "List_Price_USD" in sm.columns:
            sm_row = sm[sm.get("SKU_ID", sm.columns[0] if not sm.empty else pd.Series([])) == sku_id]
            if not sm_row.empty:
                ex_price = float(sm_row["List_Price_USD"].iloc[0] or 0)

        # Three drivers of cannibalization
        price_prox = _price_proximity(new_price, ex_price, price_range)
        basket_sub = _basket_substitution_score(sku_id)
        hist_transfer = _transfer_matrix_rate(new_sku_id, sku_id)

        # Cannibalization coefficient: blend drivers
        if hist_transfer > 0:
            cannib_coef = 0.40 * sim_score + 0.20 * price_prox + 0.20 * basket_sub + 0.20 * hist_transfer
        else:
            cannib_coef = 0.50 * sim_score + 0.25 * price_prox + 0.25 * basket_sub

        cannib_coef = float(np.clip(cannib_coef, 0, 1))
        total_cannib_coef += cannib_coef

        # Transfer volume estimate
        transfer_units = forecast_units_total * cannib_coef * (sim_score ** 0.5)

        impacted.append({
            "sku_id":             sku_id,
            "product_name":       str(row.get("Existing_Product_Name", sku_id)),
            "brand":              str(row.get("Existing_Brand", "")),
            "sub_category":       str(row.get("Existing_Sub_Category", "")),
            "similarity_score":   round(sim_score, 4),
            "price_proximity":    round(price_prox, 4),
            "basket_substitution":round(basket_sub, 4),
            "historical_transfer":round(hist_transfer, 4),
            "cannibalization_coef": round(cannib_coef, 4),
            "estimated_transfer_units": round(transfer_units, 1),
            "hierarchy_similarity":  float(row.get("Hierarchy_Similarity",  0)),
            "functional_similarity": float(row.get("Functional_Similarity", 0)),
        })

    # Sort by transfer volume
    impacted.sort(key=lambda x: x["estimated_transfer_units"], reverse=True)

    # Aggregate cannibalization rate (normalise — total can't exceed 90%)
    raw_rate = min(sum(x["cannibalization_coef"] for x in impacted) / max(len(impacted), 1), 0.90)
    cannib_rate = round(float(raw_rate), 4)
    increm_rate = round(1 - cannib_rate, 4)

    cannib_units = round(forecast_units_total * cannib_rate, 1)
    increm_units = round(forecast_units_total * increm_rate, 1)

    # Composite cannibalization risk score (0–1)
    max_sim = float(same_cat["Final_Similarity_Score"].max()) if "Final_Similarity_Score" in same_cat.columns else 0.5
    n_same_cat = len(same_cat)
    cannib_score = round(
        0.40 * cannib_rate +
        0.30 * max_sim +
        0.30 * min(n_same_cat / 10, 1.0),
        4
    )

    # Risk level
    if cannib_score >= 0.65:
        risk_level = "High"
    elif cannib_score >= 0.35:
        risk_level = "Medium"
    else:
        risk_level = "Low"

    # Net category effect
    if increm_rate >= 0.50:
        cat_effect = "Positive"
    elif increm_rate >= 0.25:
        cat_effect = "Neutral"
    else:
        cat_effect = "Negative"

    # NL Summary
    top_sku = impacted[0]["product_name"] if impacted else "existing SKUs"
    summary_nl = (
        f"{risk_level} cannibalization risk. "
        f"Of the {round(forecast_units_total)} projected units, "
        f"~{round(cannib_rate*100)}% ({round(cannib_units)} units) are expected to cannibalize "
        f"existing category demand — primarily from {top_sku}. "
        f"~{round(increm_rate*100)}% ({round(increm_units)} units) represent genuinely incremental category growth. "
        f"Net category impact: {cat_effect}."
    )

    return {
        "cannibalization_rate":   cannib_rate,
        "incrementality_rate":    increm_rate,
        "cannibalized_units":     cannib_units,
        "incremental_units":      increm_units,
        "forecast_units_total":   round(forecast_units_total, 1),
        "cannibalization_score":  cannib_score,
        "risk_level":             risk_level,
        "category_net_effect":    cat_effect,
        "impacted_skus":          impacted,
        "n_competing_skus":       len(impacted),
        "summary_nl":             summary_nl,
    }
