"""
decision_hub_service.py
=======================
All data-layer computations for the Category Decision Hub page.
Reads existing Outputs/ CSVs — no new data pipeline required.
"""

import os
import numpy as np
import pandas as pd
from pathlib import Path
from functools import lru_cache
from typing import Optional

from ..database.connection import read_table_or_csv

_SVC  = Path(__file__).resolve().parent
_PROJ = _SVC.parent.parent
_OUT  = _PROJ / "Outputs"
_RAW  = _PROJ / "Raw_Input"


# ---------------------------------------------------------------------------
# Raw loaders (cached)
# ---------------------------------------------------------------------------
@lru_cache(maxsize=1)
def _sku():
    return read_table_or_csv("sku_master", _RAW / "SKU_Master.csv")

@lru_cache(maxsize=1)
def _store():
    return read_table_or_csv("store_master", _RAW / "Store_Master.csv")

@lru_cache(maxsize=1)
def _clusters():
    return read_table_or_csv("store_clusters", _OUT / "store_clusters.csv")

@lru_cache(maxsize=1)
def _demand_raw():
    df = read_table_or_csv("weekly_demand_output", _OUT / "weekly_demand_output.csv")
    df["Quantity_Sold"]      = pd.to_numeric(df["Quantity_Sold"],      errors="coerce").fillna(0)
    df["Quantity_Available"] = pd.to_numeric(df["Quantity_Available"], errors="coerce").fillna(0)
    return df

@lru_cache(maxsize=1)
def _forecast_raw():
    df = read_table_or_csv("forecast_output", _OUT / "Forecast_Output.csv")
    for c in ["Final_Forecast","Forecast_Lower","Forecast_Upper",
              "Total_Sales","Total_Margin","List_Price_USD","Unit_Cost_USD"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)
    return df

@lru_cache(maxsize=1)
def _delist_raw():
    df = read_table_or_csv("delisting_recommendations", _OUT / "delisting_recommendations.csv")
    for c in ["Health_Score","GMROI","delist_score","Forecast_Growth_Pct"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df

@lru_cache(maxsize=1)
def _assoc_raw():
    return read_table_or_csv("association_rules", _OUT / "association_rules.csv")

@lru_cache(maxsize=1)
def _basket_raw():
    return read_table_or_csv("sku_basket_insights", _OUT / "sku_basket_insights.csv")


# ---------------------------------------------------------------------------
# Core merged frame (unfiltered, cached)
# ---------------------------------------------------------------------------
@lru_cache(maxsize=1)
def _base_frame() -> pd.DataFrame:
    """
    One row per Store_ID × SKU_ID with all computed metrics.
    """
    dm  = _demand_raw()
    fc  = _forecast_raw()
    dls = _delist_raw()

    # --- Inventory: latest available qty per store×sku ---
    last_wk = dm["Year_WK"].max()
    inv = (dm[dm["Year_WK"] == last_wk]
           .groupby(["Store_ID", "SKU_ID"])["Quantity_Available"]
           .sum()
           .reset_index(name="current_inventory"))

    # --- Historical demand per store×sku ---
    hist = (dm.groupby(["Store_ID", "SKU_ID"])
            .agg(hist_qty=("Quantity_Sold", "sum"), hist_wks=("Year_WK", "nunique"))
            .reset_index())
    hist["hist_avg_weekly"] = hist["hist_qty"] / hist["hist_wks"].replace(0, np.nan)

    # --- Forecast: aggregate 6 weeks per store×sku ---
    fc_agg = (fc.groupby(["Store_ID", "SKU_ID"])
              .agg(
                  forecast_6wk=("Final_Forecast", "sum"),
                  fc_lower_6wk=("Forecast_Lower", "sum"),
                  fc_upper_6wk=("Forecast_Upper", "sum"),
                  total_sales_6wk=("Total_Sales", "sum"),
                  total_margin_6wk=("Total_Margin", "sum"),
                  List_Price_USD=("List_Price_USD", "first"),
                  Unit_Cost_USD=("Unit_Cost_USD", "first"),
                  Sub_Category=("Sub_Category", "first"),
                  Brand=("Brand", "first"),
                  Cluster=("Cluster", "first"),
                  Geography=("Geography", "first"),
                  Region=("Region", "first"),
              )
              .reset_index())

    # --- Delist: one row per SKU (aggregate across granularities) ---
    dls_sku = (dls.groupby("SKU_ID")
               .agg(
                   Health_Score=("Health_Score", "median"),
                   GMROI=("GMROI", "median"),
                   delist_score=("delist_score", "median"),
                   Forecast_Growth_Pct=("Forecast_Growth_Pct", "median"),
                   Basket_Role=("Basket_Role", lambda x: x.mode().iloc[0] if len(x) > 0 else "Unknown"),
                   Decision=("Decision", lambda x: x.mode().iloc[0] if len(x) > 0 else "MONITOR"),
                   Recommended_Action=("Recommended_Action", "first"),
                   Recommendation_Narrative=("Recommendation_Narrative", "first"),
               )
               .reset_index())

    # --- SKU master attributes ---
    sku = _sku()[["SKU_ID", "Product_Name", "Margin_Pct"]].copy()

    # --- Merge ---
    df = (fc_agg
          .merge(inv,  on=["Store_ID", "SKU_ID"], how="left")
          .merge(hist, on=["Store_ID", "SKU_ID"], how="left")
          .merge(dls_sku, on="SKU_ID", how="left")
          .merge(sku,     on="SKU_ID", how="left"))

    df["current_inventory"] = df["current_inventory"].fillna(0)
    df["hist_avg_weekly"]   = df["hist_avg_weekly"].fillna(0)

    # --- Derived metrics ---
    df["avg_weekly_fc"] = df["forecast_6wk"] / 6
    safe_fc = df["avg_weekly_fc"].replace(0, np.nan)

    df["WoC"] = (df["current_inventory"] / safe_fc).clip(0, 52).fillna(0)
    df["Lost_Units"]   = (df["forecast_6wk"] - df["current_inventory"]).clip(lower=0)
    df["Lost_Revenue"] = df["Lost_Units"] * df["List_Price_USD"]
    df["Lost_Margin"]  = df["Lost_Units"] * (df["List_Price_USD"] - df["Unit_Cost_USD"])

    sell_denom = df["hist_qty"].fillna(0) + df["current_inventory"]
    df["Sell_Through"] = np.where(
        sell_denom > 0, df["hist_qty"].fillna(0) / sell_denom, 0
    )

    # Forecast growth from actuals vs forecast
    df["Calc_Growth_Pct"] = np.where(
        df["hist_avg_weekly"] > 0,
        (df["avg_weekly_fc"] - df["hist_avg_weekly"]) / df["hist_avg_weekly"] * 100,
        df["Forecast_Growth_Pct"].fillna(0)
    )

    # Health score to 0-100 scale
    df["Health_Score_100"] = (df["Health_Score"].fillna(0) * 100).clip(0, 100)

    # Bucket classification
    df["risk_bucket"] = _classify_buckets(df)

    return df


def _classify_buckets(df: pd.DataFrame) -> pd.Series:
    if len(df) < 5:
        return pd.Series(["Stable"] * len(df), index=df.index)

    woc   = df["WoC"]
    gp    = df["Calc_Growth_Pct"]
    ds    = df["delist_score"].fillna(df["delist_score"].median())

    low_woc   = woc.quantile(0.20)
    high_woc  = woc.quantile(0.80)
    high_gp   = gp.quantile(0.75)    # top-25% growth
    high_ds   = ds.quantile(0.75)    # top-25% delist risk

    conditions = [
        woc <= low_woc,
        woc >= high_woc,
        (gp >= high_gp) & (ds < ds.median()),
        ds >= high_ds,
    ]
    choices = ["Stock-out Risk", "Excess Inventory", "Growth Opportunity", "Delist Candidate"]
    return np.select(conditions, choices, default="Stable")


def _apply_filters(df: pd.DataFrame, store_id=None, sub_cat=None, cluster=None) -> pd.DataFrame:
    if store_id:  df = df[df["Store_ID"]   == store_id]
    if sub_cat:   df = df[df["Sub_Category"] == sub_cat]
    if cluster:   df = df[df["Cluster"]    == cluster]
    return df


# ---------------------------------------------------------------------------
# 1. KPI Header
# ---------------------------------------------------------------------------
def get_hub_kpis(store_id=None, sub_cat=None, cluster=None) -> dict:
    df = _apply_filters(_base_frame(), store_id, sub_cat, cluster)
    if df.empty:
        return {k: 0 for k in ["forecast_revenue","forecast_margin","revenue_at_risk",
                                "excess_inventory_value","delist_count","growth_opportunities"]}

    forecast_revenue    = round(float(df["total_sales_6wk"].sum()), 0)
    forecast_margin     = round(float(df["total_margin_6wk"].sum()), 0)
    revenue_at_risk     = round(float(df["Lost_Revenue"].sum()), 0)
    excess_inv_skus     = df[df["WoC"] > 12].copy()
    excess_inv_value    = round(float((excess_inv_skus["current_inventory"] * excess_inv_skus["List_Price_USD"]).sum()), 0)
    ds_thresh  = float(df["delist_score"].fillna(0).quantile(0.75))
    gp_thresh  = float(df["Calc_Growth_Pct"].quantile(0.75))
    delist_count = int(df[df["delist_score"].fillna(0) >= ds_thresh]["SKU_ID"].nunique())
    growth_opps  = int(df[(df["Calc_Growth_Pct"] >= gp_thresh) & (df["delist_score"].fillna(1) < df["delist_score"].median())]["SKU_ID"].nunique())

    return {
        "forecast_revenue":      forecast_revenue,
        "forecast_margin":       forecast_margin,
        "revenue_at_risk":       revenue_at_risk,
        "excess_inventory_value": excess_inv_value,
        "delist_count":          delist_count,
        "growth_opportunities":  growth_opps,
    }


# ---------------------------------------------------------------------------
# 2. Risk Matrix
# ---------------------------------------------------------------------------
def get_risk_matrix(store_id=None, sub_cat=None, cluster=None) -> list[dict]:
    df = _apply_filters(_base_frame(), store_id, sub_cat, cluster).copy()

    # Transfer candidates: same SKU has stockout in one store + excess in another
    woc = df["WoC"]
    low_woc  = woc.quantile(0.20) if len(woc) > 5 else woc.min()
    high_woc = woc.quantile(0.80) if len(woc) > 5 else woc.max()
    pivot_woc = df.pivot_table(index="SKU_ID", values="WoC", aggfunc=["min", "max"])
    pivot_woc.columns = ["WoC_min", "WoC_max"]
    transfer_skus = pivot_woc[(pivot_woc["WoC_min"] <= low_woc) & (pivot_woc["WoC_max"] >= high_woc)].index
    df.loc[(df["SKU_ID"].isin(transfer_skus)) & (df["risk_bucket"] == "Stable"), "risk_bucket"] = "Transfer Candidate"

    df = df[df["risk_bucket"] != "Stable"].copy()

    action_map = {
        "Stock-out Risk":       "Replenish Now",
        "Excess Inventory":     "Reduce Orders",
        "Growth Opportunity":   "Expand Assortment",
        "Delist Candidate":     "Review Delisting",
        "Transfer Candidate":   "Transfer Stock",
    }
    df["action"] = df["risk_bucket"].map(action_map).fillna("Review")
    df["financial_impact_usd"] = np.where(
        df["risk_bucket"] == "Stock-out Risk",    df["Lost_Revenue"],
        np.where(df["risk_bucket"] == "Excess Inventory",
                 df["current_inventory"] * df["List_Price_USD"], df["total_sales_6wk"])
    ).round(0)

    cols = ["SKU_ID","Product_Name","Store_ID","Sub_Category","Brand",
            "risk_bucket","action","financial_impact_usd","WoC","Lost_Revenue",
            "Calc_Growth_Pct","Health_Score_100","delist_score"]
    out = df[[c for c in cols if c in df.columns]].fillna(0)
    return out.sort_values("financial_impact_usd", ascending=False).head(200).to_dict("records")


# ---------------------------------------------------------------------------
# 3. Lost Sales
# ---------------------------------------------------------------------------
def get_lost_sales(store_id=None, sub_cat=None, top_n: int = 20) -> list[dict]:
    df = _apply_filters(_base_frame(), store_id, sub_cat)

    stockout = df[df["Lost_Units"] > 0].copy()

    agg = (stockout.groupby(["SKU_ID", "Product_Name", "Sub_Category", "Brand"])
           .agg(
               Lost_Units=("Lost_Units", "sum"),
               Lost_Revenue=("Lost_Revenue", "sum"),
               Lost_Margin=("Lost_Margin", "sum"),
               Affected_Stores=("Store_ID", "nunique"),
           )
           .reset_index()
           .sort_values("Lost_Revenue", ascending=False)
           .head(top_n))

    agg["Lost_Revenue"] = agg["Lost_Revenue"].round(0)
    agg["Lost_Margin"]  = agg["Lost_Margin"].round(0)
    agg["Lost_Units"]   = agg["Lost_Units"].round(0)
    return agg.to_dict("records")


# ---------------------------------------------------------------------------
# 4. Inventory Productivity Scatter
# ---------------------------------------------------------------------------
def get_inventory_productivity(store_id=None, sub_cat=None, cluster=None) -> list[dict]:
    df = _apply_filters(_base_frame(), store_id, sub_cat, cluster).copy()

    # Aggregate to SKU level for cleaner scatter
    agg = (df.groupby(["SKU_ID", "Product_Name", "Sub_Category", "Brand"])
           .agg(
               WoC=("WoC", "mean"),
               GMROI=("GMROI", "median"),
               Revenue=("total_sales_6wk", "sum"),
               Health_Score_100=("Health_Score_100", "mean"),
               Sell_Through=("Sell_Through", "mean"),
               delist_score=("delist_score", "median"),
               Calc_Growth_Pct=("Calc_Growth_Pct", "mean"),
           )
           .reset_index())

    agg["WoC"]     = agg["WoC"].round(1)
    agg["Revenue"] = agg["Revenue"].round(0)
    agg["GMROI"]   = agg["GMROI"].fillna(0).round(1)
    agg["Health_Score_100"] = agg["Health_Score_100"].round(1)

    # Normalise bubble size for Plotly (1-60 range)
    rev_max = agg["Revenue"].max() or 1
    agg["bubble_size"] = ((agg["Revenue"] / rev_max) * 55 + 5).round(1)

    return agg.dropna(subset=["WoC", "GMROI"]).to_dict("records")


# ---------------------------------------------------------------------------
# 5. Delist & Rationalization Hub
# ---------------------------------------------------------------------------
def get_delist_rationalization(store_id=None, sub_cat=None) -> dict:
    df = _apply_filters(_base_frame(), store_id, sub_cat)
    sku = _sku()[["SKU_ID", "Product_Name"]].copy()

    # SKU-level view (aggregate stores)
    sku_df = (df.groupby("SKU_ID")
              .agg(
                  Revenue=("total_sales_6wk", "sum"),
                  delist_score=("delist_score", "median"),
                  Health_Score_100=("Health_Score_100", "mean"),
                  Calc_Growth_Pct=("Calc_Growth_Pct", "mean"),
                  GMROI=("GMROI", "median"),
                  Basket_Role=("Basket_Role", "first"),
                  Decision=("Decision", "first"),
                  Recommended_Action=("Recommended_Action", "first"),
                  Sub_Category=("Sub_Category", "first"),
                  Brand=("Brand", "first"),
              )
              .reset_index()
              .merge(sku, on="SKU_ID", how="left"))

    sku_df["delist_score"] = sku_df["delist_score"].fillna(0)

    ds_hi  = float(sku_df["delist_score"].quantile(0.75))
    ds_med = float(sku_df["delist_score"].quantile(0.50))
    ds_lo  = float(sku_df["delist_score"].quantile(0.25))
    gp_hi  = float(sku_df["Calc_Growth_Pct"].quantile(0.75))

    def bucket(row):
        ds = row["delist_score"]
        gp = row["Calc_Growth_Pct"]
        if ds <= ds_lo:             return "Keep"
        if gp >= gp_hi and ds < ds_med: return "Grow"
        if ds >= ds_hi:             return "Delist"
        return "Watch"

    sku_df["hub_bucket"] = sku_df.apply(bucket, axis=1)

    # Insight: how many Watch/Delist contribute small % of sales
    total_rev = sku_df["Revenue"].sum() or 1
    risk_sku  = sku_df[sku_df["hub_bucket"].isin(["Delist", "Watch"])]
    risk_rev  = risk_sku["Revenue"].sum()
    risk_pct  = round(risk_rev / total_rev * 100, 1)
    insight   = (f"{len(risk_sku)} SKUs contribute only {risk_pct}% of forecast revenue"
                 f" but consume significant shelf space and working capital.")

    result = {}
    for b in ["Keep", "Grow", "Watch", "Delist"]:
        sub = sku_df[sku_df["hub_bucket"] == b].copy()
        sub = sub.sort_values("delist_score", ascending=(b in ["Keep","Grow"]))
        cols = ["SKU_ID","Product_Name","Sub_Category","Brand","delist_score",
                "Health_Score_100","Calc_Growth_Pct","GMROI","Basket_Role",
                "Revenue","Recommended_Action","Decision"]
        result[b] = sub[[c for c in cols if c in sub.columns]].fillna(0).head(30).to_dict("records")

    result["insight"] = insight
    return result


# ---------------------------------------------------------------------------
# 6. Exception Alerts
# ---------------------------------------------------------------------------
def get_exception_alerts(store_id=None, sub_cat=None, cluster=None) -> list[dict]:
    df = _apply_filters(_base_frame(), store_id, sub_cat, cluster).copy()
    df["name"] = df["Product_Name"].fillna(df["SKU_ID"]).str[:35]

    woc_low  = df["WoC"].quantile(0.20) if len(df) > 5 else df["WoC"].min()
    woc_high = df["WoC"].quantile(0.80) if len(df) > 5 else df["WoC"].max()

    alerts = []

    for _, r in df[df["WoC"] <= woc_low].nlargest(8, "Lost_Revenue").iterrows():
        alerts.append({
            "severity": "red",
            "icon": "🔴",
            "title": f"Stockout Risk – {r['name']}",
            "detail": f"Store {r['Store_ID']} · {r['WoC']:.1f} wks cover left",
            "financial": round(float(r["Lost_Revenue"]), 0),
            "sku_id": r["SKU_ID"], "store_id": r["Store_ID"],
        })

    for _, r in df[df["Calc_Growth_Pct"] > 30].nlargest(5, "Calc_Growth_Pct").iterrows():
        alerts.append({
            "severity": "orange",
            "icon": "🟠",
            "title": f"Demand Surge – {r['name']}",
            "detail": f"+{r['Calc_Growth_Pct']:.0f}% vs historical · Store {r['Store_ID']}",
            "financial": round(float(r["total_sales_6wk"]), 0),
            "sku_id": r["SKU_ID"], "store_id": r["Store_ID"],
        })

    for _, r in df[df["Calc_Growth_Pct"] < -25].nsmallest(5, "Calc_Growth_Pct").iterrows():
        alerts.append({
            "severity": "orange",
            "icon": "🟠",
            "title": f"Demand Drop – {r['name']}",
            "detail": f"{r['Calc_Growth_Pct']:.0f}% vs historical · Store {r['Store_ID']}",
            "financial": round(float(r["total_sales_6wk"]), 0),
            "sku_id": r["SKU_ID"], "store_id": r["Store_ID"],
        })

    for _, r in df[df["delist_score"].fillna(0) > 0.8].nlargest(5, "delist_score").iterrows():
        alerts.append({
            "severity": "red",
            "icon": "🔴",
            "title": f"Delist Candidate – {r['name']}",
            "detail": f"Delist score {r['delist_score']:.2f} · {r['Sub_Category']}",
            "financial": round(float(r["total_sales_6wk"]), 0),
            "sku_id": r["SKU_ID"], "store_id": r["Store_ID"],
        })

    for _, r in (df[(df["Calc_Growth_Pct"] > 20) & (df["delist_score"].fillna(1) < 0.3)]
                 .nlargest(4, "Calc_Growth_Pct").iterrows()):
        alerts.append({
            "severity": "green",
            "icon": "🟢",
            "title": f"Growth Opportunity – {r['name']}",
            "detail": f"+{r['Calc_Growth_Pct']:.0f}% growth · Health {r['Health_Score_100']:.0f}/100",
            "financial": round(float(r["total_sales_6wk"]), 0),
            "sku_id": r["SKU_ID"], "store_id": r["Store_ID"],
        })

    priority = {"red": 0, "orange": 1, "green": 2}
    alerts.sort(key=lambda a: (priority.get(a["severity"], 3), -a["financial"]))
    return alerts[:25]


# ---------------------------------------------------------------------------
# 7. Category Health Scores
# ---------------------------------------------------------------------------
def get_category_health_scores() -> list[dict]:
    df = _base_frame()

    sku_df = (df.groupby(["SKU_ID", "Sub_Category"])
              .agg(
                  Health_Score_100=("Health_Score_100", "mean"),
                  GMROI=("GMROI", "median"),
                  Sell_Through=("Sell_Through", "mean"),
                  Calc_Growth_Pct=("Calc_Growth_Pct", "mean"),
                  delist_score=("delist_score", "median"),
              )
              .reset_index())

    def norm(series, lo=None, hi=None):
        lo = lo if lo is not None else series.quantile(0.05)
        hi = hi if hi is not None else series.quantile(0.95)
        return ((series - lo) / (hi - lo + 1e-9)).clip(0, 1) * 100

    sku_df["gmroi_score"]  = norm(sku_df["GMROI"])
    sku_df["growth_score"] = norm(sku_df["Calc_Growth_Pct"], -30, 30)

    cat = (sku_df.groupby("Sub_Category")
           .agg(
               health=("Health_Score_100", "mean"),
               gmroi=("gmroi_score", "mean"),
               sell_through=("Sell_Through", "mean"),
               growth=("growth_score", "mean"),
               delist_free=("delist_score", lambda x: (x < 0.4).mean() * 100),
               sku_count=("SKU_ID", "nunique"),
           )
           .reset_index())

    cat["composite"] = (
        cat["health"]        * 0.25 +
        cat["growth"]        * 0.25 +
        cat["gmroi"]         * 0.20 +
        cat["sell_through"]  * 100 * 0.20 +
        cat["delist_free"]   * 0.10
    ).clip(0, 100).round(1)

    cat["health"]       = cat["health"].round(1)
    cat["sell_through"] = (cat["sell_through"] * 100).round(1)
    return cat.sort_values("composite", ascending=False).to_dict("records")


# ---------------------------------------------------------------------------
# 8. Forecast Fan (per SKU × Store)
# ---------------------------------------------------------------------------
def get_forecast_fan(sku_id: str, store_id: str) -> dict:
    fc = _forecast_raw()
    dm = _demand_raw()

    fc_s = fc[(fc["SKU_ID"] == sku_id) & (fc["Store_ID"] == store_id)].sort_values("Forecast_Week")
    dm_s = dm[(dm["SKU_ID"] == sku_id) & (dm["Store_ID"] == store_id)].sort_values("Year_WK")

    return {
        "actuals": dm_s[["Year_WK","Quantity_Sold"]].rename(
            columns={"Year_WK":"week","Quantity_Sold":"value"}).to_dict("records"),
        "forecast": fc_s[["Forecast_Week","Final_Forecast","Forecast_Lower","Forecast_Upper"]].rename(
            columns={"Forecast_Week":"week","Final_Forecast":"point",
                     "Forecast_Lower":"lower","Forecast_Upper":"upper"}).to_dict("records"),
    }


# ---------------------------------------------------------------------------
# 9. SKU Drilldown
# ---------------------------------------------------------------------------
def get_sku_drilldown(sku_id: str, store_id: str) -> dict:
    base = _base_frame()
    row  = base[(base["SKU_ID"] == sku_id) & (base["Store_ID"] == store_id)]
    sku  = _sku()
    dls  = _delist_raw()

    sku_meta = sku[sku["SKU_ID"] == sku_id].iloc[0].to_dict() if len(sku[sku["SKU_ID"] == sku_id]) else {}
    fan      = get_forecast_fan(sku_id, store_id)

    dls_row = dls[dls["SKU_ID"] == sku_id].head(1)
    dls_dict = dls_row.iloc[0].to_dict() if len(dls_row) else {}

    metrics = {}
    if len(row):
        r = row.iloc[0]
        metrics = {
            "WoC":              round(float(r["WoC"]), 1),
            "GMROI":            round(float(r["GMROI"]) if not pd.isna(r["GMROI"]) else 0, 1),
            "Sell_Through":     round(float(r["Sell_Through"]) * 100, 1),
            "forecast_6wk":     round(float(r["forecast_6wk"]), 0),
            "total_sales_6wk":  round(float(r["total_sales_6wk"]), 0),
            "total_margin_6wk": round(float(r["total_margin_6wk"]), 0),
            "Lost_Revenue":     round(float(r["Lost_Revenue"]), 0),
            "Calc_Growth_Pct":  round(float(r["Calc_Growth_Pct"]), 1),
            "Health_Score_100": round(float(r["Health_Score_100"]), 0),
            "delist_score":     round(float(r["delist_score"]) if not pd.isna(r["delist_score"]) else 0, 3),
            "risk_bucket":      r["risk_bucket"],
            "Basket_Role":      r.get("Basket_Role", "Unknown"),
            "Decision":         r.get("Decision", "MONITOR"),
        }

    return {
        "sku_id":   sku_id,
        "store_id": store_id,
        "sku_meta": {k: str(v) for k, v in sku_meta.items()},
        "metrics":  metrics,
        "fan":      fan,
        "narrative": str(dls_dict.get("Recommendation_Narrative", "")),
        "action":    str(dls_dict.get("Recommended_Action", "")),
    }


# ---------------------------------------------------------------------------
# 10. Copilot Context Builder (used by llm_service)
# ---------------------------------------------------------------------------
def build_copilot_context(store_id=None, sub_cat=None, cluster=None) -> dict:
    kpis    = get_hub_kpis(store_id, sub_cat, cluster)
    alerts  = get_exception_alerts(store_id, sub_cat, cluster)
    lost    = get_lost_sales(store_id, sub_cat, top_n=5)
    matrix  = get_risk_matrix(store_id, sub_cat, cluster)
    health  = get_category_health_scores()

    red_alerts    = [a for a in alerts if a["severity"] == "red"][:5]
    growth_opps   = [r for r in matrix if r["risk_bucket"] == "Growth Opportunity"][:3]
    delist_cands  = [r for r in matrix if r["risk_bucket"] == "Delist Candidate"][:3]
    stockout_risk = [r for r in matrix if r["risk_bucket"] == "Stock-out Risk"][:3]

    def _trim(rows, keys):
        return [{k: r.get(k) for k in keys} for r in rows]

    return {
        "summary_kpis": kpis,
        "top_stockout_risk": _trim(stockout_risk, ["SKU_ID","Product_Name","Store_ID","WoC","Lost_Revenue"]),
        "top_lost_sales":    _trim(lost, ["SKU_ID","Product_Name","Lost_Revenue","Lost_Units","Affected_Stores"]),
        "top_growth_opps":   _trim(growth_opps, ["SKU_ID","Product_Name","Store_ID","Calc_Growth_Pct","total_sales_6wk"]),
        "top_delist_cands":  _trim(delist_cands, ["SKU_ID","Product_Name","Store_ID","delist_score"]),
        "urgent_alerts":     _trim(red_alerts, ["title","detail","financial"]),
        "category_health":   health[:5],
        "filters_applied":   {"store_id": store_id, "sub_cat": sub_cat, "cluster": cluster},
    }
