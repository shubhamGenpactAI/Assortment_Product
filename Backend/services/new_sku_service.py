"""
new_sku_service.py — Service layer for New SKU Intelligence API.
Thin adapter between FastAPI router and core engine modules.
"""

from __future__ import annotations
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from ..db import read_table_or_csv
from ..NewSKU.sku_intelligence import run_new_sku_intelligence
from ..NewSKU.hierarchical_forecast import build_hierarchical_forecast
from ..NewSKU.cannibalization        import estimate_cannibalization
from ..NewSKU.store_recommender      import recommend_stores
from ..NewSKU.scenario_simulator     import run_scenario
from ..NewSKU.whitespace_detector    import detect_whitespace
from ..NewSKU.explainer              import explain_similarity, explain_differences, attribute_contributions

_ROOT = Path(__file__).resolve().parent.parent.parent
_OUT  = _ROOT / "Outputs"

_sim_cache: dict = {}

def _sim_df() -> pd.DataFrame:
    if "df" not in _sim_cache:
        p = _OUT / "new_sku_similarity_scores.csv"
        _sim_cache["df"] = read_table_or_csv("new_sku_similarity_scores", p)
    return _sim_cache["df"]


# ---------------------------------------------------------------------------
# Service functions
# ---------------------------------------------------------------------------

def run_intelligence(
    new_sku_id:    str,
    new_sku_attrs: dict,
    top_n_analogs: int = 5,
    top_n_stores:  int = 10,
) -> dict[str, Any]:
    return run_new_sku_intelligence(
        new_sku_id    = new_sku_id,
        new_sku_attrs = new_sku_attrs,
        top_n_analogs = top_n_analogs,
        top_n_stores  = top_n_stores,
    )


def get_forecast(new_sku_id: str, attrs: dict) -> dict[str, Any]:
    return build_hierarchical_forecast(new_sku_id, attrs)


def get_cannibalization(
    new_sku_id: str,
    attrs: dict,
    forecast_units_total: float = 1000.0,
) -> dict[str, Any]:
    return estimate_cannibalization(new_sku_id, attrs, forecast_units_total)


def get_store_recommendation(new_sku_id: str, attrs: dict) -> dict[str, Any]:
    return recommend_stores(new_sku_id, attrs)


def run_custom_scenario(
    new_sku_id:          str,
    new_sku_attrs:       dict,
    base_units:          float,
    price_delta_pct:     float = 0.0,
    promo_intensity:     float = 0.0,
    pack_size_delta_pct: float = 0.0,
    geography_filter:    list | None = None,
    custom_elasticity:   float | None = None,
) -> dict[str, Any]:
    return run_scenario(
        new_sku_id          = new_sku_id,
        new_sku_attrs       = new_sku_attrs,
        base_units          = base_units,
        price_delta_pct     = price_delta_pct,
        promo_intensity     = promo_intensity,
        pack_size_delta_pct = pack_size_delta_pct,
        geography_filter    = geography_filter,
        custom_elasticity   = custom_elasticity,
    )


def get_whitespace(sub_category: Optional[str] = None, top_n: int = 15) -> dict[str, Any]:
    return detect_whitespace(focus_sub_category=sub_category, top_n=top_n)


def upload_csv(file_bytes: bytes, filename: str) -> dict[str, Any]:
    from ..NewSKU.csv_upload_processor import process_uploaded_csv
    return process_uploaded_csv(file_bytes, filename)


def clear_upload_cache() -> dict[str, Any]:
    from ..NewSKU.csv_upload_processor import clear_cache, list_uploaded_skus
    skus_before = list_uploaded_skus()
    clear_cache()
    return {"cleared": len(skus_before), "message": f"Removed {len(skus_before)} uploaded SKU(s) from cache."}


def get_new_sku_list() -> dict[str, Any]:
    from ..NewSKU.csv_upload_processor import list_uploaded_skus
    df = _sim_df()
    csv_skus: list[str] = []
    if not df.empty:
        col = "New_SKU_ID" if "New_SKU_ID" in df.columns else df.columns[0]
        csv_skus = sorted(df[col].dropna().unique().tolist())
    uploaded = list_uploaded_skus()
    # Merge: uploaded first (they are the freshest), then CSV skus not already in uploaded
    merged = uploaded + [s for s in csv_skus if s not in uploaded]
    return {
        "new_skus":    [str(s) for s in merged],
        "count":       len(merged),
        "csv_count":   len(csv_skus),
        "upload_count":len(uploaded),
    }


def get_analogs(new_sku_id: str, top_n: int = 5) -> dict[str, Any]:
    df = _sim_df()
    if df.empty:
        return {"analogs": [], "attribute_contributions": {}}

    col_new = "New_SKU_ID" if "New_SKU_ID" in df.columns else df.columns[0]
    rows = df[df[col_new] == new_sku_id]
    if "Final_Similarity_Score" in rows.columns:
        rows = rows.nlargest(top_n, "Final_Similarity_Score")
    else:
        rows = rows.head(top_n)

    sim_rows = rows.to_dict(orient="records")

    analogs = []
    for r in sim_rows:
        analog_id = str(r.get("Existing_SKU_ID", ""))
        sim_expl  = explain_similarity({}, analog_id, r)
        diffs     = explain_differences({}, analog_id)
        analogs.append({
            "sku_id":       analog_id,
            "product_name": str(r.get("Existing_Product_Name", analog_id)),
            "brand":        str(r.get("Existing_Brand", "")),
            "sub_category": str(r.get("Existing_Sub_Category", "")),
            "similarity_score": float(r.get("Final_Similarity_Score", 0)),
            "explanation":  sim_expl,
            "differences":  diffs,
        })

    contrib = attribute_contributions(new_sku_id, sim_rows)
    return {"analogs": analogs, "attribute_contributions": contrib}
