"""
hierarchical_forecast.py
Multi-level demand / revenue / margin aggregation for new SKU analog forecasts.

Hierarchy:  Store → Cluster → Region → Enterprise
Outputs per level:
  - units (point + lower + upper)
  - revenue  (point + lower + upper)
  - margin   (point + lower + upper)
  - confidence_score  (0-1)
  - sparse_analog_flag (bool)
  - weekly breakdown list
"""

from __future__ import annotations
import warnings
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_ROOT = Path(__file__).resolve().parent.parent.parent
_OUT  = _ROOT / "Outputs"
_RAW  = _ROOT / "Raw_Input"

# ---------------------------------------------------------------------------
# Loaders (lazy, cached module-level)
# ---------------------------------------------------------------------------
_cache: dict[str, pd.DataFrame] = {}

def _load(key: str, path: Path) -> pd.DataFrame:
    if key not in _cache:
        if path.exists():
            _cache[key] = pd.read_csv(path)
        else:
            _cache[key] = pd.DataFrame()
    return _cache[key]

def _analog_forecast(sku_id: str = "") -> pd.DataFrame:
    # Check in-memory cache from uploaded CSVs first
    if sku_id:
        try:
            from .csv_upload_processor import get_cached_analog_demand
            cached = get_cached_analog_demand(sku_id)
            if cached is not None and not cached.empty:
                return cached
        except ImportError:
            pass
    return _load("analog_fc", _OUT / "new_sku_analog_demand_forecast.csv")

def _store_master() -> pd.DataFrame:
    return _load("store_master", _RAW / "Store_Master.csv")

def _store_clusters() -> pd.DataFrame:
    return _load("clusters", _OUT / "store_clusters.csv")

def _sku_master() -> pd.DataFrame:
    return _load("sku_master", _RAW / "SKU_Master.csv")

def _similarity_scores() -> pd.DataFrame:
    return _load("sim_scores", _OUT / "new_sku_similarity_scores.csv")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
CONFIDENCE_COLS = ["Forecast_Lower", "Forecast_Upper", "Final_Forecast"]

def _price_cost(new_sku_attrs: dict) -> tuple[float, float]:
    """Return (list_price, unit_cost) from new_sku_attrs or fallback to sub_cat median."""
    price = float(new_sku_attrs.get("List_Price_USD", 0) or 0)
    cost  = float(new_sku_attrs.get("Unit_Cost_USD",  0) or 0)
    if price <= 0:
        sm = _sku_master()
        if not sm.empty:
            sub = new_sku_attrs.get("Sub_Category", "")
            g = sm[sm.get("Sub_Category", sm.get("sub_category", pd.Series([]))) == sub]
            if g.empty:
                g = sm
            price = float(g["List_Price_USD"].median() or 0) if "List_Price_USD" in g else 0
            cost  = float(g["Unit_Cost_USD"].median()  or 0) if "Unit_Cost_USD"  in g else 0
    return max(price, 0.0), max(cost, 0.0)


def _analog_confidence(new_sku_id: str) -> dict[str, float]:
    """
    Confidence per store based on:
      - quality of best analog similarity score
      - number of analog SKUs available
    Returns {store_id: confidence_score}
    """
    sim = _similarity_scores()
    if sim.empty:
        return {}
    col_new = "New_SKU_ID" if "New_SKU_ID" in sim.columns else sim.columns[0]
    rows = sim[sim[col_new] == new_sku_id]
    if rows.empty:
        return {}
    best_sim = float(rows["Final_Similarity_Score"].max()) if "Final_Similarity_Score" in rows else 0.5
    n_analogs = min(len(rows), 5) / 5.0
    # confidence = blend of analog quality + coverage
    confidence = 0.6 * best_sim + 0.4 * n_analogs
    # store-level (same confidence for all stores — differentiated in store-level pass)
    af = _analog_forecast()
    if af.empty:
        return {}
    col_nsku = "New_SKU_ID" if "New_SKU_ID" in af.columns else af.columns[0]
    stores = af[af[col_nsku] == new_sku_id]["Store_ID"].unique() if "Store_ID" in af.columns else []
    return {str(s): round(confidence, 4) for s in stores}


# ---------------------------------------------------------------------------
# Core: build store-week dataframe for a new SKU
# ---------------------------------------------------------------------------
def _build_store_week_df(new_sku_id: str, new_sku_attrs: dict) -> pd.DataFrame:
    """
    Merges analog demand forecast with store/cluster/region metadata.
    Adds revenue, margin, lower/upper bounds.
    Returns grain: Store × Week
    """
    af = _analog_forecast(new_sku_id)
    if af.empty:
        return pd.DataFrame()

    col_nsku = "New_SKU_ID" if "New_SKU_ID" in af.columns else af.columns[0]
    df = af[af[col_nsku] == new_sku_id].copy()
    if df.empty:
        return pd.DataFrame()

    # Rename analog demand column
    demand_col = "Analog_Demand" if "Analog_Demand" in df.columns else df.columns[-1]
    df = df.rename(columns={demand_col: "Units"})
    df["Units"] = pd.to_numeric(df["Units"], errors="coerce").fillna(0).clip(lower=0)

    # Confidence interval: use analog similarity to set interval width
    conf_map = _analog_confidence(new_sku_id)
    df["confidence"] = df["Store_ID"].astype(str).map(conf_map).fillna(0.5)

    # Wider interval for lower-confidence stores
    interval_half = (1 - df["confidence"]) * 0.40  # ±40% at 0% confidence, ±0% at 100%
    df["Units_Lower"] = (df["Units"] * (1 - interval_half)).clip(lower=0)
    df["Units_Upper"] = df["Units"] * (1 + interval_half)

    # Sparse analog flag
    n_analogs_col = "Analog_SKUs_Used" if "Analog_SKUs_Used" in df.columns else None
    if n_analogs_col:
        df["sparse_analog"] = pd.to_numeric(df[n_analogs_col], errors="coerce").fillna(0) < 2
    else:
        df["sparse_analog"] = df["confidence"] < 0.4

    # Price / margin
    price, cost = _price_cost(new_sku_attrs)
    margin_per_unit = max(price - cost, 0.0)
    df["Revenue"]       = df["Units"]       * price
    df["Revenue_Lower"] = df["Units_Lower"] * price
    df["Revenue_Upper"] = df["Units_Upper"] * price
    df["Margin"]        = df["Units"]       * margin_per_unit
    df["Margin_Lower"]  = df["Units_Lower"] * margin_per_unit
    df["Margin_Upper"]  = df["Units_Upper"] * margin_per_unit

    # Merge cluster
    clusters = _store_clusters()
    if not clusters.empty:
        df = df.merge(
            clusters[["Store_ID", "Cluster_ID", "Cluster_Label"]],
            on="Store_ID", how="left"
        )
    else:
        df["Cluster_ID"]    = "Unknown"
        df["Cluster_Label"] = "Unknown"

    # Merge region / geography
    sm = _store_master()
    if not sm.empty:
        geo_cols = [c for c in ["Store_ID", "Region", "Geography", "Urban_Rural"] if c in sm.columns]
        df = df.merge(sm[geo_cols], on="Store_ID", how="left")
    for col in ["Region", "Geography"]:
        if col not in df.columns:
            df[col] = "Unknown"

    return df


# ---------------------------------------------------------------------------
# Aggregate a dataframe to a given level
# ---------------------------------------------------------------------------
def _aggregate(df: pd.DataFrame, group_cols: list[str]) -> pd.DataFrame:
    num_cols = ["Units", "Units_Lower", "Units_Upper",
                "Revenue", "Revenue_Lower", "Revenue_Upper",
                "Margin", "Margin_Lower", "Margin_Upper"]
    num_cols = [c for c in num_cols if c in df.columns]
    week_col = "Year_WK" if "Year_WK" in df.columns else None
    if week_col:
        g = df.groupby(group_cols + [week_col], as_index=False)[num_cols].sum()
    else:
        g = df.groupby(group_cols, as_index=False)[num_cols].sum()
    return g


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def build_hierarchical_forecast(
    new_sku_id: str,
    new_sku_attrs: dict,
) -> dict[str, Any]:
    """
    Returns a dict with keys:
      store   — list of store-week records
      cluster — list of cluster-week records
      region  — list of region-week records
      enterprise — list of enterprise-week records
      summary — rollup totals per level
      confidence_map — {store_id: score}
      sparse_stores  — list of stores with low analog quality
    """
    df = _build_store_week_df(new_sku_id, new_sku_attrs)
    if df.empty:
        return {"error": f"No analog forecast found for new_sku_id='{new_sku_id}'"}

    week_col = "Year_WK" if "Year_WK" in df.columns else None
    metric_cols = ["Units", "Units_Lower", "Units_Upper",
                   "Revenue", "Revenue_Lower", "Revenue_Upper",
                   "Margin", "Margin_Lower", "Margin_Upper"]
    metric_cols = [c for c in metric_cols if c in df.columns]

    def _to_records(agg: pd.DataFrame) -> list[dict]:
        return agg.round(2).to_dict(orient="records")

    # Store level
    store_cols = ["Store_ID"] + (["Cluster_Label", "Region", "Geography"] if "Region" in df.columns else [])
    store_cols = [c for c in store_cols if c in df.columns]
    df_store = _aggregate(df, store_cols)

    # Cluster level
    cluster_cols = ["Cluster_ID", "Cluster_Label"] if "Cluster_ID" in df.columns else []
    df_cluster = _aggregate(df, cluster_cols) if cluster_cols else pd.DataFrame()

    # Region level
    region_cols = ["Region"] if "Region" in df.columns else []
    df_region = _aggregate(df, region_cols) if region_cols else pd.DataFrame()

    # Enterprise level
    if week_col:
        df_ent = df.groupby(week_col, as_index=False)[metric_cols].sum()
    else:
        df_ent = df[metric_cols].sum().to_frame().T

    # Summary (total across all weeks)
    def _total(frame: pd.DataFrame) -> dict:
        if frame.empty:
            return {}
        return {c: round(float(frame[c].sum()), 2) for c in metric_cols if c in frame.columns}

    # Confidence map
    conf_map = df.drop_duplicates("Store_ID").set_index("Store_ID")["confidence"].to_dict()
    conf_map = {k: round(float(v), 4) for k, v in conf_map.items()}

    sparse = df[df.get("sparse_analog", pd.Series([False]*len(df)))]["Store_ID"].unique().tolist() if "sparse_analog" in df.columns else []

    return {
        "store":      _to_records(df_store),
        "cluster":    _to_records(df_cluster),
        "region":     _to_records(df_region),
        "enterprise": _to_records(df_ent),
        "summary": {
            "enterprise_total":  _total(df),
            "by_cluster":        {
                row.get("Cluster_Label", row.get("Cluster_ID", "?")): {
                    c: round(float(df_cluster.loc[i, c]), 2)
                    for c in metric_cols if c in df_cluster.columns
                }
                for i, row in df_cluster.iterrows()
            } if not df_cluster.empty else {},
            "by_region":         {
                row.get("Region", "?"): {
                    c: round(float(df_region.loc[i, c]), 2)
                    for c in metric_cols if c in df_region.columns
                }
                for i, row in df_region.iterrows()
            } if not df_region.empty else {},
            "store_count":       int(df["Store_ID"].nunique()) if "Store_ID" in df.columns else 0,
            "week_count":        int(df[week_col].nunique()) if week_col else 0,
        },
        "confidence_map": conf_map,
        "sparse_stores":  [str(s) for s in sparse],
        "avg_confidence": round(float(np.mean(list(conf_map.values()))) if conf_map else 0.5, 4),
    }
