"""
sku_intelligence.py
Orchestrator — single entry-point for all New SKU Intelligence capabilities.

Calls all sub-engines and assembles a unified intelligence payload:
  1. Similarity (existing similarity.py output)
  2. Hierarchical Forecast
  3. Cannibalization Analysis
  4. Store Recommendation
  5. Scenario Simulation (base + price −5%, price +5%, promo)
  6. Explainability (similarity, differences, forecast, risk, attribute contributions)
  7. Whitespace Detection
  8. AI Merchant Copilot Summary

Usage:
  from Backend.NewSKU.sku_intelligence import run_new_sku_intelligence
  result = run_new_sku_intelligence(new_sku_id="SKU999", new_sku_attrs={...})
"""

from __future__ import annotations
import traceback
from pathlib import Path
from typing import Any

import pandas as pd

from ..database.connection import read_table_or_csv
from .hierarchical_forecast import build_hierarchical_forecast
from .cannibalization         import estimate_cannibalization
from .store_recommender       import recommend_stores
from .scenario_simulator      import run_scenario, compare_scenarios
from .explainer               import (
    explain_similarity, explain_differences, explain_forecast,
    explain_risks, attribute_contributions
)
from .whitespace_detector     import detect_whitespace
from .copilot                 import generate_copilot_summary

_ROOT = Path(__file__).resolve().parent.parent.parent
_OUT  = _ROOT / "Outputs"
_RAW  = _ROOT / "Raw_Input"


# ---------------------------------------------------------------------------
# Data helpers
# ---------------------------------------------------------------------------
_cache: dict[str, pd.DataFrame] = {}

def _load(key: str, path: Path) -> pd.DataFrame:
    if key not in _cache:
        _cache[key] = read_table_or_csv(path.stem.lower(), path)
    return _cache[key]

def _sim_scores()  -> pd.DataFrame: return _load("sim",  _OUT / "new_sku_similarity_scores.csv")
def _sku_master()  -> pd.DataFrame: return _load("sm",   _RAW / "SKU_Master.csv")


def _get_new_sku_attrs(new_sku_id: str, provided_attrs: dict) -> dict:
    """Merge provided attrs with SKU_Master row (or upload cache) if available."""
    attrs = dict(provided_attrs)

    # Check upload cache first (uploaded SKUs may not be in SKU_Master)
    try:
        from .csv_upload_processor import get_cached_attrs
        cached_attrs = get_cached_attrs(new_sku_id)
        if cached_attrs:
            for k, v in cached_attrs.items():
                if k not in attrs or not attrs[k]:
                    attrs[k] = v
    except ImportError:
        pass

    sm = _sku_master()
    if not sm.empty:
        col = "SKU_ID" if "SKU_ID" in sm.columns else sm.columns[0]
        row = sm[sm[col] == new_sku_id]
        if not row.empty:
            master_attrs = row.iloc[0].to_dict()
            for k, v in master_attrs.items():
                if k not in attrs or not attrs[k]:
                    attrs[k] = v
    attrs["New_SKU_ID"] = new_sku_id
    return attrs


def _load_similarity_rows(new_sku_id: str, top_n: int = 5) -> list[dict]:
    # Check in-memory upload cache first
    try:
        from .csv_upload_processor import get_cached_sim_scores
        cached = get_cached_sim_scores(new_sku_id)
        if cached is not None and not cached.empty:
            col_new = "New_SKU_ID" if "New_SKU_ID" in cached.columns else cached.columns[0]
            rows = cached[cached[col_new] == new_sku_id]
            if "Final_Similarity_Score" in rows.columns:
                rows = rows.nlargest(top_n, "Final_Similarity_Score")
            else:
                rows = rows.head(top_n)
            return rows.to_dict(orient="records")
    except ImportError:
        pass

    sim = _sim_scores()
    if sim.empty:
        return []
    col_new = "New_SKU_ID" if "New_SKU_ID" in sim.columns else sim.columns[0]
    rows = sim[sim[col_new] == new_sku_id]
    if "Final_Similarity_Score" in rows.columns:
        rows = rows.nlargest(top_n, "Final_Similarity_Score")
    else:
        rows = rows.head(top_n)
    return rows.to_dict(orient="records")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def run_new_sku_intelligence(
    new_sku_id:    str,
    new_sku_attrs: dict | None = None,
    top_n_analogs: int = 5,
    top_n_stores:  int = 10,
) -> dict[str, Any]:
    """
    Full intelligence run for a new SKU.

    Parameters
    ----------
    new_sku_id    : ID of the new SKU (must exist in new_sku_similarity_scores.csv)
    new_sku_attrs : Optional dict of SKU attributes (fills gaps not in SKU_Master)
    top_n_analogs : Number of top analog SKUs to use
    top_n_stores  : Number of top stores to highlight

    Returns
    -------
    dict with keys:
      new_sku_id, new_sku_attrs,
      similarity, hierarchical_forecast, cannibalization,
      store_recommendation, scenarios,
      explainability, whitespace, copilot,
      status, errors
    """
    attrs = _get_new_sku_attrs(new_sku_id, new_sku_attrs or {})
    sim_rows = _load_similarity_rows(new_sku_id, top_n_analogs)

    errors = []
    result: dict[str, Any] = {
        "new_sku_id":   new_sku_id,
        "new_sku_attrs": {k: str(v) for k, v in attrs.items() if pd.notna(v) and v != ""},
    }

    # -------------------------------------------------------------------------
    # 1. Similarity summary
    # -------------------------------------------------------------------------
    try:
        result["similarity"] = {
            "top_analogs": [
                {
                    "rank":             int(r.get("Similarity_Rank", i + 1)),
                    "sku_id":           str(r.get("Existing_SKU_ID", "")),
                    "product_name":     str(r.get("Existing_Product_Name", "")),
                    "brand":            str(r.get("Existing_Brand", "")),
                    "sub_category":     str(r.get("Existing_Sub_Category", "")),
                    "similarity_score": round(float(r.get("Final_Similarity_Score", 0)), 4),
                    "hierarchy":        round(float(r.get("Hierarchy_Similarity",   0)), 4),
                    "functional":       round(float(r.get("Functional_Similarity",  0)), 4),
                    "ingredient":       round(float(r.get("Ingredient_Similarity",  0)), 4),
                    "commercial":       round(float(r.get("Commercial_Similarity",  0)), 4),
                }
                for i, r in enumerate(sim_rows)
            ],
            "n_analogs": len(sim_rows),
        }
    except Exception as e:
        errors.append(f"similarity: {e}")
        result["similarity"] = {"top_analogs": [], "n_analogs": 0}

    # -------------------------------------------------------------------------
    # 2. Hierarchical Forecast
    # -------------------------------------------------------------------------
    try:
        result["hierarchical_forecast"] = build_hierarchical_forecast(new_sku_id, attrs)
    except Exception as e:
        errors.append(f"hierarchical_forecast: {e}")
        result["hierarchical_forecast"] = {"error": str(e)}

    # Total forecast units for downstream modules
    fc_summary = result["hierarchical_forecast"].get("summary", {}) if isinstance(result["hierarchical_forecast"], dict) else {}
    total_units = float(fc_summary.get("enterprise_total", {}).get("Units", 0))

    # -------------------------------------------------------------------------
    # 3. Cannibalization
    # -------------------------------------------------------------------------
    try:
        result["cannibalization"] = estimate_cannibalization(
            new_sku_id=new_sku_id,
            new_sku_attrs=attrs,
            forecast_units_total=total_units,
            top_n=top_n_analogs * 2,
        )
    except Exception as e:
        errors.append(f"cannibalization: {e}")
        result["cannibalization"] = {"error": str(e)}

    # -------------------------------------------------------------------------
    # 4. Store Recommendation
    # -------------------------------------------------------------------------
    try:
        result["store_recommendation"] = recommend_stores(new_sku_id, attrs)
    except Exception as e:
        errors.append(f"store_recommendation: {e}")
        result["store_recommendation"] = {"error": str(e)}

    # -------------------------------------------------------------------------
    # 5. Scenario Simulation
    # -------------------------------------------------------------------------
    try:
        scenarios_input = [
            {"label": "Base Case",         "price_delta_pct": 0,    "promo_intensity": 0,   "pack_size_delta_pct": 0},
            {"label": "Price −5%",         "price_delta_pct": -5,   "promo_intensity": 0,   "pack_size_delta_pct": 0},
            {"label": "Price +5%",         "price_delta_pct": 5,    "promo_intensity": 0,   "pack_size_delta_pct": 0},
            {"label": "Promo 50%",         "price_delta_pct": 0,    "promo_intensity": 0.5, "pack_size_delta_pct": 0},
            {"label": "Price −5% + Promo", "price_delta_pct": -5,   "promo_intensity": 0.5, "pack_size_delta_pct": 0},
            {"label": "Pack +20%",         "price_delta_pct": 0,    "promo_intensity": 0,   "pack_size_delta_pct": 20},
        ]
        result["scenarios"] = compare_scenarios(
            new_sku_id    = new_sku_id,
            new_sku_attrs = attrs,
            base_units    = max(total_units, 1.0),
            scenarios     = scenarios_input,
        )
    except Exception as e:
        errors.append(f"scenarios: {e}")
        result["scenarios"] = {"error": str(e)}

    # -------------------------------------------------------------------------
    # 6. Explainability
    # -------------------------------------------------------------------------
    try:
        expl_similarity = []
        expl_differences = []
        for r in sim_rows[:3]:
            analog_id = str(r.get("Existing_SKU_ID", ""))
            if analog_id:
                expl_similarity.append({
                    "analog_sku_id":  analog_id,
                    "analog_name":    str(r.get("Existing_Product_Name", analog_id)),
                    **explain_similarity(attrs, analog_id, r),
                })
                expl_differences.append({
                    "analog_sku_id": analog_id,
                    "analog_name":   str(r.get("Existing_Product_Name", analog_id)),
                    "differences":   explain_differences(attrs, analog_id),
                })

        expl_forecast = explain_forecast(
            new_sku_id, attrs,
            result["hierarchical_forecast"],
            result.get("cannibalization", {}),
        )

        expl_risks = explain_risks(
            attrs,
            result.get("cannibalization", {}),
            result.get("store_recommendation", {}),
            result.get("hierarchical_forecast", {}),
        )

        attr_contrib = attribute_contributions(new_sku_id, sim_rows)

        result["explainability"] = {
            "similarity_explanations":   expl_similarity,
            "difference_explanations":   expl_differences,
            "forecast_explanation":      expl_forecast,
            "risk_explanation":          expl_risks,
            "attribute_contributions":   attr_contrib,
        }
    except Exception as e:
        errors.append(f"explainability: {e}")
        result["explainability"] = {"error": str(e)}

    # -------------------------------------------------------------------------
    # 7. Whitespace Detection
    # -------------------------------------------------------------------------
    try:
        result["whitespace"] = detect_whitespace(
            focus_sub_category=attrs.get("Sub_Category"),
            top_n=10,
        )
    except Exception as e:
        errors.append(f"whitespace: {e}")
        result["whitespace"] = {"error": str(e)}

    # -------------------------------------------------------------------------
    # 8. AI Merchant Copilot
    # -------------------------------------------------------------------------
    try:
        result["copilot"] = generate_copilot_summary(
            new_sku_id       = new_sku_id,
            new_sku_attrs    = attrs,
            similarity_data  = result.get("similarity",          {}),
            forecast_data    = result.get("hierarchical_forecast",{}),
            cannib_data      = result.get("cannibalization",     {}),
            store_rec_data   = result.get("store_recommendation",{}),
            whitespace_data  = result.get("whitespace",          {}),
            risks_data       = result.get("explainability", {}).get("risk_explanation", {}),
        )
    except Exception as e:
        errors.append(f"copilot: {e}")
        result["copilot"] = {"error": str(e)}

    # -------------------------------------------------------------------------
    # Status
    # -------------------------------------------------------------------------
    result["status"] = "ok" if not errors else "partial"
    result["errors"] = errors
    return result
