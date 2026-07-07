"""
catalog.py
==========
Data catalog for the Data-Access Copilot.

Combines the hand-curated business metadata in
Backend/config/data_catalog.yaml (description, join keys, business notes)
with LIVE schema + sample rows fetched through the existing
read_table_or_csv() (PG-first, CSV-fallback, column-casing already
reconciled) — so the schema shown to the LLM can never drift from what
the pipeline actually retrieves at execution time.

Two entry points:
  get_catalog_index()      -> cheap {name, kind, description} list for
                               every source. Used by the Intent & Routing
                               Agent, which only needs to pick sources.
  get_source_detail(names) -> full schema + sample rows + business notes
                               for a specific set of sources. Used by the
                               Query Generation Agent once routing is done.
  get_dataframe(name)      -> the actual DataFrame for execution. Used by
                               the Data Retrieval Agent. Backed by the
                               same cache as get_source_detail(), so the
                               samples shown to the LLM are drawn from
                               the exact data it will query.
"""
import time
from pathlib import Path
from typing import Any

import pandas as pd
import yaml

from ...database.connection import read_table_or_csv

_HERE        = Path(__file__).resolve().parent          # Backend/agents/data_copilot/
_BACKEND_DIR = _HERE.parent.parent                       # Backend/
_PROJ        = _BACKEND_DIR.parent                       # Assortment/
_CATALOG_YAML = _BACKEND_DIR / "config" / "data_catalog.yaml"

_DF_TTL_SECONDS = 300  # re-fetch a source's data at most every 5 minutes
_SAMPLE_ROWS    = 5

_df_cache: dict[str, tuple[float, pd.DataFrame]] = {}


def _load_sources() -> dict[str, dict]:
    with open(_CATALOG_YAML, encoding="utf-8") as fh:
        return yaml.safe_load(fh)["sources"]


_SOURCES = _load_sources()


def _csv_path(rel: str) -> Path:
    return _PROJ / rel


def _get_df(name: str) -> pd.DataFrame:
    """Fetch (and cache) the DataFrame for a catalog source by name."""
    if name not in _SOURCES:
        raise KeyError(f"Unknown data source: {name!r}")

    now = time.time()
    cached = _df_cache.get(name)
    if cached is not None and (now - cached[0]) < _DF_TTL_SECONDS:
        return cached[1]

    src = _SOURCES[name]
    df = read_table_or_csv(src["table"], _csv_path(src["csv"]))
    _df_cache[name] = (now, df)
    return df


def refresh_cache(names: list[str] | None = None) -> None:
    """Drop cached DataFrames so the next access re-fetches. Mirrors the
    existing /api/agents/admin/refresh-cache pattern."""
    if names is None:
        _df_cache.clear()
    else:
        for n in names:
            _df_cache.pop(n, None)


def get_catalog_index() -> list[dict[str, str]]:
    """Cheap listing of every known source — for the Intent & Routing Agent."""
    return [
        {"name": name, "kind": meta["kind"], "description": meta["description"]}
        for name, meta in _SOURCES.items()
    ]


def _jsonable_sample(df: pd.DataFrame, n: int) -> list[dict[str, Any]]:
    sample = df.head(n).copy()
    for col in sample.columns:
        if pd.api.types.is_datetime64_any_dtype(sample[col]):
            sample[col] = sample[col].astype(str)
    return sample.where(pd.notna(sample), None).to_dict(orient="records")


def get_source_detail(names: list[str]) -> dict[str, dict[str, Any]]:
    """Full schema + sample rows + business metadata for the given sources
    only — used by the Query Generation Agent so prompt size scales with
    what's actually needed for one question, not the whole catalog."""
    detail: dict[str, dict[str, Any]] = {}
    for name in names:
        if name not in _SOURCES:
            continue
        meta = _SOURCES[name]
        df = _get_df(name)
        detail[name] = {
            "description":      meta["description"],
            "join_keys":        meta.get("join_keys", []),
            "business_notes":   meta.get("business_notes", ""),
            "columns":          [{"name": c, "dtype": str(df[c].dtype)} for c in df.columns],
            "sample_rows":      _jsonable_sample(df, _SAMPLE_ROWS),
            "row_count_cached": len(df),
        }
    return detail


def get_dataframe(name: str) -> pd.DataFrame:
    """The real DataFrame for a source, for the Data Retrieval Agent to
    register into DuckDB. Backed by the same cache as get_source_detail()."""
    return _get_df(name)


def known_source_names() -> set[str]:
    return set(_SOURCES.keys())
