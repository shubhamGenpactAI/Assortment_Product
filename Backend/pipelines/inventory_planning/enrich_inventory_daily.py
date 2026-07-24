"""
enrich_inventory_daily.py
==========================
Enriches Raw_Input/Inventory_Report.csv (and the PostgreSQL "inventory_report"
table) from a sparse sample into a full DAILY time series covering 12 months,
Jun'2025 - May'2026 (2025-06-01 .. 2026-05-31 inclusive), with exactly one row
per (Date, Store_ID, SKU_ID) and no missing days.

The source file has only 2,500 rows across 590 distinct (Store_ID, SKU_ID)
pairs and 5 months (2026-01-01 .. 2026-05-31) - far short of a full daily
grid (590 pairs x 365 days = 215,350 rows). Every ORIGINAL row is preserved
unchanged at its original (Date, Store_ID, SKU_ID); every other day in the
12-month window is filled in.

ASSUMPTIONS (no raw source captures a daily inventory feed for Jun-Dec 2025,
so those days are simulated - documented proxies, not measured data):
  * The source data encodes an exact relationship for every real row:
        Inventory_Value = Inventory_On_Hand * SKU_Master.Unit_Cost_USD
        Days_Of_Supply  = round(Inventory_On_Hand / daily_sales_rate, 1)
    where daily_sales_rate is near-constant per (Store_ID, SKU_ID) (verified:
    std/mean well under 10% for the large majority of pairs). Both formulas
    are reused to derive Days_Of_Supply/Inventory_Value/Stockout_Flag for
    every SIMULATED (non-original) row, so filled rows stay internally
    consistent with the real rows for the same pair.
  * Inventory_On_Hand for simulated days follows a classic sawtooth
    depletion/restock pattern: it drains by that pair's daily_sales_rate
    (+/- noise) each day and jumps back up to an order-up-to level once it
    hits zero (a stockout day) - the same "stockout -> replenishment" shape
    real retail inventory follows. The path is anchored to the real
    observations: whenever the walk reaches a date that has an original row,
    it snaps to that exact value and continues from there, so simulated
    stretches stay continuous with the real data around them.
  * order_up_to per pair = 2 x daily_sales_rate x mean(Days_Of_Supply) from
    that pair's real rows, i.e. calibrated so the simulated average days-of-
    supply matches what was actually observed for that Store_ID x SKU_ID.
  * Fixed RNG seed (SIM_SEED) + deterministic pair/day iteration order make
    this script idempotent - re-running it reproduces the same fill values.

Outputs:
  Raw_Input/Inventory_Report.csv   (overwritten in place, enriched to 12
                                    months daily grain; also loaded into
                                    PostgreSQL table "inventory_report" when
                                    the DB is reachable)

Run:
    python enrich_inventory_daily.py
"""

import logging
import os
import sys

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# DB import (try; fall back gracefully if not available) - mirrors the
# convention used by forecasting.py / basket_analysis.py / safety_stock_supplier.py.
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
BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(BASE_DIR)))
OUTPUTS_DIR = os.path.join(PROJECT_DIR, "Outputs")
RAW_DIR     = os.path.join(PROJECT_DIR, "Raw_Input")
os.makedirs(OUTPUTS_DIR, exist_ok=True)

INVENTORY_CSV = os.path.join(RAW_DIR, "Inventory_Report.csv")
SKU_CSV       = os.path.join(RAW_DIR, "SKU_Master.csv")
PG_TABLE      = "inventory_report"

# 12-month daily window: Jun'2025 - May'2026 inclusive.
START_DATE = "2025-06-01"
END_DATE   = "2026-05-31"

# --- ASSUMPTIONS (documented proxies for the simulated fill - see module
# docstring for the full rationale) --------------------------------------
SIM_SEED           = 7          # fixed -> reproducible re-runs
DEPLETION_NOISE_SD = 0.15       # day-to-day noise on the depletion rate
RESTOCK_NOISE_SD   = 0.05       # noise on the restock-to level
MIN_ORDER_UP_TO    = 1.0        # floor so a pair never gets a degenerate 0 order-up-to level
FALLBACK_DAILY_RATE = None      # filled in from the network-wide mean at runtime
FALLBACK_MEAN_DOS   = None      # filled in from the network-wide mean at runtime


# =============================================================================
# LOADERS
# =============================================================================
def _load_inventory() -> pd.DataFrame:
    if _DB_AVAILABLE:
        df = _db_read("inventory_report", INVENTORY_CSV)
    else:
        df = pd.read_csv(INVENTORY_CSV)
    df["Date"] = pd.to_datetime(df["Date"])
    df["Inventory_On_Hand"] = pd.to_numeric(df["Inventory_On_Hand"], errors="coerce").fillna(0).astype("int64")
    df["Stockout_Flag"]     = pd.to_numeric(df["Stockout_Flag"],     errors="coerce").fillna(0).astype("int64")
    df["Days_Of_Supply"]    = pd.to_numeric(df["Days_Of_Supply"],    errors="coerce").fillna(0.0)
    df["Inventory_Value"]   = pd.to_numeric(df["Inventory_Value"],   errors="coerce").fillna(0.0)
    return _dedupe_original(df)


def _dedupe_original(df: pd.DataFrame) -> pd.DataFrame:
    """
    The source file carries a small number of conflicting duplicate
    (Date, Store_ID, SKU_ID) readings (two different inventory snapshots
    logged for the same day). Each duplicate group is collapsed to one row:
    Inventory_On_Hand/Days_Of_Supply/Inventory_Value averaged (rounded back
    to the source dtypes), Stockout_Flag OR'd across the group (a stockout
    reported by either reading counts as a stockout that day).
    """
    dup_mask = df.duplicated(subset=["Date", "Store_ID", "SKU_ID"], keep=False)
    n_dup_groups = df.loc[dup_mask].groupby(["Date", "Store_ID", "SKU_ID"]).ngroups
    if n_dup_groups == 0:
        return df

    log.warning(f"  Source file has {n_dup_groups} duplicate (Date, Store_ID, SKU_ID) keys "
                f"({dup_mask.sum()} rows) with conflicting readings — collapsing each to one "
                f"row (mean of numeric fields, OR of Stockout_Flag).")
    collapsed = (df.groupby(["Date", "Store_ID", "SKU_ID"], as_index=False)
                 .agg(Inventory_On_Hand=("Inventory_On_Hand", "mean"),
                      Stockout_Flag=("Stockout_Flag", "max"),
                      Days_Of_Supply=("Days_Of_Supply", "mean"),
                      Inventory_Value=("Inventory_Value", "mean")))
    collapsed["Inventory_On_Hand"] = collapsed["Inventory_On_Hand"].round().astype("int64")
    collapsed["Stockout_Flag"]     = collapsed["Stockout_Flag"].astype("int64")
    collapsed["Days_Of_Supply"]    = collapsed["Days_Of_Supply"].round(1)
    collapsed["Inventory_Value"]   = collapsed["Inventory_Value"].round(2)
    return collapsed


def _load_unit_costs() -> dict:
    if _DB_AVAILABLE:
        df = _db_read("sku_master", SKU_CSV)
    else:
        df = pd.read_csv(SKU_CSV)
    df["Unit_Cost_USD"] = pd.to_numeric(df["Unit_Cost_USD"], errors="coerce")
    return dict(zip(df["SKU_ID"], df["Unit_Cost_USD"]))


# =============================================================================
# SECTION 1: PER (Store_ID, SKU_ID) DEPLETION-RATE / ORDER-UP-TO STATS
# =============================================================================
def compute_pair_stats(inv: pd.DataFrame) -> pd.DataFrame:
    """
    One row per (Store_ID, SKU_ID) with the daily_sales_rate and mean
    Days_Of_Supply implied by that pair's ORIGINAL rows, used to calibrate
    the sawtooth simulation for every day this pair is missing.
    """
    real = inv[inv["Inventory_On_Hand"] > 0].copy()
    real["Implied_Daily_Rate"] = real["Inventory_On_Hand"] / real["Days_Of_Supply"].replace(0, np.nan)

    global_rate = real["Implied_Daily_Rate"].mean(skipna=True)
    global_dos  = real["Days_Of_Supply"].mean(skipna=True)

    stats = (real.groupby(["Store_ID", "SKU_ID"])
             .agg(Daily_Sales_Rate=("Implied_Daily_Rate", "mean"),
                  Mean_Days_Of_Supply=("Days_Of_Supply", "mean"))
             .reset_index())
    stats["Daily_Sales_Rate"] = stats["Daily_Sales_Rate"].fillna(global_rate)
    stats["Mean_Days_Of_Supply"] = stats["Mean_Days_Of_Supply"].fillna(global_dos)

    stats["Order_Up_To"] = (2 * stats["Daily_Sales_Rate"] * stats["Mean_Days_Of_Supply"]).clip(lower=MIN_ORDER_UP_TO)

    log.info(f"  Calibrated depletion/restock stats for {len(stats):,} Store_ID x SKU_ID pairs "
             f"(network-wide fallback rate={global_rate:.2f} units/day, "
             f"mean days-of-supply={global_dos:.2f}).")
    return stats


# =============================================================================
# SECTION 2: DAILY SKELETON (Date x Store_ID x SKU_ID, full 12-month grid)
# =============================================================================
def build_daily_skeleton(pairs: pd.DataFrame, date_range: pd.DatetimeIndex) -> pd.DataFrame:
    pairs = pairs[["Store_ID", "SKU_ID"]].drop_duplicates().reset_index(drop=True)
    dates = pd.DataFrame({"Date": date_range})
    skeleton = dates.merge(pairs, how="cross")
    log.info(f"  Built daily skeleton: {len(date_range):,} days x {len(pairs):,} Store_ID x SKU_ID "
              f"pairs = {len(skeleton):,} rows.")
    return skeleton


# =============================================================================
# SECTION 3: SAWTOOTH DEPLETION/RESTOCK SIMULATION (anchored to real rows)
# =============================================================================
def _simulate_pair_series(dates: pd.DatetimeIndex, actual_by_date: dict,
                           daily_rate: float, order_up_to: float,
                           rng: np.random.Generator) -> np.ndarray:
    """
    Walks the full date range day by day. On a date with a real observation
    it snaps to that exact value; otherwise it depletes by daily_rate
    (+/- noise) and restocks to order_up_to (+/- noise) once it hits zero.
    Snapping to real anchors keeps simulated stretches continuous with the
    genuine data surrounding them.
    """
    n = len(dates)
    depletion_noise = rng.normal(1.0, DEPLETION_NOISE_SD, size=n).clip(min=0.0)
    restock_noise   = rng.normal(1.0, RESTOCK_NOISE_SD, size=n).clip(min=0.5)

    levels = np.empty(n)
    level = order_up_to * rng.uniform(0.3, 1.0)
    for i, d in enumerate(dates):
        if d in actual_by_date:
            level = actual_by_date[d]
        elif level <= 0:
            level = max(order_up_to * restock_noise[i], 1.0)
        levels[i] = max(level, 0.0)
        level -= daily_rate * depletion_noise[i]
        if level < 0:
            level = 0.0
    return levels


def fill_daily_series(skeleton: pd.DataFrame, inv: pd.DataFrame,
                       pair_stats: pd.DataFrame, unit_cost: dict) -> pd.DataFrame:
    stats_map = pair_stats.set_index(["Store_ID", "SKU_ID"])[
        ["Daily_Sales_Rate", "Order_Up_To"]
    ].to_dict(orient="index")

    inv_by_pair = {
        key: dict(zip(g["Date"], g["Inventory_On_Hand"]))
        for key, g in inv.groupby(["Store_ID", "SKU_ID"])
    }

    rng = np.random.default_rng(SIM_SEED)
    out_rows = []
    for (store_id, sku_id), group in skeleton.sort_values(["Store_ID", "SKU_ID", "Date"]).groupby(
        ["Store_ID", "SKU_ID"], sort=True
    ):
        dates = group["Date"].to_numpy()
        pstats = stats_map[(store_id, sku_id)]
        actual_by_date = inv_by_pair.get((store_id, sku_id), {})

        levels = _simulate_pair_series(dates, actual_by_date, pstats["Daily_Sales_Rate"],
                                        pstats["Order_Up_To"], rng)
        on_hand = np.round(levels).astype("int64")
        on_hand = np.maximum(on_hand, 0)

        rate = pstats["Daily_Sales_Rate"]
        cost = unit_cost.get(sku_id, np.nan)
        dos = np.where(on_hand > 0, np.round(on_hand / rate, 1), 0.0)
        value = np.round(on_hand * cost, 2)
        stockout = (on_hand == 0).astype("int64")

        out_rows.append(pd.DataFrame({
            "Date": dates, "Store_ID": store_id, "SKU_ID": sku_id,
            "Inventory_On_Hand": on_hand, "Stockout_Flag": stockout,
            "Days_Of_Supply": dos, "Inventory_Value": value,
        }))

    simulated = pd.concat(out_rows, ignore_index=True)

    # Overlay the ORIGINAL rows verbatim on top of the simulated grid so every
    # real observation is preserved exactly as-is.
    merged = simulated.merge(
        inv, on=["Date", "Store_ID", "SKU_ID"], how="left", suffixes=("", "_orig")
    )
    is_original = merged["Inventory_On_Hand_orig"].notna()
    for col in ["Inventory_On_Hand", "Stockout_Flag", "Days_Of_Supply", "Inventory_Value"]:
        merged[col] = np.where(is_original, merged[f"{col}_orig"], merged[col])
    merged = merged.drop(columns=[c for c in merged.columns if c.endswith("_orig")])

    merged["Inventory_On_Hand"] = merged["Inventory_On_Hand"].astype("int64")
    merged["Stockout_Flag"]     = merged["Stockout_Flag"].astype("int64")
    merged["Days_Of_Supply"]    = merged["Days_Of_Supply"].astype("float64").round(1)
    merged["Inventory_Value"]   = merged["Inventory_Value"].astype("float64").round(2)

    log.info(f"  Filled {len(merged):,} rows total ({is_original.sum():,} preserved from the "
              f"original file, {(~is_original).sum():,} simulated).")
    return merged


# =============================================================================
# SECTION 4: VALIDATION
# =============================================================================
def validate(df: pd.DataFrame, expected_pairs: int, expected_days: int) -> None:
    dup_count = df.duplicated(subset=["Date", "Store_ID", "SKU_ID"]).sum()
    assert dup_count == 0, f"Found {dup_count} duplicate (Date, Store_ID, SKU_ID) rows."

    expected_rows = expected_pairs * expected_days
    assert len(df) == expected_rows, (
        f"Row count {len(df):,} != expected {expected_rows:,} "
        f"({expected_pairs:,} pairs x {expected_days:,} days)."
    )

    days_per_pair = df.groupby(["Store_ID", "SKU_ID"])["Date"].nunique()
    short_pairs = days_per_pair[days_per_pair != expected_days]
    assert short_pairs.empty, (
        f"{len(short_pairs)} Store_ID x SKU_ID pairs are missing dates: "
        f"{short_pairs.head().to_dict()}"
    )

    zero_rows = (df["Inventory_On_Hand"] == 0).sum()
    log.info(f"  [OK] Validation passed: 0 duplicates, {len(df):,} rows = "
             f"{expected_pairs:,} pairs x {expected_days:,} days, every pair has full "
             f"daily coverage, {zero_rows:,} zero-inventory rows present.")


# =============================================================================
# POSTGRES LOAD
# =============================================================================
def _sa_type_for(dtype) -> type:
    from sqlalchemy import BigInteger, Boolean, Float, String
    if pd.api.types.is_bool_dtype(dtype):
        return Boolean
    if pd.api.types.is_integer_dtype(dtype):
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
    log.info("Inventory 12-Month Daily Enrichment Module")
    log.info("=" * 60)

    inv = _load_inventory()
    unit_cost = _load_unit_costs()
    date_range = pd.date_range(START_DATE, END_DATE, freq="D")

    log.info(f"STEP: Loaded {len(inv):,} original rows, "
             f"{inv.groupby(['Store_ID', 'SKU_ID']).ngroups:,} Store_ID x SKU_ID pairs, "
             f"range {inv['Date'].min().date()} .. {inv['Date'].max().date()}")

    log.info("STEP: Calibrating depletion rate / order-up-to level per pair")
    pair_stats = compute_pair_stats(inv)

    log.info(f"STEP: Building daily skeleton for {START_DATE} .. {END_DATE}")
    skeleton = build_daily_skeleton(pair_stats, date_range)

    log.info("STEP: Simulating missing days (anchored sawtooth depletion/restock)")
    df = fill_daily_series(skeleton, inv, pair_stats, unit_cost)

    df = df.sort_values(["Store_ID", "SKU_ID", "Date"]).reset_index(drop=True)
    df = df[["Date", "Store_ID", "SKU_ID", "Inventory_On_Hand", "Stockout_Flag",
              "Days_Of_Supply", "Inventory_Value"]]

    log.info("STEP: Validating no duplicates / no missing dates")
    validate(df, expected_pairs=pair_stats.shape[0], expected_days=len(date_range))

    df_out = df.copy()
    df_out["Date"] = df_out["Date"].dt.strftime("%Y-%m-%d")
    df_out.to_csv(INVENTORY_CSV, index=False)
    log.info(f"  [OK] Saved: {os.path.basename(INVENTORY_CSV)} "
              f"({len(df_out):,} rows, {len(df_out.columns)} cols)")

    _load_to_postgres(df_out)

    log.info("=" * 60)
    log.info("Inventory 12-Month Daily Enrichment Module complete.")
    return df_out


if __name__ == "__main__":
    main()
