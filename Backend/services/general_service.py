"""
general_service.py
==================
Loads and processes all non-forecast CSV files for the remaining dashboard pages.
"""

import pandas as pd
import numpy as np
from pathlib import Path
from functools import lru_cache
from typing import Any

_SVC  = Path(__file__).resolve().parent
_PROJ = _SVC.parent.parent           # Assortment/
_OUT  = _PROJ / "Outputs"
_RAW  = _PROJ / "Raw_Input"


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------
@lru_cache(maxsize=1)
def _sales():     return pd.read_csv(_RAW / "Sales_Tx.csv")
@lru_cache(maxsize=1)
def _sku():       return pd.read_csv(_RAW / "SKU_Master.csv")
@lru_cache(maxsize=1)
def _store():     return pd.read_csv(_RAW / "Store_Master.csv")
@lru_cache(maxsize=1)
def _delist():    return pd.read_csv(_OUT / "delisting_recommendations.csv")
@lru_cache(maxsize=1)
def _assoc():     return pd.read_csv(_OUT / "association_rules.csv")
@lru_cache(maxsize=1)
def _basket():    return pd.read_csv(_OUT / "sku_basket_insights.csv")
@lru_cache(maxsize=1)
def _sim():       return pd.read_csv(_OUT / "new_sku_similarity_scores.csv")
@lru_cache(maxsize=1)
def _clusters():  return pd.read_csv(_OUT / "store_clusters.csv")
@lru_cache(maxsize=1)
def _demand():    return pd.read_csv(_OUT / "weekly_demand_output.csv")
@lru_cache(maxsize=1)
def _forecast():
    df = pd.read_csv(_OUT / "Forecast_Output.csv")
    df["Final_Forecast"] = pd.to_numeric(df["Final_Forecast"], errors="coerce").fillna(0)
    return df


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------
def get_dashboard_kpis() -> dict:
    fc   = _forecast()
    sku  = _sku()
    dls  = _delist()
    asc  = _assoc()
    clus = _clusters()

    n_stores   = fc["Store_ID"].nunique() if "Store_ID" in fc.columns else 0
    n_skus     = sku["SKU_ID"].nunique() if sku is not None else 0
    total_fc   = round(float(fc["Final_Forecast"].sum()), 0)
    n_delist   = int(dls[dls["recommendation"].str.contains("Delist", case=False, na=False)]["SKU_ID"].nunique()) \
                 if "recommendation" in dls.columns else 0
    top_lift   = round(float(asc["lift"].max()), 2) if "lift" in asc.columns else 0.0

    return {
        "stores":           n_stores,
        "active_skus":      n_skus,
        "forecast_6wk":     total_fc,
        "delist_candidates":n_delist,
        "top_basket_lift":  top_lift,
    }


def get_manager_recommendations() -> list[dict]:
    fc   = _forecast()
    dm   = _demand()
    dls  = _delist()
    asc  = _assoc()
    sim  = _sim()
    sku  = _sku()

    cards = []

    # Card 1: Product Optimization
    try:
        fc_agg = fc.groupby("SKU_ID")["Final_Forecast"].mean().reset_index(name="FC_Avg")
        dm_num = dm.copy(); dm_num["Quantity_Sold"] = pd.to_numeric(dm_num["Quantity_Sold"], errors="coerce").fillna(0)
        dm_agg = dm_num.groupby("SKU_ID")["Quantity_Sold"].mean().reset_index(name="DM_Avg")
        mg = fc_agg.merge(dm_agg, on="SKU_ID")
        mg = mg[mg["DM_Avg"] > 0].copy()
        mg["Growth"] = (mg["FC_Avg"] - mg["DM_Avg"]) / mg["DM_Avg"] * 100
        best = mg.nlargest(1, "FC_Avg").iloc[0]
        nm_row = sku[sku["SKU_ID"] == best["SKU_ID"]][["SKU_ID", "Product_Name"]].head(1)
        name = nm_row["Product_Name"].values[0][:30] if len(nm_row) else best["SKU_ID"]
        cards.append({"icon": "📈", "title": "Product Optimization",
                      "body": f"{name}", "badge": f"{best['Growth']:+.1f}% forecast growth",
                      "badge_type": "green" if best["Growth"] >= 0 else "red",
                      "action": "View SKU →"})
    except Exception:
        cards.append({"icon": "📈", "title": "Product Optimization", "body": "No data", "badge": "", "badge_type": "gray", "action": ""})

    # Card 2: Cross-Sell
    try:
        top = asc.nlargest(1, "lift").iloc[0]
        ant = top["antecedent_sku"]; con = top["consequent_sku"]
        def sname(s):
            r = sku[sku["SKU_ID"] == s]["Product_Name"].values
            return r[0][:22] if len(r) else s
        cards.append({"icon": "🔗", "title": "Cross-Sell Opportunity",
                      "body": f"{sname(ant)} + {sname(con)}",
                      "badge": f"Lift {top['lift']:.1f}x", "badge_type": "blue", "action": "View Basket →"})
    except Exception:
        cards.append({"icon": "🔗", "title": "Cross-Sell Opportunity", "body": "No data", "badge": "", "badge_type": "gray", "action": ""})

    # Card 3: New SKU
    try:
        top_sim = sim.nlargest(1, "Final_Similarity_Score").iloc[0]
        new_id  = str(top_sim.get("New_SKU_ID", "NEW"))
        exist   = str(top_sim.get("Existing_Product_Name", top_sim.get("Existing_SKU_ID", "")))[:24]
        score   = float(top_sim.get("Final_Similarity_Score", 0))
        cards.append({"icon": "✨", "title": "New SKU Opportunity",
                      "body": f"Analog for {new_id}: {exist}",
                      "badge": f"Similarity {score:.0%}", "badge_type": "blue", "action": "Score New SKU →"})
    except Exception:
        cards.append({"icon": "✨", "title": "New SKU Opportunity", "body": "No data", "badge": "", "badge_type": "gray", "action": ""})

    # Card 4: Risk Alerts
    try:
        top_risk = dls[dls["recommendation"].str.contains("Delist", case=False, na=False)].nlargest(2, "delist_score") \
                   if "recommendation" in dls.columns else dls.head(2)
        lines = []
        for _, r in top_risk.iterrows():
            nm_r = sku[sku["SKU_ID"] == r["SKU_ID"]]["Product_Name"].values
            nm   = nm_r[0][:24] if len(nm_r) else r["SKU_ID"]
            lines.append(f"⚠ {nm} — Score {r.get('delist_score', 0):.2f}")
        cards.append({"icon": "🚨", "title": "Risk Alerts", "body": "\n".join(lines),
                      "badge": "ALERT", "badge_type": "red", "action": "View Risk →"})
    except Exception:
        cards.append({"icon": "🚨", "title": "Risk Alerts", "body": "No data", "badge": "", "badge_type": "gray", "action": ""})

    return cards


def get_abc_data(store_id: str | None = None, sub_cat: str | None = None) -> dict:
    df = _sales().copy()
    if store_id: df = df[df["Store_ID"] == store_id]
    if sub_cat and "Sub_Category" in df.columns: df = df[df["Sub_Category"] == sub_cat]
    if df.empty or "ABC_Class" not in df.columns: return {"bars": []}
    abc = df.groupby("ABC_Class").agg(Revenue=("Net_Sales_USD","sum"),SKUs=("SKU_ID","nunique")).reset_index()
    total = abc["Revenue"].sum()
    abc["Rev_Pct"] = (abc["Revenue"] / total * 100).round(1)
    abc["Cum_Rev"] = abc["Rev_Pct"].cumsum().round(1)
    return {"bars": abc.to_dict("records")}


def get_basket_top_pairs(n: int = 8) -> list[dict]:
    asc = _assoc().copy()
    sku = _sku()
    def nm(s):
        r = sku[sku["SKU_ID"]==s]["Product_Name"].values
        return r[0][:26] if len(r) else s
    top = asc.nlargest(n, "lift").copy()
    top["ant_name"] = top["antecedent_sku"].apply(nm)
    top["con_name"] = top["consequent_sku"].apply(nm)
    top["pair"]     = top["ant_name"] + " → " + top["con_name"]
    top["lift"]     = top["lift"].round(2)
    top["confidence"] = top["confidence"].round(3)
    return top[["pair","lift","confidence","antecedent_sku","consequent_sku"]].to_dict("records")


def get_sales_trend(store_id: str | None = None, sub_cat: str | None = None) -> dict:
    dm  = _demand().copy()
    fc  = _forecast().copy()
    sku = _sku()
    dm["Quantity_Sold"] = pd.to_numeric(dm["Quantity_Sold"], errors="coerce").fillna(0)
    if store_id:
        dm = dm[dm["Store_ID"] == store_id]
        fc = fc[fc["Store_ID"] == store_id]
    if sub_cat and sku is not None and "Sub_Category" in sku.columns:
        sub_skus = sku[sku["Sub_Category"] == sub_cat]["SKU_ID"].unique()
        dm = dm[dm["SKU_ID"].isin(sub_skus)]
        fc = fc[fc["SKU_ID"].isin(sub_skus)]
    hist = dm.groupby("Year_WK")["Quantity_Sold"].sum().reset_index().sort_values("Year_WK")
    fc_w = fc.groupby("Forecast_Week")["Final_Forecast"].sum().reset_index().sort_values("Forecast_Week")
    return {
        "actuals":  hist.rename(columns={"Year_WK":"week","Quantity_Sold":"value"}).to_dict("records"),
        "forecast": fc_w.rename(columns={"Forecast_Week":"week","Final_Forecast":"value"}).to_dict("records"),
    }


def get_store_ranking() -> list[dict]:
    fc   = _forecast().copy()
    clus = _clusters()
    sf = fc.groupby("Store_ID")["Final_Forecast"].sum().reset_index(name="FC_Total")
    if clus is not None and "Cluster_Label" in clus.columns:
        sf = sf.merge(clus[["Store_ID","Cluster_Label"]], on="Store_ID", how="left")
        sf["label"] = sf["Store_ID"] + " · " + sf["Cluster_Label"].fillna("")
    else:
        sf["label"] = sf["Store_ID"]
    sf = sf.sort_values("FC_Total", ascending=False).round(0)
    return sf[["label","FC_Total"]].to_dict("records")


# ---------------------------------------------------------------------------
# SKU Performance
# ---------------------------------------------------------------------------
def get_sku_performance(store_id: str) -> list[dict]:
    dm   = _demand().copy()
    fc   = _forecast().copy()
    sku  = _sku()
    dm["Quantity_Sold"] = pd.to_numeric(dm["Quantity_Sold"], errors="coerce").fillna(0)
    fc["Final_Forecast"] = pd.to_numeric(fc["Final_Forecast"], errors="coerce").fillna(0)

    dm_s = dm[dm["Store_ID"] == store_id]
    fc_s = fc[fc["Store_ID"] == store_id]

    hist = dm_s.groupby("SKU_ID").agg(
        Hist_Qty=("Quantity_Sold","sum"),
        Hist_Wks=("Year_WK","nunique")).reset_index()
    hist["Hist_Avg"] = (hist["Hist_Qty"] / hist["Hist_Wks"].replace(0, np.nan)).round(1)

    fcsm = fc_s.groupby("SKU_ID").agg(
        FC_Qty=("Final_Forecast","sum"),
        FC_Wks=("Forecast_Week","nunique")).reset_index()
    fcsm["FC_Avg"] = (fcsm["FC_Qty"] / fcsm["FC_Wks"].replace(0, np.nan)).round(1)

    summary = fcsm.merge(hist, on="SKU_ID", how="outer").fillna(0)
    summary["Growth_Pct"] = np.where(
        summary["Hist_Avg"] > 0,
        ((summary["FC_Avg"] - summary["Hist_Avg"]) / summary["Hist_Avg"] * 100).round(1),
        0)

    # Demand tier
    if summary["FC_Qty"].nunique() > 1:
        hi = summary["FC_Qty"].quantile(0.66)
        lo = summary["FC_Qty"].quantile(0.33)
        summary["Demand_Tier"] = np.where(summary["FC_Qty"] >= hi, "High",
                                  np.where(summary["FC_Qty"] <= lo, "Low", "Medium"))
    else:
        summary["Demand_Tier"] = "Medium"

    # Merge SKU master
    if sku is not None:
        keep = [c for c in ["SKU_ID","Product_Name","Brand","Sub_Category","Margin_Pct"] if c in sku.columns]
        summary = summary.merge(sku[keep], on="SKU_ID", how="left")

    summary = summary.sort_values("FC_Qty", ascending=False).reset_index(drop=True)
    summary["Rank"] = range(1, len(summary)+1)

    cols = [c for c in ["Rank","SKU_ID","Product_Name","Brand","Sub_Category",
                         "Hist_Qty","FC_Qty","Growth_Pct","Demand_Tier","Margin_Pct"] if c in summary.columns]
    return summary[cols].round(2).to_dict("records")


def get_brand_share(store_id: str) -> list[dict]:
    fc  = _forecast().copy()
    fc["Final_Forecast"] = pd.to_numeric(fc["Final_Forecast"], errors="coerce").fillna(0)
    fc_s = fc[fc["Store_ID"] == store_id] if store_id else fc
    if "Brand" not in fc_s.columns: return []
    bw = fc_s.groupby("Brand")["Final_Forecast"].sum().reset_index().sort_values("Final_Forecast", ascending=False)
    return bw.rename(columns={"Brand":"name","Final_Forecast":"value"}).to_dict("records")


def get_store_list() -> list[str]:
    fc = _forecast()
    return sorted(fc["Store_ID"].dropna().unique().tolist())


# ---------------------------------------------------------------------------
# Assortment Recommendations
# ---------------------------------------------------------------------------
MARGIN_LOW = 25.0
GROWTH_STRONG = 15.0

def _recommend(tier, growth, margin):
    if tier == "High" and growth >= GROWTH_STRONG:
        return "Expand", f"Top-tier demand + strong growth ({growth:.0f}%)."
    if tier == "High" and growth >= 0:
        return "Keep", f"High forecast demand, positive growth ({growth:.0f}%)."
    if tier == "Low" and growth < 0 and (pd.isna(margin) or margin < MARGIN_LOW):
        return "Delist", f"Low demand, negative growth, low margin."
    return "Watch", f"Medium/uncertain demand (tier={tier}, growth={growth:.0f}%)."


def get_assortment_recs(store_id: str) -> list[dict]:
    rows = get_sku_performance(store_id)
    result = []
    for r in rows:
        tier   = r.get("Demand_Tier", "Medium")
        growth = float(r.get("Growth_Pct", 0))
        margin = r.get("Margin_Pct")
        rec, reason = _recommend(tier, growth, margin if margin else float("nan"))
        result.append({**r, "Recommendation": rec, "Reason": reason})
    return result


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

    show_cols = [c for c in ["SKU_ID","Sub_Category","ABC_Class","granularity_level",
                              "granularity_value","total_revenue","total_margin",
                              "delist_score","recommendation","nl_summary"] if c in df.columns]
    top50 = df.nlargest(50, "delist_score") if "delist_score" in df.columns else df.head(50)

    scatter = []
    if {"delist_score","total_revenue"}.issubset(df.columns):
        sku = _sku()
        uniq = df.drop_duplicates("SKU_ID").copy()
        if sku is not None and "Product_Name" in sku.columns:
            uniq = uniq.merge(sku[["SKU_ID","Product_Name"]], on="SKU_ID", how="left")
            uniq["label"] = uniq["Product_Name"].fillna(uniq["SKU_ID"]).str[:20]
        else:
            uniq["label"] = uniq["SKU_ID"]
        scatter = uniq[["label","total_revenue","delist_score","recommendation"]].fillna(0).to_dict("records")

    counts = {}
    if "recommendation" in df.columns:
        counts = df.drop_duplicates("SKU_ID")["recommendation"].value_counts().to_dict()

    return {
        "filter_options": filters,
        "counts": counts,
        "scatter": scatter,
        "table": top50[show_cols].fillna("").to_dict("records"),
    }


# ---------------------------------------------------------------------------
# Data Quality
# ---------------------------------------------------------------------------
def get_data_quality() -> list[dict]:
    files = {
        "Forecast_Output.csv":       (_OUT / "Forecast_Output.csv",        ["Forecast_Week","Final_Forecast","Store_ID","SKU_ID"]),
        "weekly_demand_output.csv":  (_OUT / "weekly_demand_output.csv",   ["Year_WK","Quantity_Sold","Store_ID","SKU_ID"]),
        "SKU_Master.csv":            (_RAW / "SKU_Master.csv",             ["SKU_ID","Product_Name","Brand"]),
        "Store_Master.csv":          (_RAW / "Store_Master.csv",           ["Store_ID"]),
        "Sales_Tx.csv":              (_RAW / "Sales_Tx.csv",               ["SKU_ID","Store_ID","ABC_Class","Net_Sales_USD"]),
        "delisting_recommendations.csv": (_OUT / "delisting_recommendations.csv", ["SKU_ID","delist_score","recommendation"]),
        "association_rules.csv":     (_OUT / "association_rules.csv",      ["antecedent_sku","consequent_sku","lift"]),
        "sku_basket_insights.csv":   (_OUT / "sku_basket_insights.csv",    ["SKU_ID"]),
        "new_sku_similarity_scores.csv": (_OUT / "new_sku_similarity_scores.csv", ["Existing_SKU_ID","Final_Similarity_Score"]),
        "store_clusters.csv":        (_OUT / "store_clusters.csv",         ["Store_ID","Cluster_Label"]),
    }
    rows = []
    for fname, (path, req_cols) in files.items():
        if not path.exists():
            rows.append({"File": fname, "Rows": 0, "Columns": 0, "Missing_Columns": "FILE NOT FOUND", "Status": "❌ Missing"})
            continue
        df = pd.read_csv(path)
        missing = [c for c in req_cols if c not in df.columns]
        rows.append({
            "File": fname, "Rows": len(df), "Columns": df.shape[1],
            "Missing_Columns": ", ".join(missing) or "—",
            "Status": "⚠️ Cols missing" if missing else "✅ OK",
        })
    return rows


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
    sim  = _sim()
    dm   = _demand()
    if sim is None or dm is None: return []
    dm = dm.copy(); dm["Quantity_Sold"] = pd.to_numeric(dm["Quantity_Sold"], errors="coerce").fillna(0)
    top = sim[sim["New_SKU_ID"] == new_sku_id].nlargest(5, "Final_Similarity_Score") if "New_SKU_ID" in sim.columns else sim.head(5)
    if top.empty: return []
    wsum = top["Final_Similarity_Score"].sum()
    if wsum <= 0: return []
    wmap = dict(zip(top["Existing_SKU_ID"], top["Final_Similarity_Score"] / wsum))
    d = dm[dm["SKU_ID"].isin(wmap)].copy()
    d["w"]    = d["SKU_ID"].map(wmap)
    d["wqty"] = d["w"] * d["Quantity_Sold"]
    g = d.groupby("Year_WK").agg(wsum=("wqty","sum"), pw=("w","sum")).reset_index()
    g["Analog_Demand"] = (g["wsum"] / g["pw"]).round(1)
    return g.rename(columns={"Year_WK":"week"})[["week","Analog_Demand"]].sort_values("week").to_dict("records")
