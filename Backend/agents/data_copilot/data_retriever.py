"""
data_retriever.py
==================
Agent 3: Data Retrieval.

Deterministic (no LLM call). Validates the generated SQL, materializes
only the routed sources into a fresh in-memory DuckDB connection via the
existing catalog.get_dataframe() (itself backed by the unchanged
read_table_or_csv()), executes the query, and returns the resulting rows.

The generated SQL never touches the live Postgres connection — DuckDB
here holds copies of the routed DataFrames only, for the lifetime of this
one request.
"""
import threading
from dataclasses import dataclass

import duckdb
import pandas as pd

from . import catalog
from .sql_guardrails import validate_and_prepare

DEFAULT_ROW_LIMIT = 2000
DEFAULT_TIMEOUT_SECONDS = 20


class DataRetrievalError(Exception):
    """Raised when a validated query fails to execute against DuckDB."""


@dataclass
class RetrievalResult:
    dataframe: pd.DataFrame
    row_count: int
    validated_sql: str
    truncated: bool


def execute(
    sql: str,
    sources: list[str],
    *,
    row_limit: int = DEFAULT_ROW_LIMIT,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> RetrievalResult:
    """
    Validate + execute `sql` against DuckDB views registered for `sources`.

    Raises SQLValidationError (bad/unauthorized SQL, caught before
    execution) or DataRetrievalError (DuckDB failed to run valid-shaped
    SQL, e.g. unknown column) — both are retryable by feeding the message
    back into query_generator.generate_sql().
    """
    validated_sql = validate_and_prepare(sql, set(sources), row_limit=row_limit)

    conn = duckdb.connect(database=":memory:")
    timer = threading.Timer(timeout_seconds, conn.interrupt)
    try:
        for name in sources:
            conn.register(name, catalog.get_dataframe(name))

        timer.start()
        result_df = conn.execute(validated_sql).fetch_df()
    except duckdb.Error as exc:
        raise DataRetrievalError(str(exc)) from exc
    finally:
        timer.cancel()
        conn.close()

    row_count = len(result_df)
    return RetrievalResult(
        dataframe=result_df,
        row_count=row_count,
        validated_sql=validated_sql,
        truncated=row_count >= row_limit,
    )
