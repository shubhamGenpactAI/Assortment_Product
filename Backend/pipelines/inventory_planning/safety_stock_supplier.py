"""
safety_stock_supplier.py
=========================
Computes two new per Store_ID x SKU_ID metrics that do not exist anywhere
else in the pipeline yet, feeding the Watchdog agent's stock-out Root Cause
Analysis (RCA):

  * Safety_Stock_Units / Safety_Stock_Gap_Units — classic max/average
    safety-stock formula:
        Safety_Stock = (Max_Daily_Sales * Max_Lead_Time_Days)
                      - (Avg_Daily_Sales * Avg_Lead_Time_Days)
    computed per Store_ID x SKU_ID over a trailing 3-month window, so a
    stock-out can be attributed to an under-sized buffer relative to demand
    AND lead-time volatility (not demand volatility alone).
  * Supplier_Confidence_Score — a weighted blend of Sell-Through, Margin,
    and a derived Supplier Fill Rate (3-month trailing average).
  * Supplier_Rating — A/B/C tier bucketed from Supplier_Confidence_Score's
    percentile rank (top 30% = A, middle 40% = B, bottom 30% = C).

No raw input file carries a Safety_Stock, Lead_Time, or Supplier Fill Rate /
On-Time-Delivery column, so every one of those is DERIVED here from columns
that do exist (Quantity_Sold / Quantity_Available in weekly_demand_output.csv,
Supplier / Margin_Pct in SKU_Master.csv), or randomly generated (Lead_Time_Days
— see LEAD_TIME_MIN_DAYS/LEAD_TIME_MAX_DAYS below). See the "ASSUMPTIONS"
section below — these are clearly-documented proxies, not measured supplier
data.

Outputs:
  Outputs/safety_stock_supplier_scores.csv   (also loaded into PostgreSQL
  table "safety_stock_supplier_scores" when the DB is reachable)

Run:
    python safety_stock_supplier.py
"""

import logging
import os
import sys

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# DB import (try; fall back gracefully if not available) — mirrors the
# convention used by forecasting.py / basket_analysis.py.
# ---------------------------------------------------------------------------
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)
try:
    from database.connection import read_table_or_csv as _db_read, get_engine
    _DB_AVAILABLE = True
except ImportError:
    _DB_AVAILABLE = False

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(levelname)-7s  %(message)s")
log = logging.getLogger(__name__)

# =============================================================================
# CONFIGURATION
# =============================================================================
BASE_DIR     = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR  = os.path.dirname(os.path.dirname(os.path.dirname(BASE_DIR)))
OUTPUTS_DIR  = os.path.join(PROJECT_DIR, "Outputs")
RAW_DIR      = os.path.join(PROJECT_DIR, "Raw_Input")
os.makedirs(OUTPUTS_DIR, exist_ok=True)

DEMAND_CSV    = os.path.join(OUTPUTS_DIR, "weekly_demand_output.csv")
SKU_CSV       = os.path.join(RAW_DIR, "SKU_Master.csv")
INVENTORY_CSV = os.path.join(RAW_DIR, "Inventory_Report.csv")
OUTPUT_CSV    = os.path.join(OUTPUTS_DIR, "safety_stock_supplier_scores.csv")
PG_TABLE      = "safety_stock_supplier_scores"

# --- ASSUMPTIONS (no real data exists for these — documented proxies) ------
# No supplier lead-time is captured anywhere in Raw_Input. A per Store_ID x
# SKU_ID x Year_WK lead time is randomly generated (fixed seed -> reproducible
# across re-runs) within a plausible FMCG replenishment range; override here
# if real per-supplier lead-time data becomes available.
LEAD_TIME_MIN_DAYS = 3
LEAD_TIME_MAX_DAYS = 21
LEAD_TIME_SEED     = 42

# A week is "fill-rate stressed" when ending inventory (Quantity_Available)
# was thin relative to that week's Quantity_Sold. No absolute ratio is
# meaningful across 60 very different SKUs, so — consistent with the
# adaptive-percentile approach already used in basket_analysis.py's
# Health_Band / Basket_Role classification — the bottom 20th percentile of
# the Availability_Ratio distribution (network-wide) defines "stressed".
FILL_RATE_STRESS_PCTILE = 20

# Trailing window for the Supplier Fill Rate and Safety Stock inputs
# ("3-month trailing average").
TRAILING_WEEKS = 13  # ~3 months at weekly grain
TRAILING_DAYS  = TRAILING_WEEKS * 7  # same 3-month window at the daily grain
                                     # of Inventory_Report (days-of-supply rollup)

# Supplier_Rating tiers: top 30% of Supplier_Confidence_Score = A,
# middle 40% = B, bottom 30% = C (percentile rank across all Store x SKU rows).
SUPPLIER_RATING_A_CUTOFF = 0.70  # rank >= this -> A
SUPPLIER_RATING_B_CUTOFF = 0.30  # rank >= this (and < A cutoff) -> B, else C

# Supplier Confidence Score weights (must sum to 1.0).
CONFIDENCE_WEIGHTS = {
    "sell_through": 0.30,
    "margin":       0.30,
    "fill_rate":    0.40,
}
assert abs(sum(CONFIDENCE_WEIGHTS.values()) - 1.0) < 1e-9, "CONFIDENCE_WEIGHTS must sum to 1.0"


# =============================================================================
# LOADERS
# =============================================================================
def _load_demand() -> pd.DataFrame:
    if _DB_AVAILABLE:
        df = _db_read("weekly_demand_output", DEMAND_CSV)
    else:
        df = pd.read_csv(DEMAND_CSV)
    df["Quantity_Sold"]      = pd.to_numeric(df["Quantity_Sold"],      errors="coerce").fillna(0)
    df["Quantity_Available"] = pd.to_numeric(df["Quantity_Available"], errors="coerce").fillna(0)
    return df


def _load_sku() -> pd.DataFrame:
    if _DB_AVAILABLE:
        df = _db_read("sku_master", SKU_CSV)
    else:
        df = pd.read_csv(SKU_CSV)
    cols = ["SKU_ID", "EAN_ID", "Product_Name", "Supplier", "Margin_Pct"]
    return df[[c for c in cols if c in df.columns]].copy()


def _load_inventory() -> pd.DataFrame:
    """
    Daily Date x Store_ID x SKU_ID inventory positions from Inventory_Report.
    Only the columns needed for the days-of-supply rollup are kept. Returns an
    empty frame (rather than raising) if the source is missing, empty, or lacks
    the expected columns, so the scorecard still builds without it.
    """
    try:
        if _DB_AVAILABLE:
            df = _db_read("inventory_report", INVENTORY_CSV)
        else:
            df = pd.read_csv(INVENTORY_CSV)
    except Exception as e:
        log.warning(f"  Inventory_Report unavailable ({e}) — days-of-supply columns will be blank.")
        return pd.DataFrame()

    need = {"Date", "Store_ID", "SKU_ID", "Days_Of_Supply"}
    missing = need - set(df.columns)
    if missing:
        log.warning(f"  Inventory_Report missing {missing} — days-of-supply columns will be blank.")
        return pd.DataFrame()

    df = df[["Date", "Store_ID", "SKU_ID", "Days_Of_Supply"]].copy()
    df["Date"]           = pd.to_datetime(df["Date"], errors="coerce")
    df["Days_Of_Supply"] = pd.to_numeric(df["Days_Of_Supply"], errors="coerce")
    return df.dropna(subset=["Date"])


# =============================================================================
# SECTION 1: RANDOM LEAD TIME
# =============================================================================
def add_lead_time(dm: pd.DataFrame) -> pd.DataFrame:
    """
    Attaches a random Lead_Time_Days to every Store_ID x SKU_ID x Year_WK row.
    Rows are sorted deterministically first so the fixed RNG seed produces the
    same values on every re-run (idempotent, reproducible — no real per-order
    lead-time data exists to source this from instead).
    """
    dm = dm.sort_values(["Store_ID", "SKU_ID", "Year_WK"]).reset_index(drop=True)
    rng = np.random.default_rng(LEAD_TIME_SEED)
    dm["Lead_Time_Days"] = rng.integers(LEAD_TIME_MIN_DAYS, LEAD_TIME_MAX_DAYS + 1, size=len(dm))
    return dm


# =============================================================================
# SECTION 2: SAFETY STOCK
# =============================================================================
def compute_safety_stock(dm: pd.DataFrame) -> pd.DataFrame:
    """
    One row per Store_ID x SKU_ID:
      Weekly_Demand_Mean, Weekly_Demand_Std — from full available history
      Current_Inventory                     — latest week's Quantity_Available
      Max_Daily_Sales_3M, Avg_Daily_Sales_3M — trailing 3-month daily sales rate
      Max_Lead_Time_Days_3M, Avg_Lead_Time_Days_3M,
      Lead_Time_Target_Days                 — trailing 3-month lead time (Avg, rounded)
      Safety_Stock_Units    = (Max_Daily_Sales_3M * Max_Lead_Time_Days_3M)
                             - (Avg_Daily_Sales_3M * Avg_Lead_Time_Days_3M)
      Safety_Stock_Gap_Units = Current_Inventory - Safety_Stock_Units
      Safety_Stock_Adequate_Flag = gap >= 0
    """
    stats = (dm.groupby(["Store_ID", "SKU_ID"])["Quantity_Sold"]
             .agg(Weekly_Demand_Mean="mean", Weekly_Demand_Std="std")
             .reset_index())
    stats["Weekly_Demand_Std"] = stats["Weekly_Demand_Std"].fillna(0)

    last_wk = dm["Year_WK"].max()
    current_inv = (dm[dm["Year_WK"] == last_wk]
                   .groupby(["Store_ID", "SKU_ID"])["Quantity_Available"]
                   .sum()
                   .reset_index(name="Current_Inventory"))

    weeks    = sorted(dm["Year_WK"].unique())
    trailing = weeks[-TRAILING_WEEKS:] if len(weeks) > TRAILING_WEEKS else weeks
    trail_df = dm[dm["Year_WK"].isin(trailing)].copy()
    trail_df["Daily_Sales"] = trail_df["Quantity_Sold"] / 7.0

    trail_stats = (trail_df.groupby(["Store_ID", "SKU_ID"])
                   .agg(Max_Daily_Sales_3M=("Daily_Sales", "max"),
                        Avg_Daily_Sales_3M=("Daily_Sales", "mean"),
                        Max_Lead_Time_Days_3M=("Lead_Time_Days", "max"),
                        Avg_Lead_Time_Days_3M=("Lead_Time_Days", "mean"))
                   .reset_index())

    df = (stats
          .merge(current_inv, on=["Store_ID", "SKU_ID"], how="left")
          .merge(trail_stats, on=["Store_ID", "SKU_ID"], how="left"))
    df["Current_Inventory"] = df["Current_Inventory"].fillna(0)
    for c in ["Max_Daily_Sales_3M", "Avg_Daily_Sales_3M", "Max_Lead_Time_Days_3M", "Avg_Lead_Time_Days_3M"]:
        df[c] = df[c].fillna(0)

    df["Lead_Time_Target_Days"] = df["Avg_Lead_Time_Days_3M"].round(0)

    df["Safety_Stock_Units"] = (
        (df["Max_Daily_Sales_3M"] * df["Max_Lead_Time_Days_3M"])
        - (df["Avg_Daily_Sales_3M"] * df["Avg_Lead_Time_Days_3M"])
    ).clip(lower=0).round(1)
    df["Safety_Stock_Gap_Units"]     = (df["Current_Inventory"] - df["Safety_Stock_Units"]).round(1)
    df["Safety_Stock_Adequate_Flag"] = df["Safety_Stock_Gap_Units"] >= 0

    log.info(f"  Safety stock computed for {len(df):,} Store x SKU combinations "
              f"(Max/Avg sales x Max/Avg lead time over trailing {len(trailing)} weeks).")
    return df


# =============================================================================
# SECTION 2b: DAYS OF SUPPLY (rollup of the daily Inventory_Report series)
# =============================================================================
def compute_days_of_supply(inv: pd.DataFrame) -> pd.DataFrame:
    """
    Rolls the daily Days_Of_Supply time series in Inventory_Report up to one
    row per Store_ID x SKU_ID:

      Latest_Days_Of_Supply — value on the most recent date on record; current
                              replenishment urgency (low = reorder soon).
      Mean_Days_Of_Supply   — average over the trailing 3-month window; typical
                              stock cover, smoothing daily depletion/replenish
                              swings.

    Days of supply is inherently a DAILY series (it decays as stock depletes and
    jumps on replenishment), so the full series stays in Inventory_Report at its
    Date x Store x SKU grain. The scorecard is Store x SKU with no date, so only
    these two per-pair summaries are carried here.
    """
    if inv.empty:
        return pd.DataFrame(columns=["Store_ID", "SKU_ID",
                                     "Latest_Days_Of_Supply", "Mean_Days_Of_Supply"])

    # Latest value per Store x SKU (row on the most recent date on record).
    latest_idx = inv.groupby(["Store_ID", "SKU_ID"])["Date"].idxmax()
    latest = (inv.loc[latest_idx, ["Store_ID", "SKU_ID", "Days_Of_Supply"]]
              .rename(columns={"Days_Of_Supply": "Latest_Days_Of_Supply"}))

    # Trailing 3-month mean (same 3-month window as the rest of the module).
    max_date = inv["Date"].max()
    cutoff   = max_date - pd.Timedelta(days=TRAILING_DAYS - 1)
    trail    = inv[inv["Date"] >= cutoff]
    mean = (trail.groupby(["Store_ID", "SKU_ID"])["Days_Of_Supply"]
            .mean()
            .reset_index(name="Mean_Days_Of_Supply"))

    df = latest.merge(mean, on=["Store_ID", "SKU_ID"], how="outer")
    df["Latest_Days_Of_Supply"] = df["Latest_Days_Of_Supply"].round(1)
    df["Mean_Days_Of_Supply"]   = df["Mean_Days_Of_Supply"].round(1)

    log.info(f"  Days-of-supply rolled up for {len(df):,} Store x SKU combinations "
              f"(latest + trailing {TRAILING_DAYS}-day mean, "
              f"window ending {max_date.date()}).")
    return df


# =============================================================================
# SECTION 3: SELL-THROUGH
# =============================================================================
def compute_sell_through(dm: pd.DataFrame) -> pd.DataFrame:
    """Sell_Through_Pct = units sold / (units sold + units still on hand)."""
    hist = (dm.groupby(["Store_ID", "SKU_ID"])
            .agg(hist_qty=("Quantity_Sold", "sum"))
            .reset_index())
    last_wk = dm["Year_WK"].max()
    inv = (dm[dm["Year_WK"] == last_wk]
           .groupby(["Store_ID", "SKU_ID"])["Quantity_Available"]
           .sum()
           .reset_index(name="current_inventory"))
    df = hist.merge(inv, on=["Store_ID", "SKU_ID"], how="left")
    df["current_inventory"] = df["current_inventory"].fillna(0)
    denom = df["hist_qty"] + df["current_inventory"]
    df["Sell_Through_Pct"] = np.where(denom > 0, df["hist_qty"] / denom, 0).round(4)
    return df[["Store_ID", "SKU_ID", "Sell_Through_Pct"]]


# =============================================================================
# SECTION 4: SUPPLIER FILL RATE (3-month trailing average)
# =============================================================================
def compute_fill_rate(dm: pd.DataFrame) -> pd.DataFrame:
    """
    Derives a Fill Rate proxy from real depletion behaviour since no supplier
    order/delivery data exists: a week is "stressed" when ending inventory
    (Quantity_Available) was thin relative to that week's demand
    (Quantity_Sold) — i.e. availability nearly ran out. Fill Rate = the
    fraction of the trailing window's weeks that were NOT stressed.
    """
    df = dm.copy()
    df["Availability_Ratio"] = df["Quantity_Available"] / df["Quantity_Sold"].replace(0, np.nan)
    stress_cut = df["Availability_Ratio"].quantile(FILL_RATE_STRESS_PCTILE / 100)
    df["Stress_Week"] = df["Availability_Ratio"] <= stress_cut

    weeks = sorted(df["Year_WK"].unique())
    trailing = weeks[-TRAILING_WEEKS:] if len(weeks) > TRAILING_WEEKS else weeks
    trail_df = df[df["Year_WK"].isin(trailing)]

    fill = (trail_df.groupby(["Store_ID", "SKU_ID"])["Stress_Week"]
            .agg(lambda s: 1 - s.mean())
            .reset_index(name="SKU_Store_Fill_Rate_Pct_3M"))
    fill["SKU_Store_Fill_Rate_Pct_3M"] = fill["SKU_Store_Fill_Rate_Pct_3M"].round(4)

    log.info(f"  Fill-rate stress threshold (bottom {FILL_RATE_STRESS_PCTILE}th pctile of "
              f"availability/sold ratio): <= {stress_cut:.3f}; trailing window = "
              f"{len(trailing)} of {len(weeks)} weeks.")
    return fill


# =============================================================================
# SECTION 5: SUPPLIER CONFIDENCE SCORE + RATING
# =============================================================================
def compute_supplier_confidence(df: pd.DataFrame) -> pd.DataFrame:
    """
    Rolls SKU x Store fill rate up to the Supplier level, then blends
    Sell-Through + Margin + Supplier Fill Rate into one 0-1 score per row.
    """
    df = df.copy()
    supplier_fill = (df.groupby("Supplier")["SKU_Store_Fill_Rate_Pct_3M"]
                      .mean()
                      .reset_index(name="Supplier_Fill_Rate_Pct_3M"))
    df = df.merge(supplier_fill, on="Supplier", how="left")
    df["Supplier_Fill_Rate_Pct_3M"] = df["Supplier_Fill_Rate_Pct_3M"].round(4)

    margin_norm = (pd.to_numeric(df["Margin_Pct"], errors="coerce").fillna(0) / 100).clip(0, 1)

    df["Supplier_Confidence_Score"] = (
        CONFIDENCE_WEIGHTS["sell_through"] * df["Sell_Through_Pct"] +
        CONFIDENCE_WEIGHTS["margin"]       * margin_norm +
        CONFIDENCE_WEIGHTS["fill_rate"]    * df["Supplier_Fill_Rate_Pct_3M"]
    ).round(4)

    return df


def compute_supplier_rating(df: pd.DataFrame) -> pd.DataFrame:
    """
    Supplier_Rating: A/B/C tier from the percentile rank of
    Supplier_Confidence_Score across all Store x SKU rows —
    top 30% -> A, middle 40% -> B, bottom 30% -> C.
    """
    df = df.copy()
    n = len(df)
    rank = df["Supplier_Confidence_Score"].rank(pct=True, method="average") if n > 1 else pd.Series([1.0] * n)
    df["Supplier_Rating"] = np.select(
        [rank >= SUPPLIER_RATING_A_CUTOFF, rank >= SUPPLIER_RATING_B_CUTOFF],
        ["A", "B"],
        default="C",
    )
    return df


# =============================================================================
# POSTGRES LOAD (no existing loader precedent in this codebase — new pattern)
# =============================================================================
# df.to_sql() is not used here: pandas >= 2.0 requires sqlalchemy >= 2.0 for
# its own SQL engine dispatch, but this project pins sqlalchemy 1.4.x (used
# throughout Backend for raw text() queries). Loading via SQLAlchemy Core
# directly (Table/MetaData + Table.insert()) works on 1.4 without touching
# that shared dependency.
def _sa_type_for(dtype) -> type:
    from sqlalchemy import BigInteger, Boolean, Float, String
    if pd.api.types.is_bool_dtype(dtype):
        return Boolean
    if pd.api.types.is_integer_dtype(dtype):
        # BigInteger, not Integer: EAN-13 codes (13 digits) overflow a 32-bit
        # PG integer column.
        return BigInteger
    if pd.api.types.is_float_dtype(dtype):
        return Float
    return String


def _load_to_postgres(df: pd.DataFrame) -> None:
    if not _DB_AVAILABLE:
        log.warning("  DB module unavailable — skipping PostgreSQL load.")
        return
    try:
        from sqlalchemy import Column, MetaData, Table

        engine = get_engine()
        meta   = MetaData()
        cols   = [Column(c, _sa_type_for(df[c].dtype)) for c in df.columns]
        table  = Table(PG_TABLE, meta, *cols)
        records = df.where(pd.notnull(df), None).to_dict(orient="records")

        with engine.begin() as conn:
            table.drop(conn, checkfirst=True)
            table.create(conn)
            if records:
                conn.execute(table.insert(), records)

        log.info(f"  [OK] Loaded {len(df):,} rows into PostgreSQL table '{PG_TABLE}'.")
    except Exception as e:
        log.warning(f"  PostgreSQL load skipped (unreachable or failed): {e}")


# =============================================================================
# ORCHESTRATION
# =============================================================================
def main() -> pd.DataFrame:
    log.info("Safety Stock & Supplier Confidence Score Module")
    log.info("=" * 60)

    dm  = _load_demand()
    sku = _load_sku()
    inv = _load_inventory()

    log.info("STEP: Generating random lead time (Store_ID x SKU_ID x Year_WK)")
    dm = add_lead_time(dm)

    log.info("STEP: Computing safety stock (Max/Avg sales x Max/Avg lead time)")
    ss = compute_safety_stock(dm)

    log.info("STEP: Rolling up days of supply (latest + trailing 3-month mean)")
    dos = compute_days_of_supply(inv)

    log.info("STEP: Computing sell-through")
    st = compute_sell_through(dm)

    log.info("STEP: Computing supplier fill rate (3-month trailing)")
    fr = compute_fill_rate(dm)

    df = (ss
          .merge(dos, on=["Store_ID", "SKU_ID"], how="left")
          .merge(st, on=["Store_ID", "SKU_ID"], how="left")
          .merge(fr, on=["Store_ID", "SKU_ID"], how="left")
          .merge(sku, on="SKU_ID", how="left"))
    df["SKU_Store_Fill_Rate_Pct_3M"] = df["SKU_Store_Fill_Rate_Pct_3M"].fillna(0)

    log.info("STEP: Computing supplier confidence score")
    df = compute_supplier_confidence(df)

    log.info("STEP: Computing supplier rating (A/B/C)")
    df = compute_supplier_rating(df)

    ordered_cols = [
        "Store_ID", "SKU_ID", "EAN_ID", "Product_Name", "Supplier",
        "Weekly_Demand_Mean", "Weekly_Demand_Std",
        "Current_Inventory",
        "Latest_Days_Of_Supply", "Mean_Days_Of_Supply",
        "Max_Daily_Sales_3M", "Avg_Daily_Sales_3M",
        "Max_Lead_Time_Days_3M", "Avg_Lead_Time_Days_3M", "Lead_Time_Target_Days",
        "Safety_Stock_Units", "Safety_Stock_Gap_Units", "Safety_Stock_Adequate_Flag",
        "Sell_Through_Pct", "Margin_Pct",
        "SKU_Store_Fill_Rate_Pct_3M", "Supplier_Fill_Rate_Pct_3M",
        "Supplier_Confidence_Score", "Supplier_Rating",
    ]
    df = df[[c for c in ordered_cols if c in df.columns]]

    df.to_csv(OUTPUT_CSV, index=False)
    log.info(f"  [OK] Saved: {os.path.basename(OUTPUT_CSV)} ({len(df):,} rows, {len(df.columns)} cols)")

    _load_to_postgres(df)

    log.info("=" * 60)
    log.info("Safety Stock & Supplier Confidence Score Module complete.")
    return df


if __name__ == "__main__":
    main()
