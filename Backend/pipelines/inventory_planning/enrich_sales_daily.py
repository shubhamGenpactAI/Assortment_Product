"""
enrich_sales_daily.py
=======================
Enriches Raw_Input/Sales_Tx.csv (and the PostgreSQL "sales_tx" table) to a
full 12-month window, 2025-06-01 .. 2026-05-31, and reconciles daily sales
against Raw_Input/Inventory_Report.csv so the two datasets agree.

SCOPE (decided with the user): Inventory_Report.csv only tracks 590 of the
900 possible (Store_ID, SKU_ID) pairs (not every store carries every SKU).
Sales_Tx.csv, in contrast, has at least one historical transaction for all
900 pairs. This script only enriches/aligns the 590 pairs Inventory_Report
tracks; the remaining 310 "legacy" pairs are left completely untouched
(their real rows keep their original Jan-May 2026 dates and are not
extended, capped, or consolidated) since there is no inventory basis to
validate them against.

What happens to the 590 in-scope pairs:
  1. Existing (Date, Store_ID, SKU_ID) groups with MORE than 4 transaction
     lines are consolidated down to <= 4 (the 3 largest lines keep their
     original Txn_ID/basket membership untouched; every smaller line beyond
     that is merged into one new aggregate line) - satisfies the "no more
     than 4 records per Store-SKU-day" rule.
  2. Existing groups whose total Units_Sold exceeds that day's
     Inventory_On_Hand are capped: proportionally scaled down (lines that
     would floor to 0 units are dropped), or entirely dropped if that day's
     Inventory_On_Hand is 0 (you cannot sell out of zero stock).
  3. Every day in the 12-month window with NO existing transaction line for
     a pair is a candidate for a new synthetic sale: 1-4 new single-SKU
     transaction lines are generated (each its own Txn_ID/basket, Basket_Size
     1), sized off that pair's own historical daily sell-through rate,
     capped at that day's Inventory_On_Hand, and skipped entirely (0 sales)
     with a pair-specific probability calibrated from how often that pair
     already shows zero sales in its real Jan-May 2026 history.

ASSUMPTIONS (documented proxies for the fully-synthetic Jun-Dec 2025 period
and for reconciling the two independently-generated datasets):
  * "Sales must not exceed inventory on hand that day" is enforced directly
    per day. This also implements the stated "if Inventory_On_Hand=0 on a
    day, sales must be 0 the following day unless replenished" rule as a
    special case: day D+1's own cap is Inventory_On_Hand(D+1), which is 0
    unless a restock happened, so the daily cap alone is sufficient and no
    separate lag rule is needed.
  * New line's Unit_Price_USD / Promo_Flag / Channel are bootstrap-sampled
    from that SKU's own real historical Sales_Tx rows (network-wide, all
    stores) rather than modelled from scratch, so they stay in-range with
    already-observed pricing/promo/channel behaviour for that SKU.
  * Cost_Price = SKU_Master.Unit_Cost_USD (same cost basis already used by
    basket_analysis.py's GMROI calc and by enrich_inventory_daily.py's
    Inventory_Value formula), replicated onto every line. Net_Sales_USD and
    Gross_Margin_USD are recomputed for every row (Units_Sold x
    Unit_Price_USD, and (Unit_Price_USD - Cost_Price) x Units_Sold) so the
    whole file is internally consistent, not just the newly-added rows.
  * Basket_Size is recomputed file-wide as the actual line count per Txn_ID
    after consolidation/dropping, since it is a derived field, not an
    independent one (verified: it always matches exact Txn_ID line counts
    in the original data).
  * Fixed RNG seed (SIM_SEED) -> reproducible re-runs.

Outputs:
  Raw_Input/Sales_Tx.csv   (overwritten in place; also loaded into
                             PostgreSQL table "sales_tx" when reachable)

Run:
    python enrich_sales_daily.py
"""

import logging
import os
import sys

import numpy as np
import pandas as pd

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
RAW_DIR     = os.path.join(PROJECT_DIR, "Raw_Input")

SALES_CSV     = os.path.join(RAW_DIR, "Sales_Tx.csv")
INVENTORY_CSV = os.path.join(RAW_DIR, "Inventory_Report.csv")
SKU_CSV       = os.path.join(RAW_DIR, "SKU_Master.csv")
STORE_CSV     = os.path.join(RAW_DIR, "Store_Master.csv")
PG_TABLE      = "sales_tx"

START_DATE = "2025-06-01"
END_DATE   = "2026-05-31"

MAX_RECORDS_PER_DAY = 4    # hard cap for the 590 in-scope pairs
SIM_SEED = 11              # fixed -> reproducible re-runs


# =============================================================================
# LOADERS
# =============================================================================
def _load_sales() -> pd.DataFrame:
    if _DB_AVAILABLE:
        df = _db_read("sales_tx", SALES_CSV)
    else:
        df = pd.read_csv(SALES_CSV)
    df["Units_Sold"]  = pd.to_numeric(df["Units_Sold"], errors="coerce").fillna(0).astype("int64")
    df["Promo_Flag"]  = pd.to_numeric(df["Promo_Flag"], errors="coerce").fillna(0).astype("int64")
    return df


def _load_inventory() -> pd.DataFrame:
    if _DB_AVAILABLE:
        df = _db_read("inventory_report", INVENTORY_CSV)
    else:
        df = pd.read_csv(INVENTORY_CSV)
    df["Inventory_On_Hand"] = pd.to_numeric(df["Inventory_On_Hand"], errors="coerce").fillna(0).astype("int64")
    return df


def _load_sku() -> pd.DataFrame:
    if _DB_AVAILABLE:
        df = _db_read("sku_master", SKU_CSV)
    else:
        df = pd.read_csv(SKU_CSV)
    return df


def _load_store() -> pd.DataFrame:
    if _DB_AVAILABLE:
        df = _db_read("store_master", STORE_CSV)
    else:
        df = pd.read_csv(STORE_CSV)
    return df


# =============================================================================
# SECTION 1: PER-PAIR CALIBRATION (daily sell-through rate, zero-sale rate,
# bootstrap pools) - all derived from the pair's / SKU's own real history.
# =============================================================================
def compute_pair_daily_rate(inv: pd.DataFrame) -> tuple:
    real = inv[inv["Inventory_On_Hand"] > 0].copy()
    real["Implied_Daily_Rate"] = real["Inventory_On_Hand"] / real["Days_Of_Supply"].replace(0, np.nan)
    global_rate = real["Implied_Daily_Rate"].mean(skipna=True)
    rate_map = (real.groupby(["Store_ID", "SKU_ID"])["Implied_Daily_Rate"]
                .mean().fillna(global_rate).to_dict())
    return rate_map, global_rate


def compute_pair_zero_sale_rate(tx_in_scope: pd.DataFrame, pairs: list, n_hist_days: int) -> dict:
    """Fraction of the pair's real Jan-May 2026 days with no recorded sale — reused as
    that pair's probability of a genuine no-sale day when generating new (missing) days."""
    days_with_sale = (tx_in_scope.groupby(["Store_ID", "SKU_ID"])["Date"]
                       .nunique())
    zero_rate = {}
    for store_id, sku_id in pairs:
        n_sale_days = days_with_sale.get((store_id, sku_id), 0)
        zero_rate[(store_id, sku_id)] = 1.0 - (n_sale_days / n_hist_days)
    return zero_rate


def build_bootstrap_pools(tx_in_scope: pd.DataFrame, sku_ids: list) -> dict:
    """Per-SKU pool of (Unit_Price_USD, Promo_Flag, Channel) tuples sampled from
    that SKU's own real transaction lines (across all stores) - used to draw
    realistic attribute values for newly-generated lines."""
    pools = {}
    for sku_id, g in tx_in_scope.groupby("SKU_ID"):
        pools[sku_id] = list(zip(g["Unit_Price_USD"], g["Promo_Flag"], g["Channel"]))
    return pools


# =============================================================================
# SECTION 2: RECONCILE EXISTING IN-SCOPE ROWS (consolidate >4/day, cap to
# on-hand)
# =============================================================================
def _consolidate_over_max(group: pd.DataFrame, next_ids) -> pd.DataFrame:
    """Collapse a >MAX_RECORDS_PER_DAY-line group to <= MAX_RECORDS_PER_DAY:
    keep the (MAX-1) largest lines untouched (their real Txn_ID/basket is
    preserved), merge every smaller line into a single new aggregate line."""
    if len(group) <= MAX_RECORDS_PER_DAY:
        return group

    ordered = group.sort_values("Units_Sold", ascending=False)
    keep = ordered.iloc[: MAX_RECORDS_PER_DAY - 1]
    rest = ordered.iloc[MAX_RECORDS_PER_DAY - 1:]

    merged_units = int(rest["Units_Sold"].sum())
    merged_price = round(rest["Net_Sales_USD"].sum() / merged_units, 2) if merged_units > 0 else rest["Unit_Price_USD"].iloc[0]
    line_id, txn_id = next_ids()
    merged_row = rest.iloc[0].copy()
    merged_row["Line_ID"] = line_id
    merged_row["Txn_ID"] = txn_id
    merged_row["Units_Sold"] = merged_units
    merged_row["Unit_Price_USD"] = merged_price
    merged_row["Promo_Flag"] = int(rest["Promo_Flag"].max())
    merged_row["Channel"] = rest["Channel"].mode().iloc[0]

    return pd.concat([keep, merged_row.to_frame().T], ignore_index=True)


def _cap_group_to_inventory(group: pd.DataFrame, on_hand: int) -> pd.DataFrame:
    """Scale a group's Units_Sold down so the day's total never exceeds
    on_hand; drop the whole group if on_hand is 0 (nothing could have sold)."""
    total = group["Units_Sold"].sum()
    if total <= on_hand:
        return group
    if on_hand <= 0:
        return group.iloc[0:0]

    ratio = on_hand / total
    scaled = np.floor(group["Units_Sold"].to_numpy() * ratio).astype(int)
    keep_mask = scaled > 0
    if not keep_mask.any():
        idx = group["Units_Sold"].idxmax()
        out = group.loc[[idx]].copy()
        out["Units_Sold"] = int(on_hand)
        return out
    out = group.loc[keep_mask].copy()
    out["Units_Sold"] = scaled[keep_mask]
    return out


def reconcile_existing(tx_in_scope: pd.DataFrame, inv_map: dict, next_ids) -> pd.DataFrame:
    inv_lookup = inv_map  # {(date_str, store, sku): on_hand}
    out_groups = []
    n_consolidated = 0
    n_capped = 0
    n_dropped_zero_inv = 0

    for (date, store_id, sku_id), group in tx_in_scope.groupby(["Date", "Store_ID", "SKU_ID"], sort=False):
        if len(group) > MAX_RECORDS_PER_DAY:
            group = _consolidate_over_max(group, next_ids)
            n_consolidated += 1

        on_hand = inv_lookup.get((date, store_id, sku_id))
        if on_hand is not None:
            total_before = group["Units_Sold"].sum()
            group = _cap_group_to_inventory(group, on_hand)
            if group.empty and total_before > 0:
                n_dropped_zero_inv += 1
            elif group["Units_Sold"].sum() < total_before:
                n_capped += 1

        if not group.empty:
            out_groups.append(group)

    result = pd.concat(out_groups, ignore_index=True) if out_groups else tx_in_scope.iloc[0:0].copy()
    log.info(f"  Reconciled existing rows: {n_consolidated:,} day-pairs consolidated (>{MAX_RECORDS_PER_DAY} lines), "
             f"{n_capped:,} day-pairs capped to available inventory, "
             f"{n_dropped_zero_inv:,} day-pairs dropped entirely (0 on-hand that day).")
    return result


# =============================================================================
# SECTION 3: GENERATE NEW ROWS FOR MISSING PAIR-DAYS
# =============================================================================
def _split_units(total: int, n: int, rng: np.random.Generator) -> list:
    n = max(1, min(n, total))
    if n == 1:
        return [total]
    cuts = rng.choice(np.arange(1, total), size=n - 1, replace=False)
    cuts.sort()
    bounds = [0] + list(cuts) + [total]
    return [bounds[i + 1] - bounds[i] for i in range(n)]


def generate_missing_days(pairs: list, existing_days: dict, inv_map: dict,
                           rate_map: dict, zero_rate_map: dict, pools: dict,
                           sku_meta: dict, store_meta: dict, date_strs: list,
                           next_ids) -> pd.DataFrame:
    rng = np.random.default_rng(SIM_SEED)
    rows = []

    for store_id, sku_id in pairs:
        existing = existing_days.get((store_id, sku_id), set())
        rate = rate_map.get((store_id, sku_id))
        zero_rate = min(max(zero_rate_map.get((store_id, sku_id), 0.36), 0.0), 0.95)
        pool = pools.get(sku_id) or [(sku_meta[sku_id]["List_Price_USD"], 0, "Offline")]
        abc_class, sub_category, brand = sku_meta[sku_id]["ABC_Class"], sku_meta[sku_id]["Sub_Category"], sku_meta[sku_id]["Brand"]
        geography = store_meta[store_id]["Geography"]

        for date in date_strs:
            if date in existing:
                continue
            on_hand = inv_map.get((date, store_id, sku_id), 0)
            if on_hand <= 0:
                continue
            if rng.random() < zero_rate:
                continue

            noise = rng.lognormal(mean=-0.245, sigma=0.7)   # E[noise] ~= 1.0
            sold = int(round(min(on_hand, rate * noise)))
            sold = max(sold, 1) if on_hand > 0 else 0
            sold = min(sold, on_hand)
            if sold <= 0:
                continue

            n_lines = rng.integers(1, min(MAX_RECORDS_PER_DAY, sold) + 1)
            parts = _split_units(sold, int(n_lines), rng)

            for units in parts:
                price, promo, channel = pool[rng.integers(0, len(pool))]
                line_id, txn_id = next_ids()
                rows.append({
                    "Line_ID": line_id, "Txn_ID": txn_id, "Date": date, "SKU_ID": sku_id,
                    "Brand": brand, "Sub_Category": sub_category, "ABC_Class": abc_class,
                    "Store_ID": store_id, "Channel": channel, "Geography": geography,
                    "Units_Sold": int(units), "Unit_Price_USD": round(float(price), 2),
                    "Net_Sales_USD": np.nan, "Gross_Margin_USD": np.nan,
                    "Promo_Flag": int(promo), "Basket_Size": 1,
                })

    new_df = pd.DataFrame(rows)
    log.info(f"  Generated {len(new_df):,} new transaction lines across "
             f"{len(pairs):,} pairs for missing days in {START_DATE} .. {END_DATE}.")
    return new_df


# =============================================================================
# SECTION 4: FINALIZE (Cost_Price, Net_Sales/Gross_Margin recompute, Basket_Size)
# =============================================================================
def finalize(df: pd.DataFrame, unit_cost: dict) -> pd.DataFrame:
    df = df.copy()
    df["Cost_Price"] = df["SKU_ID"].map(unit_cost)
    df["Net_Sales_USD"] = (df["Units_Sold"] * df["Unit_Price_USD"]).round(2)
    df["Gross_Margin_USD"] = ((df["Unit_Price_USD"] - df["Cost_Price"]) * df["Units_Sold"]).round(2)
    df["Basket_Size"] = df.groupby("Txn_ID")["Txn_ID"].transform("size")
    return df


# =============================================================================
# SECTION 5: VALIDATION
# =============================================================================
def validate(df: pd.DataFrame, in_scope_pairs: set, inv_map: dict) -> None:
    in_scope_mask = df.set_index(["Store_ID", "SKU_ID"]).index.isin(in_scope_pairs)
    in_scope = df[in_scope_mask]

    daily = in_scope.groupby(["Date", "Store_ID", "SKU_ID"])["Units_Sold"].agg(["sum", "count"])

    over_cap = daily[daily["count"] > MAX_RECORDS_PER_DAY]
    assert over_cap.empty, f"{len(over_cap)} in-scope Store-SKU-days exceed {MAX_RECORDS_PER_DAY} records: {over_cap.head()}"

    on_hand_series = daily.index.map(lambda k: inv_map.get(k, None))
    checked = daily.assign(on_hand=list(on_hand_series)).dropna(subset=["on_hand"])
    violations = checked[checked["sum"] > checked["on_hand"]]
    assert violations.empty, f"{len(violations)} in-scope Store-SKU-days sell more than Inventory_On_Hand: {violations.head()}"

    zero_inv_keys = {k for k, v in inv_map.items() if v == 0}
    sold_on_zero_inv = [k for k in daily.index if k in zero_inv_keys]
    assert not sold_on_zero_inv, f"{len(sold_on_zero_inv)} in-scope Store-SKU-days sold on a 0 on-hand day: {sold_on_zero_inv[:5]}"

    basket_check = df.groupby("Txn_ID")["Txn_ID"].transform("size")
    assert (basket_check == df["Basket_Size"]).all(), "Basket_Size out of sync with actual Txn_ID line counts."

    dup_line = df["Line_ID"].duplicated().sum()
    assert dup_line == 0, f"{dup_line} duplicate Line_ID values."
    dup_txn_store = df.groupby("Txn_ID")["Store_ID"].nunique()
    assert (dup_txn_store <= 1).all(), "Some Txn_ID spans more than one Store_ID."

    log.info(f"  [OK] Validation passed for {len(in_scope_pairs):,} in-scope pairs: "
             f"no day exceeds {MAX_RECORDS_PER_DAY} records, no day sells more than "
             f"Inventory_On_Hand, no sale recorded on a 0 on-hand day, Basket_Size "
             f"consistent, {dup_line} duplicate Line_IDs, no cross-store Txn_ID.")


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
    log.info("Sales_Tx 12-Month Daily Enrichment & Inventory-Alignment Module")
    log.info("=" * 60)

    tx = _load_sales()
    inv = _load_inventory()
    sku = _load_sku()
    store = _load_store()

    in_scope_pairs = set(map(tuple, inv[["Store_ID", "SKU_ID"]].drop_duplicates().to_numpy()))
    pairs_list = sorted(in_scope_pairs)
    log.info(f"STEP: Loaded {len(tx):,} Sales_Tx rows, {len(inv):,} Inventory_Report rows. "
             f"In-scope: {len(in_scope_pairs):,} of {tx.groupby(['Store_ID','SKU_ID']).ngroups:,} "
             f"total Store_ID x SKU_ID pairs (matching Inventory_Report's coverage).")

    in_scope_mask = tx.set_index(["Store_ID", "SKU_ID"]).index.isin(in_scope_pairs)
    tx_in_scope = tx[in_scope_mask].reset_index(drop=True)
    tx_out_of_scope = tx[~in_scope_mask].reset_index(drop=True)
    log.info(f"  {len(tx_in_scope):,} rows in-scope (590 pairs) will be reconciled; "
             f"{len(tx_out_of_scope):,} rows for the 310 legacy pairs are left untouched.")

    max_line = tx["Line_ID"].str.replace("LN", "", regex=False).astype(int).max()
    max_txn  = tx["Txn_ID"].str.replace("TXN", "", regex=False).astype(int).max()
    counters = {"line": max_line, "txn": max_txn}

    def next_ids():
        counters["line"] += 1
        counters["txn"] += 1
        return f"LN{counters['line']:06d}", f"TXN{counters['txn']:05d}"

    inv_map = dict(zip(zip(inv["Date"], inv["Store_ID"], inv["SKU_ID"]), inv["Inventory_On_Hand"]))

    log.info("STEP: Reconciling existing in-scope rows (max-4/day, inventory cap)")
    tx_reconciled = reconcile_existing(tx_in_scope, inv_map, next_ids)

    log.info("STEP: Calibrating per-pair daily sell-through rate and zero-sale rate")
    rate_map, global_rate = compute_pair_daily_rate(inv)
    n_hist_days = tx_in_scope["Date"].nunique()
    zero_rate_map = compute_pair_zero_sale_rate(tx_in_scope, pairs_list, n_hist_days)
    pools = build_bootstrap_pools(tx_in_scope, sku["SKU_ID"].unique().tolist())
    log.info(f"  Network-wide fallback daily rate: {global_rate:.2f} units/day. "
             f"Historical window: {n_hist_days} days.")

    sku_meta = sku.set_index("SKU_ID")[["Brand", "Sub_Category"]].to_dict(orient="index")
    abc_map = tx_in_scope.groupby("SKU_ID")["ABC_Class"].agg(lambda s: s.mode().iloc[0]).to_dict()
    for sid in sku_meta:
        sku_meta[sid]["ABC_Class"] = abc_map.get(sid, "C")
        sku_meta[sid]["List_Price_USD"] = sku.set_index("SKU_ID").loc[sid, "List_Price_USD"]
    store_meta = store.set_index("Store_ID")[["Geography"]].to_dict(orient="index")

    existing_days = (tx_reconciled.groupby(["Store_ID", "SKU_ID"])["Date"]
                     .agg(set).to_dict())
    date_strs = pd.date_range(START_DATE, END_DATE, freq="D").strftime("%Y-%m-%d").tolist()

    log.info(f"STEP: Generating new transaction lines for missing days ({START_DATE} .. {END_DATE})")
    new_rows = generate_missing_days(pairs_list, existing_days, inv_map, rate_map,
                                      zero_rate_map, pools, sku_meta, store_meta,
                                      date_strs, next_ids)

    combined = pd.concat([tx_out_of_scope, tx_reconciled, new_rows], ignore_index=True)
    combined["Units_Sold"] = pd.to_numeric(combined["Units_Sold"], errors="coerce").fillna(0).astype("int64")
    combined["Unit_Price_USD"] = pd.to_numeric(combined["Unit_Price_USD"], errors="coerce").astype("float64")
    combined["Promo_Flag"] = pd.to_numeric(combined["Promo_Flag"], errors="coerce").fillna(0).astype("int64")

    log.info("STEP: Finalizing (Cost_Price, Net_Sales/Gross_Margin recompute, Basket_Size)")
    unit_cost = dict(zip(sku["SKU_ID"], sku["Unit_Cost_USD"]))
    combined = finalize(combined, unit_cost)

    combined = combined.sort_values(["Date", "Store_ID", "SKU_ID", "Txn_ID"]).reset_index(drop=True)
    combined = combined[["Line_ID", "Txn_ID", "Date", "SKU_ID", "Brand", "Sub_Category",
                          "ABC_Class", "Store_ID", "Channel", "Geography", "Units_Sold",
                          "Unit_Price_USD", "Cost_Price", "Net_Sales_USD", "Gross_Margin_USD",
                          "Promo_Flag", "Basket_Size"]]

    log.info("STEP: Validating alignment against Inventory_Report")
    validate(combined, in_scope_pairs, inv_map)

    combined.to_csv(SALES_CSV, index=False)
    log.info(f"  [OK] Saved: {os.path.basename(SALES_CSV)} "
             f"({len(combined):,} rows, {len(combined.columns)} cols, was {len(tx):,} rows)")

    _load_to_postgres(combined)

    log.info("=" * 60)
    log.info("Sales_Tx 12-Month Daily Enrichment & Inventory-Alignment Module complete.")
    return combined


if __name__ == "__main__":
    main()
