"""
connection.py — Centralized PostgreSQL connection for all Backend modules.

Reads connection parameters from the project-root .env file.
Provides read_table_or_csv() which tries PostgreSQL first and falls back
to the CSV/XLSX path when the table is absent or the DB is unreachable.
"""
import logging
import os
from functools import lru_cache
from pathlib import Path

import pandas as pd

try:
    from ..config.settings import load_env
except ImportError:
    # Standalone pipeline scripts import this module flatly (via a sys.path
    # hack that adds Backend/ to sys.path), which doesn't support relative
    # imports — fall back to an absolute import in that context.
    from config.settings import load_env

log = logging.getLogger(__name__)

load_env()

_PG_HOST = os.getenv("PGHOST",     "localhost")
_PG_PORT = os.getenv("PGPORT",     "5432")
_PG_DB   = os.getenv("PGDATABASE", "Assortment")
_PG_USER = os.getenv("PGUSER",     "postgres")
_PG_PASS = os.getenv("PGPASSWORD", "")


@lru_cache(maxsize=1)
def get_engine():
    """Return a cached SQLAlchemy engine for the PostgreSQL database."""
    from sqlalchemy import create_engine
    url = (
        f"postgresql+psycopg2://{_PG_USER}:{_PG_PASS}"
        f"@{_PG_HOST}:{_PG_PORT}/{_PG_DB}"
    )
    return create_engine(url, pool_pre_ping=True)


def _try_table(table: str):
    """
    Try SELECT * from table (exact name, then lowercase).
    Returns a DataFrame on success, None on any failure.
    """
    from sqlalchemy import text
    candidates = list(dict.fromkeys([table, table.lower()]))
    for t in candidates:
        try:
            with get_engine().connect() as conn:
                result = conn.execute(text(f'SELECT * FROM "{t}"'))
                df = pd.DataFrame(result.fetchall(), columns=list(result.keys()))
                log.debug("PostgreSQL read: table=%s rows=%d", t, len(df))
                return df
        except Exception:
            continue
    return None


def _reconcile_columns(pg_df: pd.DataFrame, csv_path: Path) -> pd.DataFrame:
    """
    When PG returns lowercase column names but downstream code expects the
    original CSV column capitalisation, rename PG columns to match the CSV header.
    Only renames when a case-insensitive match exists; leaves unmatched columns as-is.

    A CSV can legitimately have two columns whose names differ only by case
    (e.g. Store_Master.csv's Store_Size_SqFt vs Store_Size_Sqft — a
    categorical band and a numeric value). PostgreSQL preserves both as
    distinct quoted columns, so collapsing them into one case-insensitive
    lookup entry would rename both PG columns to the same label. Such
    ambiguous keys are excluded from the lookup, and a PG column already
    matching a CSV column exactly is left untouched.
    """
    csv_path = Path(csv_path)
    if not csv_path.exists():
        return pg_df
    try:
        csv_header = pd.read_csv(csv_path, nrows=0).columns.tolist()
    except Exception:
        return pg_df

    csv_header_set = set(csv_header)
    lower_counts: dict = {}
    for c in csv_header:
        lower_counts[c.lower()] = lower_counts.get(c.lower(), 0) + 1
    csv_lower_map = {c.lower(): c for c in csv_header if lower_counts[c.lower()] == 1}

    rename = {
        c: csv_lower_map[c.lower()]
        for c in pg_df.columns
        if c not in csv_header_set and c.lower() in csv_lower_map
    }
    if rename:
        log.debug("Renaming PG columns to match CSV header: %s", rename)
        pg_df = pg_df.rename(columns=rename)
    return pg_df


def read_table_or_csv(table: str, csv_path: Path) -> pd.DataFrame:
    """
    Try PostgreSQL first; fall back to the CSV/XLSX flat file when the table
    is absent or the database is unreachable.

    Parameters
    ----------
    table    : PostgreSQL table name (case-insensitive lookup applied).
    csv_path : Absolute path to the fallback flat file.
    """
    df = _try_table(table)
    if df is not None:
        return _reconcile_columns(df, csv_path)

    csv_path = Path(csv_path)
    if csv_path.exists():
        log.info("PG table '%s' not found — falling back to %s", table, csv_path.name)
        suffix = csv_path.suffix.lower()
        if suffix in (".xlsx", ".xls"):
            return pd.read_excel(csv_path)
        return pd.read_csv(csv_path)

    log.warning(
        "Neither PG table '%s' nor file '%s' exists; returning empty DataFrame.",
        table, csv_path,
    )
    return pd.DataFrame()
