"""
general_service.py
==================
Data services for: store list, delisting risk, and new-SKU similarity.
"""

import pandas as pd
from pathlib import Path
from functools import lru_cache

from ..database.connection import read_table_or_csv

_SVC  = Path(__file__).resolve().parent
_PROJ = _SVC.parent.parent           # Assortment/
_OUT  = _PROJ / "Outputs"
_RAW  = _PROJ / "Raw_Input"


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------
@lru_cache(maxsize=1)
def _sku():     return read_table_or_csv("sku_master",                _RAW / "SKU_Master.csv")

@lru_cache(maxsize=1)
def _delist():  return read_table_or_csv("delisting_recommendations", _OUT / "delisting_recommendations.csv")

@lru_cache(maxsize=1)
def _sim():     return read_table_or_csv("new_sku_similarity_scores", _OUT / "new_sku_similarity_scores.csv")

@lru_cache(maxsize=1)
def _demand():  return read_table_or_csv("weekly_demand_output",      _OUT / "weekly_demand_output.csv")

@lru_cache(maxsize=1)
def _forecast():
    df = read_table_or_csv("forecast_output", _OUT / "Forecast_Output.csv")
    df["Final_Forecast"] = pd.to_numeric(df["Final_Forecast"], errors="coerce").fillna(0)
    return df


# ---------------------------------------------------------------------------
# Store list
# ---------------------------------------------------------------------------
def get_store_list() -> list[str]:
    fc = _forecast()
    return sorted(fc["Store_ID"].dropna().unique().tolist())


# ---------------------------------------------------------------------------
# Delisting Risk
# ---------------------------------------------------------------------------
def get_delist_data(rec_filter: str | None = None, sub_cat: str | None = None,
                    abc_cls: str | None = None) -> dict:
    df = _delist().copy()
    if rec_filter: df = df[df["recommendation"] == rec_filter]
    if sub_cat and "Sub_Category" in df.columns: df = df[df["Sub_Category"] == sub_cat]
    if abc_cls  and "ABC_Class"   in df.columns: df = df[df["ABC_Class"]    == abc_cls]

    filters = {
        "recommendations": sorted(_delist()["recommendation"].dropna().unique().tolist()) if "recommendation" in _delist().columns else [],
        "sub_categories":  sorted(_delist()["Sub_Category"].dropna().unique().tolist())   if "Sub_Category"   in _delist().columns else [],
        "abc_classes":     sorted(_delist()["ABC_Class"].dropna().unique().tolist())       if "ABC_Class"      in _delist().columns else [],
    }

    show_cols = [c for c in ["SKU_ID", "Sub_Category", "ABC_Class", "granularity_level",
                              "granularity_value", "total_revenue", "total_margin",
                              "delist_score", "recommendation", "nl_summary"] if c in df.columns]
    top50 = df.nlargest(50, "delist_score") if "delist_score" in df.columns else df.head(50)

    scatter = []
    if {"delist_score", "total_revenue"}.issubset(df.columns):
        sku  = _sku()
        uniq = df.drop_duplicates("SKU_ID").copy()
        if sku is not None and "Product_Name" in sku.columns:
            uniq = uniq.merge(sku[["SKU_ID", "Product_Name"]], on="SKU_ID", how="left")
            uniq["label"] = uniq["Product_Name"].fillna(uniq["SKU_ID"]).str[:20]
        else:
            uniq["label"] = uniq["SKU_ID"]
        scatter = uniq[["label", "total_revenue", "delist_score", "recommendation"]].fillna(0).to_dict("records")

    counts = {}
    if "recommendation" in df.columns:
        counts = df.drop_duplicates("SKU_ID")["recommendation"].value_counts().to_dict()

    return {
        "filter_options": filters,
        "counts":         counts,
        "scatter":        scatter,
        "table":          top50[show_cols].fillna("").to_dict("records"),
    }


# ---------------------------------------------------------------------------
# New SKU / Similarity
# ---------------------------------------------------------------------------
def get_similarity_data() -> dict:
    sim = _sim()
    if sim is None or sim.empty:
        return {"scores": [], "new_skus": []}
    new_skus = sorted(sim["New_SKU_ID"].dropna().unique().tolist()) if "New_SKU_ID" in sim.columns else []
    return {
        "new_skus": new_skus,
        "scores":   sim.to_dict("records"),
    }


def get_analog_forecast(new_sku_id: str) -> list[dict]:
    sim = _sim()
    dm  = _demand()
    if sim is None or dm is None:
        return []
    dm = dm.copy()
    dm["Quantity_Sold"] = pd.to_numeric(dm["Quantity_Sold"], errors="coerce").fillna(0)
    top = (sim[sim["New_SKU_ID"] == new_sku_id].nlargest(5, "Final_Similarity_Score")
           if "New_SKU_ID" in sim.columns else sim.head(5))
    if top.empty:
        return []
    wsum = top["Final_Similarity_Score"].sum()
    if wsum <= 0:
        return []
    wmap = dict(zip(top["Existing_SKU_ID"], top["Final_Similarity_Score"] / wsum))
    d = dm[dm["SKU_ID"].isin(wmap)].copy()
    d["w"]    = d["SKU_ID"].map(wmap)
    d["wqty"] = d["w"] * d["Quantity_Sold"]
    g = d.groupby("Year_WK").agg(wsum=("wqty", "sum"), pw=("w", "sum")).reset_index()
    g["Analog_Demand"] = (g["wsum"] / g["pw"]).round(1)
    return g.rename(columns={"Year_WK": "week"})[["week", "Analog_Demand"]].sort_values("week").to_dict("records")
