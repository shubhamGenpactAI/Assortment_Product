"""
build_weekly_demand.py
======================
Builds Outputs/weekly_demand_output.csv (and the PostgreSQL
"weekly_demand_output" table) — the Week x Store x SKU demand intermediate that
the forecasting, safety-stock, RCA, decision-hub and workspace layers all read.

This is the weekly-aggregation ETL described in ProcessFlow.md (Step 1-3) that
previously had no in-repo producer: the shipped Outputs/weekly_demand_output.csv
was a stale, differently-scaled artifact. This script (re)derives the file
directly from the enriched raw inputs so the whole downstream pipeline is
reproducible from Raw_Input/.

Contract (unchanged — matches what every consumer expects):
    Year_WK, Store_ID, SKU_ID, Quantity_Sold, Quantity_Available

Aggregation logic (per ProcessFlow.md):
  * Year_WK          — ISO year-week label "YYYY-WW" (sortable text; parsed by
                       forecasting.py with format "%G-%V-%u").
  * Quantity_Sold    — SUM of Sales_Tx.Units_Sold for every transaction line in
                       that (Year_WK, Store_ID, SKU_ID) cell.
  * Quantity_Available — END-OF-WEEK Inventory_On_Hand from Inventory_Report
                       (the on-hand reading on the latest date within the week,
                       NOT a sum — inventory is a stock level, not a flow).
  * Calendar continuity — the output is the FULL grid of every observed
                       Store_ID x SKU_ID pair x every ISO week in range, so
                       zero-sales weeks are represented explicitly (0) rather
                       than dropped, and demand is not left-censored.

Grain / coverage notes:
  * Sales_Tx carries all 900 Store_ID x SKU_ID pairs (15 stores x 60 SKUs).
  * Inventory_Report only tracks 590 of those 900 pairs (not every store
    carries every SKU). Pairs with no inventory row get Quantity_Available = 0
    (there is no stock series to read an end-of-week level from). Quantity_Sold
    is still populated for them from Sales_Tx.

Outputs:
  Outputs/weekly_demand_output.csv   (also loaded into the PostgreSQL
                                      "weekly_demand_output" table when reachable)

Run:
    python build_weekly_demand.py
"""

import logging
import os
import sys

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# DB import (try; fall back gracefully if not available) — mirrors the
# convention used by forecasting.py / basket_analysis.py / enrich_*_daily.py.
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

SALES_CSV     = os.path.join(RAW_DIR, "Sales_Tx.csv")
INVENTORY_CSV = os.path.join(RAW_DIR, "Inventory_Report.csv")
OUTPUT_CSV    = os.path.join(OUTPUTS_DIR, "weekly_demand_output.csv")
PG_TABLE      = "weekly_demand_output"

# Output column contract — order and names must not change (downstream code and
# the PostgreSQL table are written against exactly these).
OUTPUT_COLS = ["Year_WK", "Store_ID", "SKU_ID", "Quantity_Sold", "Quantity_Available"]


# =============================================================================
# LOADERS
# =============================================================================
def _load_sales() -> pd.DataFrame:
    if _DB_AVAILABLE:
        df = _db_read("sales_tx", SALES_CSV)
    else:
        df = pd.read_csv(SALES_CSV)
    need = {"Date", "Store_ID", "SKU_ID", "Units_Sold"}
    missing = need - set(df.columns)
    if missing:
        raise KeyError(f"Sales_Tx is missing required columns: {missing}. Available: {list(df.columns)}")
    df["Date"]       = pd.to_datetime(df["Date"], errors="coerce")
    df["Units_Sold"] = pd.to_numeric(df["Units_Sold"], errors="coerce").fillna(0)
    df = df.dropna(subset=["Date", "Store_ID", "SKU_ID"])
    return df[["Date", "Store_ID", "SKU_ID", "Units_Sold"]]


def _load_inventory() -> pd.DataFrame:
    """
    Daily Date x Store_ID x SKU_ID inventory positions. Returns an empty frame
    (rather than raising) if the source is missing/empty or lacks the expected
    columns, so the weekly table still builds (Quantity_Available all 0).
    """
    try:
        if _DB_AVAILABLE:
            df = _db_read("inventory_report", INVENTORY_CSV)
        else:
            df = pd.read_csv(INVENTORY_CSV)
    except Exception as e:
        log.warning(f"  Inventory_Report unavailable ({e}) — Quantity_Available will be 0.")
        return pd.DataFrame(columns=["Date", "Store_ID", "SKU_ID", "Inventory_On_Hand"])

    need = {"Date", "Store_ID", "SKU_ID", "Inventory_On_Hand"}
    missing = need - set(df.columns)
    if missing:
        log.warning(f"  Inventory_Report missing {missing} — Quantity_Available will be 0.")
        return pd.DataFrame(columns=["Date", "Store_ID", "SKU_ID", "Inventory_On_Hand"])

    df["Date"]              = pd.to_datetime(df["Date"], errors="coerce")
    df["Inventory_On_Hand"] = pd.to_numeric(df["Inventory_On_Hand"], errors="coerce").fillna(0)
    return df.dropna(subset=["Date", "Store_ID", "SKU_ID"])[
        ["Date", "Store_ID", "SKU_ID", "Inventory_On_Hand"]
    ]


# =============================================================================
# ISO WEEK LABEL
# =============================================================================
def _add_year_wk(df: pd.DataFrame) -> pd.DataFrame:
    iso = df["Date"].dt.isocalendar()
    df = df.copy()
    df["Year_WK"] = (
        iso["year"].astype(int).astype(str)
        + "-"
        + iso["week"].astype(int).astype(str).str.zfill(2)
    )
    return df


# =============================================================================
# AGGREGATIONS
# =============================================================================
def weekly_quantity_sold(sales: pd.DataFrame) -> pd.DataFrame:
    """SUM of Units_Sold per (Year_WK, Store_ID, SKU_ID)."""
    s = _add_year_wk(sales)
    out = (s.groupby(["Year_WK", "Store_ID", "SKU_ID"], as_index=False)["Units_Sold"]
           .sum()
           .rename(columns={"Units_Sold": "Quantity_Sold"}))
    return out


def weekly_end_of_week_inventory(inv: pd.DataFrame) -> pd.DataFrame:
    """
    END-OF-WEEK Inventory_On_Hand per (Year_WK, Store_ID, SKU_ID): the on-hand
    reading on the latest calendar date that falls inside the ISO week.
    """
    if inv.empty:
        return pd.DataFrame(columns=["Year_WK", "Store_ID", "SKU_ID", "Quantity_Available"])
    i = _add_year_wk(inv)
    # Row on the max Date within each (Year_WK, Store, SKU) group.
    idx = i.groupby(["Year_WK", "Store_ID", "SKU_ID"])["Date"].idxmax()
    eow = (i.loc[idx, ["Year_WK", "Store_ID", "SKU_ID", "Inventory_On_Hand"]]
           .rename(columns={"Inventory_On_Hand": "Quantity_Available"}))
    return eow.reset_index(drop=True)


def build_full_grid(sold: pd.DataFrame, avail: pd.DataFrame) -> pd.DataFrame:
    """
    Full calendar-continuous grid: every observed Store_ID x SKU_ID pair x every
    observed ISO week. Quantity_Sold zero-filled; Quantity_Available end-of-week
    value where inventory exists for that cell, else 0.
    """
    pairs = (pd.concat([sold[["Store_ID", "SKU_ID"]], avail[["Store_ID", "SKU_ID"]]],
                       ignore_index=True)
             .drop_duplicates()
             .reset_index(drop=True))
    weeks = pd.DataFrame({"Year_WK": sorted(set(sold["Year_WK"]) | set(avail["Year_WK"]))})

    grid = weeks.merge(pairs, how="cross")
    grid = (grid
            .merge(sold,  on=["Year_WK", "Store_ID", "SKU_ID"], how="left")
            .merge(avail, on=["Year_WK", "Store_ID", "SKU_ID"], how="left"))
    grid["Quantity_Sold"]      = grid["Quantity_Sold"].fillna(0)
    grid["Quantity_Available"] = grid["Quantity_Available"].fillna(0)

    # Integer units (Units_Sold and Inventory_On_Hand are whole units).
    grid["Quantity_Sold"]      = grid["Quantity_Sold"].round().astype("int64")
    grid["Quantity_Available"] = grid["Quantity_Available"].round().astype("int64")

    grid = grid.sort_values(["Store_ID", "SKU_ID", "Year_WK"]).reset_index(drop=True)
    return grid[OUTPUT_COLS]


# =============================================================================
# VALIDATION
# =============================================================================
def validate(df: pd.DataFrame) -> None:
    dup = df.duplicated(subset=["Year_WK", "Store_ID", "SKU_ID"]).sum()
    assert dup == 0, f"Found {dup} duplicate (Year_WK, Store_ID, SKU_ID) rows."

    n_stores = df["Store_ID"].nunique()
    n_skus   = df["SKU_ID"].nunique()
    n_weeks  = df["Year_WK"].nunique()
    n_pairs  = df.groupby(["Store_ID", "SKU_ID"]).ngroups

    # Full grid completeness: every pair present in every week.
    expected = n_pairs * n_weeks
    assert len(df) == expected, (
        f"Row count {len(df):,} != full grid {expected:,} "
        f"({n_pairs:,} pairs x {n_weeks:,} weeks) — calendar continuity broken."
    )

    weeks_per_pair = df.groupby(["Store_ID", "SKU_ID"])["Year_WK"].nunique()
    short = weeks_per_pair[weeks_per_pair != n_weeks]
    assert short.empty, f"{len(short)} pairs missing weeks: {short.head().to_dict()}"

    assert (df["Quantity_Sold"] >= 0).all(), "Negative Quantity_Sold present."
    assert (df["Quantity_Available"] >= 0).all(), "Negative Quantity_Available present."

    log.info(f"  [OK] Validation passed: {len(df):,} rows = {n_pairs:,} pairs x "
             f"{n_weeks:,} weeks; {n_stores} stores x {n_skus} SKUs; 0 duplicates; "
             f"no negatives.")


# =============================================================================
# POSTGRES LOAD (SQLAlchemy 1.4 Core — same pattern as enrich_*_daily.py)
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
    log.info("Weekly Demand Aggregation ETL (Week x Store x SKU)")
    log.info("=" * 60)

    sales = _load_sales()
    inv   = _load_inventory()
    log.info(f"STEP: Loaded {len(sales):,} Sales_Tx rows, {len(inv):,} Inventory_Report rows.")

    log.info("STEP: Aggregating Quantity_Sold (SUM Units_Sold per ISO week)")
    sold = weekly_quantity_sold(sales)

    log.info("STEP: Deriving Quantity_Available (END-OF-WEEK Inventory_On_Hand)")
    avail = weekly_end_of_week_inventory(inv)

    log.info("STEP: Building full calendar-continuous grid (pairs x weeks, zero-fill)")
    df = build_full_grid(sold, avail)

    log.info("STEP: Validating grain / continuity")
    validate(df)

    df.to_csv(OUTPUT_CSV, index=False)
    log.info(f"  [OK] Saved: {os.path.basename(OUTPUT_CSV)} "
             f"({len(df):,} rows, {len(df.columns)} cols, "
             f"weeks {df['Year_WK'].min()}..{df['Year_WK'].max()})")

    _load_to_postgres(df)

    log.info("=" * 60)
    log.info("Weekly Demand Aggregation ETL complete.")
    return df


if __name__ == "__main__":
    main()
