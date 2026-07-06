"""
store_recommender.py
Scores and ranks stores for new SKU launch prioritisation.

Scoring formula (weights tunable):
  store_score = 0.35 × analog_velocity_score
              + 0.25 × demographic_fit_score
              + 0.20 × cluster_affinity_score
              + 0.10 × category_penetration_score
              + 0.10 × price_compatibility_score

Inputs
------
  Outputs/new_sku_analog_demand_forecast.csv
  Outputs/store_clusters.csv
  Outputs/store_clusters_summary.json
  Raw_Input/Store_Master.csv
  Raw_Input/SKU_Master.csv
  Raw_Input/Sales_Tx.csv  (for category penetration)
"""

from __future__ import annotations
import json
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.preprocessing import MinMaxScaler

from ..database.connection import read_table_or_csv

_ROOT = Path(__file__).resolve().parent.parent.parent
_OUT  = _ROOT / "Outputs"
_RAW  = _ROOT / "Raw_Input"

_cache: dict[str, Any] = {}

def _load_csv(key: str, path: Path) -> pd.DataFrame:
    if key not in _cache:
        _cache[key] = read_table_or_csv(path.stem.lower(), path)
    return _cache[key]

def _load_json(key: str, path: Path) -> dict:
    if key not in _cache:
        _cache[key] = json.loads(path.read_text()) if path.exists() else {}
    return _cache[key]

def _analog_fc()    -> pd.DataFrame: return _load_csv("afc", _OUT / "new_sku_analog_demand_forecast.csv")
def _clusters()     -> pd.DataFrame: return _load_csv("cl",  _OUT / "store_clusters.csv")
def _cluster_meta() -> dict:         return _load_json("cm",  _OUT / "store_clusters_summary.json")
def _store_master() -> pd.DataFrame: return _load_csv("sm",  _RAW / "Store_Master.csv")
def _sku_master()   -> pd.DataFrame: return _load_csv("skm", _RAW / "SKU_Master.csv")
def _sales_tx()     -> pd.DataFrame: return _load_csv("tx",  _RAW / "Sales_Tx.csv")


# ---------------------------------------------------------------------------
# Sub-scorers
# ---------------------------------------------------------------------------

def _analog_velocity(new_sku_id: str) -> pd.Series:
    """Mean weekly analog demand per store → normalised 0–1."""
    af = _analog_fc()
    if af.empty:
        return pd.Series(dtype=float)
    col_new = "New_SKU_ID" if "New_SKU_ID" in af.columns else af.columns[0]
    df = af[af[col_new] == new_sku_id].copy()
    if df.empty or "Store_ID" not in df.columns:
        return pd.Series(dtype=float)
    dem_col = "Analog_Demand" if "Analog_Demand" in df.columns else df.columns[-1]
    df[dem_col] = pd.to_numeric(df[dem_col], errors="coerce").fillna(0)
    vel = df.groupby("Store_ID")[dem_col].mean()
    if vel.max() > 0:
        vel = vel / vel.max()
    return vel


def _demographic_fit(new_sku_attrs: dict) -> pd.Series:
    """
    Score each store's demographic alignment with the new SKU's target profile.
    Target profile is derived from SKU attributes (Price_Band, Age_Group, etc.).
    """
    sm = _store_master()
    if sm.empty or "Store_ID" not in sm.columns:
        return pd.Series(dtype=float)

    score = pd.Series(0.5, index=sm["Store_ID"].astype(str))

    price_band = str(new_sku_attrs.get("Price_Band", "") or "").lower()
    age_group  = str(new_sku_attrs.get("Age_Group",  "") or "").lower()
    organic    = new_sku_attrs.get("Organic_Flag", 0)

    num_feats = []

    # Premium SKU → higher income stores score higher
    if "Median_HH_Income_USD" in sm.columns:
        inc = sm.set_index(sm["Store_ID"].astype(str))["Median_HH_Income_USD"]
        inc_norm = (inc - inc.min()) / max(inc.max() - inc.min(), 1)
        if "premium" in price_band or "luxury" in price_band:
            num_feats.append(inc_norm)
        elif "value" in price_band or "economy" in price_band:
            num_feats.append(1 - inc_norm)
        else:
            num_feats.append(inc_norm * 0.5 + 0.25)

    # Organic → digital / urban stores score higher
    if organic and "Online_Order_Pct" in sm.columns:
        onl = sm.set_index(sm["Store_ID"].astype(str))["Online_Order_Pct"]
        onl_norm = (onl - onl.min()) / max(onl.max() - onl.min(), 1)
        num_feats.append(onl_norm)

    # Kids → higher footfall, family stores
    if "kids" in age_group and "Footfall_Daily" in sm.columns:
        foot = sm.set_index(sm["Store_ID"].astype(str))["Footfall_Daily"]
        foot_norm = (foot - foot.min()) / max(foot.max() - foot.min(), 1)
        num_feats.append(foot_norm)

    if num_feats:
        score = pd.concat(num_feats, axis=1).mean(axis=1)
        score = score.fillna(0.5)

    return score


def _cluster_affinity(new_sku_id: str) -> pd.Series:
    """
    Use cluster-level analog demand (avg weekly velocity per cluster) → normalised.
    Better clusters get higher scores for all their member stores.
    """
    af = _analog_fc()
    cl = _clusters()
    if af.empty or cl.empty:
        return pd.Series(dtype=float)

    col_new = "New_SKU_ID" if "New_SKU_ID" in af.columns else af.columns[0]
    df = af[af[col_new] == new_sku_id].copy()
    if df.empty:
        return pd.Series(dtype=float)

    dem_col = "Analog_Demand" if "Analog_Demand" in df.columns else df.columns[-1]
    df[dem_col] = pd.to_numeric(df[dem_col], errors="coerce").fillna(0)

    df = df.merge(cl[["Store_ID", "Cluster_ID"]], on="Store_ID", how="left")
    cluster_vel = df.groupby("Cluster_ID")[dem_col].mean()
    if cluster_vel.max() > 0:
        cluster_vel = cluster_vel / cluster_vel.max()

    store_cluster = cl.set_index("Store_ID")["Cluster_ID"] if "Store_ID" in cl.columns else pd.Series(dtype=str)
    affinity = store_cluster.astype(str).map(cluster_vel.to_dict()).fillna(0.5)
    return affinity.rename_axis("Store_ID")


def _category_penetration(sub_category: str) -> pd.Series:
    """
    Fraction of each store's revenue that comes from the new SKU's sub-category.
    Higher penetration → store is already a strong category store.
    """
    tx = _sales_tx()
    if tx.empty or "Store_ID" not in tx.columns or "Sub_Category" not in tx.columns:
        return pd.Series(dtype=float)

    if "Net_Sales_USD" not in tx.columns:
        return pd.Series(dtype=float)

    total   = tx.groupby("Store_ID")["Net_Sales_USD"].sum()
    cat_rev = tx[tx["Sub_Category"] == sub_category].groupby("Store_ID")["Net_Sales_USD"].sum()
    penetration = (cat_rev / total.replace(0, np.nan)).fillna(0)
    if penetration.max() > 0:
        penetration = penetration / penetration.max()
    return penetration


def _price_compatibility(new_sku_attrs: dict) -> pd.Series:
    """
    Compare new SKU's price band to the average basket value of each store.
    Better-aligned stores score higher.
    """
    sm = _store_master()
    if sm.empty or "Store_ID" not in sm.columns or "Avg_Basket_Value" not in sm.columns:
        return pd.Series(dtype=float)

    new_price = float(new_sku_attrs.get("List_Price_USD", 0) or 0)
    if new_price <= 0:
        return pd.Series(0.5, index=sm["Store_ID"].astype(str))

    basket = sm.set_index(sm["Store_ID"].astype(str))["Avg_Basket_Value"].astype(float)
    # New SKU price as fraction of basket → ideal range ~5–15%
    ratio = new_price / basket.replace(0, np.nan)
    # Score highest when ratio is in 0.05–0.15 range
    score = 1 - (ratio - 0.10).abs().clip(upper=0.15) / 0.15
    return score.fillna(0.5).clip(0, 1)


# ---------------------------------------------------------------------------
# Rollout phases
# ---------------------------------------------------------------------------
def _assign_phase(score: float) -> str:
    if score >= 0.70:
        return "Phase 1 — Immediate"
    elif score >= 0.45:
        return "Phase 2 — 4–8 Weeks"
    elif score >= 0.25:
        return "Phase 3 — 8–16 Weeks"
    else:
        return "Phase 4 — Do Not Launch"


def _velocity_tier(vel: float, p33: float, p66: float) -> str:
    if vel >= p66:
        return "High"
    elif vel >= p33:
        return "Medium"
    else:
        return "Low"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def recommend_stores(
    new_sku_id:    str,
    new_sku_attrs: dict,
    weights: dict | None = None,
) -> dict[str, Any]:
    """
    Returns:
      stores         — list of store dicts with scores and recommendation
      cluster_summary— list of cluster-level summaries
      top_stores     — list of top-10 recommended stores
      skip_stores    — list of stores to avoid
      launch_summary — high-level narrative
    """
    w = weights or {
        "analog_velocity":    0.35,
        "demographic_fit":    0.25,
        "cluster_affinity":   0.20,
        "category_penetration": 0.10,
        "price_compatibility":  0.10,
    }

    vel   = _analog_velocity(new_sku_id)
    demo  = _demographic_fit(new_sku_attrs)
    clust = _cluster_affinity(new_sku_id)
    cat   = _category_penetration(new_sku_attrs.get("Sub_Category", ""))
    price = _price_compatibility(new_sku_attrs)

    # Align indices
    sm = _store_master()
    all_stores = (
        sm["Store_ID"].astype(str).tolist()
        if not sm.empty and "Store_ID" in sm.columns
        else list(set(list(vel.index) + list(demo.index)))
    )
    idx = pd.Index(all_stores)

    def _get(s: pd.Series) -> pd.Series:
        return s.reindex(idx).fillna(0.5)

    scores = (
        w["analog_velocity"]    * _get(vel)  +
        w["demographic_fit"]    * _get(demo) +
        w["cluster_affinity"]   * _get(clust)+
        w["category_penetration"]* _get(cat) +
        w["price_compatibility"] * _get(price)
    )

    # Velocity percentiles
    p33 = float(vel.quantile(0.33)) if not vel.empty else 0.3
    p66 = float(vel.quantile(0.66)) if not vel.empty else 0.6

    cl_df = _clusters()
    cluster_map = {}
    if not cl_df.empty and "Store_ID" in cl_df.columns:
        cluster_map = cl_df.set_index("Store_ID")["Cluster_Label"].to_dict()

    store_records = []
    for store_id in all_stores:
        s_str = str(store_id)
        composite = float(scores.get(s_str, 0.5))
        v = float(vel.get(s_str, 0.0))
        store_records.append({
            "store_id":               s_str,
            "cluster_label":          cluster_map.get(store_id, cluster_map.get(s_str, "Unknown")),
            "composite_score":        round(composite, 4),
            "analog_velocity_score":  round(float(_get(vel).get(s_str, 0.5)),  4),
            "demographic_fit_score":  round(float(_get(demo).get(s_str, 0.5)), 4),
            "cluster_affinity_score": round(float(_get(clust).get(s_str, 0.5)),4),
            "category_penetration_score": round(float(_get(cat).get(s_str, 0.5)),4),
            "price_compatibility_score":  round(float(_get(price).get(s_str, 0.5)),4),
            "velocity_tier":          _velocity_tier(v, p33, p66),
            "rollout_phase":          _assign_phase(composite),
            "recommend":              composite >= 0.45,
        })

    store_records.sort(key=lambda x: x["composite_score"], reverse=True)

    top     = [s for s in store_records if s["composite_score"] >= 0.45]
    skip    = [s for s in store_records if s["composite_score"] < 0.25]

    # Cluster summary
    cluster_summary = []
    if not cl_df.empty and "Cluster_Label" in cl_df.columns:
        for _, grp_row in cl_df.drop_duplicates("Cluster_Label").iterrows():
            label = grp_row["Cluster_Label"]
            cluster_stores = cl_df[cl_df["Cluster_Label"] == label]["Store_ID"].astype(str).tolist()
            c_scores = [s["composite_score"] for s in store_records if s["store_id"] in cluster_stores]
            cluster_summary.append({
                "cluster_label":    label,
                "store_count":      len(cluster_stores),
                "avg_score":        round(float(np.mean(c_scores)) if c_scores else 0, 4),
                "recommend_count":  sum(1 for s in c_scores if s >= 0.45),
                "recommendation":   "Launch" if (np.mean(c_scores) if c_scores else 0) >= 0.45 else "Skip",
            })

    # High-level narrative
    n_recommended = len(top)
    n_total       = len(store_records)
    top_cluster   = cluster_summary[0]["cluster_label"] if cluster_summary else "Unknown"
    launch_summary = (
        f"Recommend launching in {n_recommended} of {n_total} stores. "
        f"Strongest fit in the '{top_cluster}' cluster, driven by high analog velocity and demographic alignment. "
        f"{len(skip)} stores score below threshold and are not recommended for this SKU."
    )

    return {
        "stores":          store_records,
        "cluster_summary": sorted(cluster_summary, key=lambda x: x["avg_score"], reverse=True),
        "top_stores":      top[:10],
        "skip_stores":     skip,
        "n_recommended":   n_recommended,
        "n_total":         n_total,
        "launch_summary":  launch_summary,
    }
