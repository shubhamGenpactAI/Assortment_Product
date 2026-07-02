"""
explainer.py
Rule-based natural-language explainability engine.

Generates merchant-friendly, data-grounded explanations for:
  A. Similarity explanation  (why this SKU is similar to analogs)
  B. Difference explanation  (how it differs from analogs)
  C. Forecast explanation    (what drives the demand prediction)
  D. Risk explanation        (what could go wrong)
  E. Attribute contributions (which attributes drive similarity most)

All language is concise business prose. No filler phrases.
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

def _sim()      -> pd.DataFrame: return _load("sim", _OUT / "new_sku_similarity_scores.csv")
def _sku_master()-> pd.DataFrame: return _load("sm", _RAW / "SKU_Master.csv")
def _clusters() -> pd.DataFrame: return _load("cl", _OUT / "store_clusters.csv")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fmt_pct(v: float) -> str:
    return f"{v*100:.0f}%"

def _sku_attrs(sku_id: str) -> dict:
    sm = _sku_master()
    if sm.empty:
        return {}
    col = "SKU_ID" if "SKU_ID" in sm.columns else sm.columns[0]
    row = sm[sm[col] == sku_id]
    if row.empty:
        return {}
    return row.iloc[0].to_dict()


# ---------------------------------------------------------------------------
# A. Similarity explanation
# ---------------------------------------------------------------------------
def explain_similarity(
    new_sku_attrs:      dict,
    analog_sku_id:      str,
    similarity_row:     dict,
) -> dict[str, Any]:
    """
    Returns:
      headline   — one-line headline
      reasons    — list of specific similarity reasons (bullet-ready)
      score_breakdown — dict of group scores
    """
    analog_attrs = _sku_attrs(analog_sku_id)
    reasons = []
    score_breakdown = {
        "hierarchy":   round(float(similarity_row.get("Hierarchy_Similarity",  0)), 3),
        "functional":  round(float(similarity_row.get("Functional_Similarity", 0)), 3),
        "ingredient":  round(float(similarity_row.get("Ingredient_Similarity", 0)), 3),
        "commercial":  round(float(similarity_row.get("Commercial_Similarity", 0)), 3),
        "overall":     round(float(similarity_row.get("Final_Similarity_Score",0)), 3),
    }

    # Hierarchy
    for col in ["Sub_Category", "Segment", "Attribute_Claim"]:
        n_val = str(new_sku_attrs.get(col, "") or "").strip()
        a_val = str(analog_attrs.get(col, "") or "").strip()
        if n_val and a_val and n_val.lower() == a_val.lower():
            reasons.append(f"Same {col.replace('_', ' ').lower()}: {n_val}")

    # Functional flags
    func_flags = ["Sulphate_Free_Flag", "Paraben_Free_Flag", "Organic_Flag",
                  "Dandruff_Flag", "Hair_Fall_Flag", "Color_Protection_Flag"]
    shared_func = []
    for f in func_flags:
        nv = str(new_sku_attrs.get(f, "") or "").lower() in ("1", "yes", "true")
        av = str(analog_attrs.get(f, "") or "").lower() in ("1", "yes", "true")
        if nv and av:
            shared_func.append(f.replace("_Flag", "").replace("_", "-"))
    if shared_func:
        reasons.append(f"Shared functional claims: {', '.join(shared_func)}")

    # Ingredients
    n_ings = set(
        str(new_sku_attrs.get(f"Ingredient_{i}", "") or "").lower().strip()
        for i in range(1, 5)
    ) - {"", "nan"}
    a_ings = set(
        str(analog_attrs.get(f"Ingredient_{i}", "") or "").lower().strip()
        for i in range(1, 5)
    ) - {"", "nan"}
    shared_ings = n_ings & a_ings
    if shared_ings:
        reasons.append(f"{len(shared_ings)} shared key ingredient(s): {', '.join(sorted(shared_ings))}")

    # Commercial
    n_brand = str(new_sku_attrs.get("Brand", "") or "")
    a_brand = str(analog_attrs.get("Brand", "") or "")
    if n_brand and a_brand and n_brand.lower() == a_brand.lower():
        reasons.append(f"Same brand: {n_brand}")

    n_pb = str(new_sku_attrs.get("Price_Band", "") or "")
    a_pb = str(analog_attrs.get("Price_Band", "") or "")
    if n_pb and a_pb and n_pb.lower() == a_pb.lower():
        reasons.append(f"Same price tier: {n_pb}")

    # Headline
    overall = score_breakdown["overall"]
    strength = "highly similar" if overall >= 0.75 else "moderately similar" if overall >= 0.50 else "loosely similar"
    analog_name = str(similarity_row.get("Existing_Product_Name", analog_sku_id))
    headline = f"{strength.capitalize()} to {analog_name} (score: {_fmt_pct(overall)})"

    return {
        "headline":        headline,
        "reasons":         reasons or ["General category overlap — no strong individual attribute match."],
        "score_breakdown": score_breakdown,
    }


# ---------------------------------------------------------------------------
# B. Difference explanation
# ---------------------------------------------------------------------------
def explain_differences(
    new_sku_attrs: dict,
    analog_sku_id: str,
) -> list[str]:
    """Returns list of key differentiating attributes."""
    analog = _sku_attrs(analog_sku_id)
    diffs = []

    # Price comparison
    np_ = float(new_sku_attrs.get("List_Price_USD", 0) or 0)
    ap_ = float(analog.get("List_Price_USD", 0) or 0)
    if np_ > 0 and ap_ > 0:
        delta_pct = (np_ - ap_) / ap_ * 100
        if abs(delta_pct) > 8:
            direction = "higher" if delta_pct > 0 else "lower"
            diffs.append(f"{abs(delta_pct):.0f}% {direction} price (${np_:.2f} vs ${ap_:.2f})")

    # Pack size comparison
    ns_ = float(new_sku_attrs.get("Pack_Size_ml", 0) or 0)
    as_ = float(analog.get("Pack_Size_ml", 0) or 0)
    if ns_ > 0 and as_ > 0 and abs(ns_ - as_) / as_ > 0.10:
        direction = "larger" if ns_ > as_ else "smaller"
        diffs.append(f"{direction} pack size ({ns_:.0f}ml vs {as_:.0f}ml)")

    # Functional flags
    func_flags = ["Sulphate_Free_Flag", "Paraben_Free_Flag", "Organic_Flag",
                  "Dandruff_Flag", "Hair_Fall_Flag", "Color_Protection_Flag"]
    for f in func_flags:
        nv = str(new_sku_attrs.get(f, "") or "").lower() in ("1", "yes", "true")
        av = str(analog.get(f, "") or "").lower() in ("1", "yes", "true")
        if nv and not av:
            diffs.append(f"New feature: {f.replace('_Flag', '').replace('_', '-')}")
        elif av and not nv:
            diffs.append(f"Does not carry: {f.replace('_Flag', '').replace('_', '-')}")

    # Price band
    n_pb = str(new_sku_attrs.get("Price_Band", "") or "")
    a_pb = str(analog.get("Price_Band", "") or "")
    if n_pb and a_pb and n_pb.lower() != a_pb.lower():
        diffs.append(f"Different price tier ({n_pb} vs {a_pb})")

    return diffs or ["No material attribute differences identified."]


# ---------------------------------------------------------------------------
# C. Forecast explanation
# ---------------------------------------------------------------------------
def explain_forecast(
    new_sku_id:     str,
    new_sku_attrs:  dict,
    forecast_data:  dict,   # output of build_hierarchical_forecast
    cannib_data:    dict,   # output of estimate_cannibalization
) -> dict[str, Any]:
    """
    Explains what drives the demand forecast.
    Returns headline + list of driver sentences.
    """
    drivers = []

    # Confidence
    avg_conf = forecast_data.get("avg_confidence", 0.5)
    if avg_conf >= 0.70:
        drivers.append(f"High forecast confidence ({_fmt_pct(avg_conf)}) — strong analog SKU coverage.")
    elif avg_conf >= 0.45:
        drivers.append(f"Moderate forecast confidence ({_fmt_pct(avg_conf)}) — limited analog history.")
    else:
        drivers.append(f"Low forecast confidence ({_fmt_pct(avg_conf)}) — sparse analogs. Treat as directional.")

    # Sparse stores
    sparse = forecast_data.get("sparse_stores", [])
    if sparse:
        drivers.append(f"{len(sparse)} store(s) have fewer than 2 analog SKUs — forecasts less reliable there.")

    # Cluster strength
    cluster_summary = forecast_data.get("summary", {}).get("by_cluster", {})
    if cluster_summary:
        best_cluster = max(cluster_summary, key=lambda k: cluster_summary[k].get("Units", 0))
        best_units   = cluster_summary[best_cluster].get("Units", 0)
        drivers.append(f"Strongest demand from '{best_cluster}' cluster ({round(best_units)} units).")

    # Cannibalization adjustment
    cannib_rate = cannib_data.get("cannibalization_rate", 0) if cannib_data else 0
    if cannib_rate > 0.40:
        drivers.append(f"Significant cannibalization expected ({_fmt_pct(cannib_rate)}), reducing net new demand.")
    elif cannib_rate > 0.20:
        drivers.append(f"Moderate cannibalization ({_fmt_pct(cannib_rate)}) — largely incremental growth.")
    else:
        drivers.append(f"Low cannibalization risk ({_fmt_pct(cannib_rate)}) — most demand is genuinely new.")

    # Health attributes
    if str(new_sku_attrs.get("Organic_Flag", "")).lower() in ("1", "yes", "true"):
        drivers.append("Organic positioning drives premium demand — strong in affluent suburban clusters.")
    if str(new_sku_attrs.get("Hair_Fall_Flag", "")).lower() in ("1", "yes", "true"):
        drivers.append("Hair-fall positioning is a high-growth segment — positive demand tailwind.")

    # Total
    ent_total = forecast_data.get("summary", {}).get("enterprise_total", {})
    total_units = ent_total.get("Units", 0)
    total_rev   = ent_total.get("Revenue", 0)
    headline = (
        f"Forecasting {round(total_units):,} units and ${total_rev:,.0f} revenue "
        f"over {forecast_data.get('summary', {}).get('week_count', 6)} weeks across "
        f"{forecast_data.get('summary', {}).get('store_count', 0)} stores."
    )

    return {
        "headline": headline,
        "drivers":  drivers,
    }


# ---------------------------------------------------------------------------
# D. Risk explanation
# ---------------------------------------------------------------------------
def explain_risks(
    new_sku_attrs: dict,
    cannib_data:   dict,
    store_rec_data: dict,
    forecast_data:  dict,
) -> dict[str, Any]:
    """Returns ranked list of risk factors with severity ratings."""
    risks = []

    # Cannibalization risk
    cannib_score = cannib_data.get("cannibalization_score", 0) if cannib_data else 0
    if cannib_score >= 0.65:
        risks.append({"factor": "High cannibalization risk", "severity": "High",
                      "detail": cannib_data.get("summary_nl", "")})
    elif cannib_score >= 0.35:
        risks.append({"factor": "Moderate cannibalization risk", "severity": "Medium",
                      "detail": f"~{cannib_data.get('cannibalization_rate', 0)*100:.0f}% demand transfer expected."})

    # Forecast confidence
    avg_conf = forecast_data.get("avg_confidence", 0.5) if forecast_data else 0.5
    if avg_conf < 0.45:
        risks.append({"factor": "Weak forecast confidence", "severity": "High",
                      "detail": f"Analog SKU coverage is thin. Forecast confidence: {_fmt_pct(avg_conf)}."})

    # Price sensitivity
    price_band = str(new_sku_attrs.get("Price_Band", "") or "").lower()
    if "premium" in price_band or "luxury" in price_band:
        risks.append({"factor": "Premium price sensitivity", "severity": "Medium",
                      "detail": "Premium SKUs show higher elasticity. Price promotions may be needed in lower-income stores."})

    # Crowded segment
    sim = _sim()
    if not sim.empty:
        col_new = "New_SKU_ID" if "New_SKU_ID" in sim.columns else sim.columns[0]
        n_analogs = len(sim[sim[col_new] == new_sku_attrs.get("New_SKU_ID", "")]) if "New_SKU_ID" in new_sku_attrs else 0
        if n_analogs >= 8:
            risks.append({"factor": "Crowded analog landscape", "severity": "Medium",
                          "detail": f"{n_analogs} existing SKUs in a similar space — strong competition."})

    # Limited store fit
    n_rec = store_rec_data.get("n_recommended", 0) if store_rec_data else 0
    n_total = store_rec_data.get("n_total", 1) if store_rec_data else 1
    fit_pct = n_rec / max(n_total, 1)
    if fit_pct < 0.40:
        risks.append({"factor": "Narrow store fit", "severity": "Medium",
                      "detail": f"Only {_fmt_pct(fit_pct)} of stores ({n_rec}/{n_total}) score above launch threshold."})

    # Sparse analogues
    sparse = forecast_data.get("sparse_stores", []) if forecast_data else []
    if len(sparse) > 2:
        risks.append({"factor": "Sparse analog coverage", "severity": "Low",
                      "detail": f"{len(sparse)} stores have limited analog SKU history — forecast less reliable."})

    if not risks:
        risks.append({"factor": "No material risks identified", "severity": "Low",
                      "detail": "Launch conditions appear favourable."})

    return {
        "risks":       risks,
        "risk_count":  len(risks),
        "highest_severity": "High" if any(r["severity"] == "High" for r in risks) else
                            "Medium" if any(r["severity"] == "Medium" for r in risks) else "Low",
    }


# ---------------------------------------------------------------------------
# E. Attribute contribution (feature importance proxy)
# ---------------------------------------------------------------------------
def attribute_contributions(
    new_sku_id: str,
    similarity_rows: list[dict],
) -> dict[str, Any]:
    """
    Compute weighted contribution of each similarity group to the final score.
    Uses the 4-group weights as defined in similarity.py:
      Hierarchy 35%, Functional 25%, Ingredient 20%, Commercial 20%
    Per-attribute breakdown within each group (approximate, rule-based).
    """
    WEIGHTS = {
        "Hierarchy":  0.35,
        "Functional": 0.25,
        "Ingredient": 0.20,
        "Commercial": 0.20,
    }

    if not similarity_rows:
        return {"group_contributions": WEIGHTS, "detail": []}

    # Average group scores across top analogs
    group_avgs = {}
    for grp in WEIGHTS:
        col = f"{grp}_Similarity"
        vals = [float(r.get(col, 0)) for r in similarity_rows if col in r]
        group_avgs[grp] = float(np.mean(vals)) if vals else 0.0

    # Weighted contribution to overall
    total_contrib = sum(WEIGHTS[g] * group_avgs[g] for g in WEIGHTS)
    group_contributions = {}
    for grp in WEIGHTS:
        raw = WEIGHTS[grp] * group_avgs[grp]
        pct = (raw / total_contrib * 100) if total_contrib > 0 else WEIGHTS[grp] * 100
        group_contributions[grp] = {
            "weight":          WEIGHTS[grp],
            "avg_group_score": round(group_avgs[grp], 4),
            "contribution_pct": round(pct, 1),
        }

    # Rank groups by contribution
    ranked = sorted(group_contributions.items(), key=lambda x: x[1]["contribution_pct"], reverse=True)

    detail = []
    for grp, v in ranked:
        detail.append({
            "group":            grp,
            "contribution_pct": v["contribution_pct"],
            "avg_score":        v["avg_group_score"],
            "weight":           v["weight"],
            "label":            f"{grp} ({v['contribution_pct']:.0f}% of similarity)",
        })

    top_group = ranked[0][0] if ranked else "Unknown"
    summary = (
        f"Similarity is primarily driven by {top_group} attributes "
        f"({ranked[0][1]['contribution_pct']:.0f}% contribution), "
        f"followed by {ranked[1][0]} ({ranked[1][1]['contribution_pct']:.0f}%)."
        if len(ranked) >= 2 else "Insufficient data for contribution analysis."
    )

    return {
        "group_contributions": group_contributions,
        "ranked_detail":       detail,
        "top_driver":          top_group,
        "summary":             summary,
    }
