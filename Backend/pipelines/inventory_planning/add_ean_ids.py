"""
add_ean_ids.py
===============
One-off data-augmentation script: adds an EAN_ID column (synthetic but
checksum-valid EAN-13 barcodes) to Raw_Input/SKU_Master.csv and
Raw_Input/New_SKUs.csv, keyed deterministically off each row's SKU_ID so
re-running this script is idempotent and reproducible.

No raw input file carries a barcode/EAN field anywhere in this project —
this generates one, it does not source real GS1 barcode data.

Run:
    python add_ean_ids.py
"""
import os
import sys

import pandas as pd

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.dirname(BASE_DIR)))
RAW_DIR = os.path.join(PROJECT_DIR, "Raw_Input")

_BACKEND_DIR = os.path.dirname(os.path.dirname(BASE_DIR))
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)
try:
    from database.connection import get_engine
    _DB_AVAILABLE = True
except ImportError:
    _DB_AVAILABLE = False

SKU_CSV = os.path.join(RAW_DIR, "SKU_Master.csv")
NEW_SKU_CSV = os.path.join(RAW_DIR, "New_SKUs.csv")

# PG tables that mirror these CSVs — read_table_or_csv() reads PG first, so a
# stale PG table would silently shadow the new EAN_ID column added below.
_PG_TABLES = {SKU_CSV: "sku_master", NEW_SKU_CSV: "new_skus"}

# Synthetic GS1-style company prefix. Real EAN-13 prefixes are assigned by
# GS1; this is a placeholder so generated codes are visually barcode-shaped
# without colliding with any real product's registered EAN.
_COMPANY_PREFIX = "890"


def _ean13_check_digit(digits12: str) -> str:
    total = 0
    for i, ch in enumerate(digits12):
        d = int(ch)
        total += d * (3 if i % 2 == 1 else 1)
    return str((10 - (total % 10)) % 10)


def _make_ean(seq: int) -> str:
    body = f"{_COMPANY_PREFIX}{seq:09d}"  # 3 + 9 = 12 digits
    return body + _ean13_check_digit(body)


def _add_ean_ids(csv_path: str, seq_offset: int) -> None:
    df = pd.read_csv(csv_path)
    if "EAN_ID" in df.columns:
        print(f"  {os.path.basename(csv_path)}: EAN_ID already present, skipping.")
        return
    order = df["SKU_ID"].sort_values().tolist()
    ean_by_sku = {sku_id: _make_ean(seq_offset + i) for i, sku_id in enumerate(order)}
    insert_at = df.columns.get_loc("SKU_ID") + 1
    df.insert(insert_at, "EAN_ID", df["SKU_ID"].map(ean_by_sku))
    df.to_csv(csv_path, index=False)
    print(f"  {os.path.basename(csv_path)}: added EAN_ID for {len(df)} rows.")


def _sa_type_for(dtype):
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


def _reload_postgres_table(csv_path: str, table: str) -> None:
    """
    Drops and recreates `table` from the current CSV content, so a table that
    predates this script's EAN_ID column (or any other manual CSV edit) picks
    up the new column instead of read_table_or_csv() silently serving the
    stale PG schema.
    """
    if not _DB_AVAILABLE:
        print(f"  DB module unavailable — skipping PostgreSQL reload of '{table}'.")
        return
    try:
        from sqlalchemy import Column, MetaData, Table

        df = pd.read_csv(csv_path)
        engine = get_engine()
        meta = MetaData()
        cols = [Column(c, _sa_type_for(df[c].dtype)) for c in df.columns]
        sa_table = Table(table, meta, *cols)
        records = df.where(pd.notnull(df), None).to_dict(orient="records")

        with engine.begin() as conn:
            sa_table.drop(conn, checkfirst=True)
            sa_table.create(conn)
            if records:
                conn.execute(sa_table.insert(), records)
        print(f"  [OK] Reloaded PostgreSQL table '{table}' ({len(df)} rows, {len(df.columns)} cols).")
    except Exception as e:
        print(f"  PostgreSQL reload of '{table}' skipped (unreachable or failed): {e}")


def main() -> None:
    print("Adding EAN_ID columns")
    print("=" * 40)
    _add_ean_ids(SKU_CSV, seq_offset=1)
    _add_ean_ids(NEW_SKU_CSV, seq_offset=100_000)  # disjoint range, no collisions with SKU_Master

    print("Syncing PostgreSQL tables to current CSV content")
    for csv_path, table in _PG_TABLES.items():
        _reload_postgres_table(csv_path, table)
    print("Done.")


if __name__ == "__main__":
    main()
