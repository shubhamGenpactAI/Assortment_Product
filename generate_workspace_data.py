"""
generate_workspace_data.py
--------------------------
Reads all Outputs/ and Raw_Input/ CSVs and produces a single compact JSON
file consumed by the Category Intelligence Workspace React app.

Run from the project root:
    python generate_workspace_data.py

Output: Frontend/public/data/assortment_data.json
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).parent
OUTPUTS      = PROJECT_ROOT / "Outputs"
RAW_INPUT    = PROJECT_ROOT / "Raw_Input"
PUBLIC_DATA  = PROJECT_ROOT / "Frontend" / "public" / "data"
OUT_FILE     = PUBLIC_DATA / "assortment_data.json"

PUBLIC_DATA.mkdir(parents=True, exist_ok=True)


# ── helpers ───────────────────────────────────────────────────────────────────

def load(path: Path, **kw) -> pd.DataFrame:
    if not path.exists():
        print(f"  [SKIP] {path.name} not found")
        return pd.DataFrame()
    df = pd.read_csv(path, **kw)
    print(f"  [OK]   {path.name}: {len(df):,} rows")
    return df


def jval(v):
    """Convert any value to a JSON-safe Python scalar."""
    if v is None:
        return None
    if isinstance(v, float) and (np.isnan(v) or np.isinf(v)):
        return None
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        return round(float(v), 6)
    if isinstance(v, np.bool_):
        return bool(v)
    return v


def to_records(df: pd.DataFrame) -> list:
    return [{k: jval(v) for k, v in row.items()} for row in df.to_dict("records")]


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    print("Generating workspace data …")

    recs       = load(OUTPUTS   / "delisting_recommendations.csv")
    transfer   = load(OUTPUTS   / "demand_transfer_matrix.csv")
    basket     = load(OUTPUTS   / "sku_basket_insights.csv")
    weekly     = load(OUTPUTS   / "weekly_demand_output.csv")
    forecast   = load(OUTPUTS   / "Forecast_Output.csv")
    clusters   = load(OUTPUTS   / "store_clusters.csv")
    sku_master = load(RAW_INPUT / "SKU_Master.csv")
    sales      = load(RAW_INPUT / "Sales_Tx.csv")

    # ── SKU master index ──────────────────────────────────────────────────────
    sku_info: dict = {}
    if not sku_master.empty and "SKU_ID" in sku_master.columns:
        for _, row in sku_master.iterrows():
            sku_info[str(row["SKU_ID"])] = {k: jval(v) for k, v in row.items()}

    # ── Historical demand → by SKU, aggregated to CALENDAR MONTH ──────────────
    # The Category Intelligence trend chart shows history at MONTHLY grain across
    # the full 12-month window (Jun'2025 .. May'2026), even though the underlying
    # pipeline is weekly. Aggregating straight from Sales_Tx by calendar month
    # gives 12 clean, evenly-spaced buckets (a week→month mapping would smear
    # ISO weeks that straddle a month boundary). Labels are non-date-like
    # ("Jun'25") so the chart never mis-parses them as dates.
    # Key stays `weeklyDemand` and point shape {w, q} for frontend compatibility.
    HIST_START = pd.Timestamp("2025-06-01")
    HIST_END   = pd.Timestamp("2026-05-31")
    weekly_by_sku: dict = {}
    if not sales.empty and {"SKU_ID", "Date", "Units_Sold"} <= set(sales.columns):
        s = sales.copy()
        s["Date"] = pd.to_datetime(s["Date"], errors="coerce")
        s = s[(s["Date"] >= HIST_START) & (s["Date"] <= HIST_END)].dropna(subset=["Date"])
        s["Units_Sold"] = pd.to_numeric(s["Units_Sold"], errors="coerce").fillna(0)
        s["_month"] = s["Date"].dt.to_period("M")

        # Canonical ordered month index (12 months) so every SKU's series is
        # calendar-continuous — missing months are zero-filled, not dropped.
        month_index = pd.period_range(HIST_START, HIST_END, freq="M")
        month_label = {m: f"{m.strftime('%b')}'{m.strftime('%y')}" for m in month_index}

        grp = s.groupby(["SKU_ID", "_month"])["Units_Sold"].sum()
        for sku_id, g in grp.groupby(level=0):
            by_month = g.droplevel(0).reindex(month_index, fill_value=0)
            weekly_by_sku[str(sku_id)] = [
                {"w": month_label[m], "q": jval(by_month.loc[m])}
                for m in month_index
            ]

    # ── Forecast → by SKU: WEEKLY, next 6 weeks (from ~Jun'2026) ─────────────
    FORECAST_WEEKS = 6

    def _wk_label(year_wk: str) -> str:
        """'2026-23' -> \"W23'26\" (non-date-like, categorical-safe)."""
        txt = str(year_wk)
        if "-" in txt:
            yr, wk = txt.split("-", 1)
            return f"W{int(wk)}'{yr[-2:]}"
        return txt

    # ── Forecast → by SKU (global aggregate across stores) ───────────────────
    forecast_by_sku: dict = {}
    fc_value_cols = [c for c in ["Final_Forecast", "Forecast_Lower", "Forecast_Upper",
                                  "Total_Sales", "Total_Margin"]
                     if c in forecast.columns]
    if not forecast.empty and "SKU_ID" in forecast.columns and "Forecast_Week" in forecast.columns:
        if fc_value_cols:
            grp = forecast.groupby(["SKU_ID", "Forecast_Week"])[fc_value_cols].sum().reset_index()
            for sku_id, g in grp.groupby("SKU_ID"):
                # First 5 forecast weeks only (chronological).
                g = g.sort_values("Forecast_Week").head(FORECAST_WEEKS)
                forecast_by_sku[str(sku_id)] = [
                    {
                        "w":    _wk_label(r["Forecast_Week"]),
                        "fc":   jval(r.get("Final_Forecast")),
                        "lo":   jval(r.get("Forecast_Lower")),
                        "hi":   jval(r.get("Forecast_Upper")),
                        "sales":  jval(r.get("Total_Sales")),
                        "margin": jval(r.get("Total_Margin")),
                    }
                    for _, r in g.iterrows()
                ]

    # ── Basket insights index ─────────────────────────────────────────────────
    basket_by_sku: dict = {}
    if not basket.empty and "SKU_ID" in basket.columns:
        for _, row in basket.iterrows():
            basket_by_sku[str(row["SKU_ID"])] = {k: jval(v) for k, v in row.items()}

    # ── Demand transfer matrix → by from_sku, top 5 candidates ───────────────
    transfer_by_sku: dict = {}
    if not transfer.empty and "from_sku" in transfer.columns:
        sort_col = "transfer_confidence" if "transfer_confidence" in transfer.columns else transfer.columns[0]
        for from_sku, g in transfer.groupby("from_sku"):
            transfer_by_sku[str(from_sku)] = to_records(
                g.sort_values(sort_col, ascending=False).head(5)
            )

    # ── Summary stats (Global level) ──────────────────────────────────────────
    global_recs = pd.DataFrame()
    if not recs.empty and "granularity_level" in recs.columns:
        global_recs = recs[recs["granularity_level"] == "Global"].copy()

    def vcounts(df: pd.DataFrame, col: str) -> dict:
        if col in df.columns:
            return df[col].value_counts().to_dict()
        return {}

    def col_mean(df: pd.DataFrame, col: str):
        if col in df.columns:
            return jval(df[col].mean())
        return None

    summary = {
        "totalSKUs":        int(len(global_recs)) if not global_recs.empty else 0,
        "decisions":        vcounts(global_recs, "Decision"),
        "healthBands":      vcounts(global_recs, "Health_Band"),
        "delistBands":      vcounts(global_recs, "Delist_Band"),
        "forecastBands":    vcounts(global_recs, "Forecast_Band"),
        "basketRoles":      vcounts(global_recs, "Basket_Role"),
        "avgHealth":        col_mean(global_recs, "Health_Score"),
        "avgGMROI":         col_mean(global_recs, "GMROI"),
        "avgForecastGrowth":col_mean(global_recs, "Forecast_Growth_Pct"),
        "avgSentiment":     col_mean(global_recs, "SentimentIndex"),
        "avgMarketStrength":col_mean(global_recs, "MarketStrengthIndex"),
        "totalRevenue":     jval(global_recs["total_revenue"].sum()) if "total_revenue" in global_recs.columns else None,
        "totalMargin":      jval(global_recs["total_margin"].sum()) if "total_margin" in global_recs.columns else None,
    }

    # ── Pack recommendations ──────────────────────────────────────────────────
    print(f"  Packing {len(recs):,} recommendation rows …")
    recs_list = to_records(recs)

    # ── Write JSON ────────────────────────────────────────────────────────────
    payload = {
        "meta":           {"version": "2.0", "rows": len(recs_list)},
        "summary":        summary,
        "recommendations": recs_list,
        "weeklyDemand":   weekly_by_sku,
        "forecastData":   forecast_by_sku,
        "basketInsights": basket_by_sku,
        "transferMatrix": transfer_by_sku,
        "skuMaster":      sku_info,
        "storeClusters":  to_records(clusters) if not clusters.empty else [],
    }

    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))

    size_mb = OUT_FILE.stat().st_size / 1024 / 1024
    print(f"\n[OK] {OUT_FILE}")
    print(f"     Size: {size_mb:.2f} MB")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        raise
