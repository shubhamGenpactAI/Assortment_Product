"""
sql_guardrails.py
==================
Security validation for LLM-generated SQL before it ever reaches DuckDB.

This is the hard security boundary for the Data-Access Copilot: even
though the SQL only ever runs against an in-memory DuckDB session (never
the live Postgres connection — see data_retriever.py), a query generator
model can still hallucinate destructive or out-of-scope SQL, so every
query is parsed into a real AST (via sqlglot) and checked before
execution, not just regex-matched.

Rejects:
  - Anything that isn't exactly one top-level SELECT statement (no
    multi-statement `;`-chains, no DDL/DML such as INSERT/UPDATE/DELETE/
    DROP/ALTER/CREATE/ATTACH/COPY/PRAGMA).
  - Any table/view reference that isn't in the caller-supplied whitelist
    (i.e. exactly the sources the Intent & Routing Agent selected for
    this question) — CTE-local aliases are exempted since they aren't
    external references.

Also enforces a row cap by injecting LIMIT when the query doesn't already
have one (safe no-op for aggregate/scalar queries that already return few
rows; caps unbounded raw SELECTs).
"""
import sqlglot
from sqlglot import exp

DIALECT = "duckdb"


class SQLValidationError(Exception):
    """Raised when generated SQL fails a security/shape check."""


_FORBIDDEN_TYPES = (
    exp.Insert, exp.Update, exp.Delete, exp.Drop, exp.Create, exp.Alter,
    exp.Command, exp.Merge, exp.Copy, exp.Attach,
    getattr(exp, "Truncate", ()),  # not all sqlglot versions define every node
)


def validate_and_prepare(sql: str, allowed_sources: set[str], *, row_limit: int = 2000) -> str:
    """
    Validate `sql` against the security rules above and return the
    (possibly LIMIT-augmented) SQL string, ready to execute.

    Raises SQLValidationError with a human-readable reason on any
    violation — callers (data_retriever.py) feed that reason back to the
    Query Generation Agent for a retry.
    """
    sql = (sql or "").strip()
    while sql.endswith(";"):
        sql = sql[:-1].strip()
    if not sql:
        raise SQLValidationError("Empty SQL.")

    try:
        statements = [s for s in sqlglot.parse(sql, dialect=DIALECT) if s is not None]
    except Exception as exc:
        raise SQLValidationError(f"SQL failed to parse: {exc}") from exc

    if len(statements) != 1:
        raise SQLValidationError(
            f"Expected exactly one SQL statement, found {len(statements)} "
            "(multi-statement / `;`-chained SQL is not allowed)."
        )

    stmt = statements[0]

    if isinstance(stmt, _FORBIDDEN_TYPES) or not isinstance(stmt, exp.Select):
        raise SQLValidationError(
            f"Only single SELECT statements are allowed; got {type(stmt).__name__}."
        )

    # Defense in depth: reject if any forbidden node type appears anywhere
    # in the tree (e.g. hidden inside an unexpected construct).
    for node in stmt.walk():
        node_expr = node[0] if isinstance(node, tuple) else node
        if isinstance(node_expr, _FORBIDDEN_TYPES):
            raise SQLValidationError(
                f"Disallowed SQL construct found: {type(node_expr).__name__}."
            )

    cte_names = {cte.alias.lower() for cte in stmt.find_all(exp.CTE)}
    referenced_tables = {t.name.lower() for t in stmt.find_all(exp.Table)}
    external_tables = referenced_tables - cte_names

    allowed_lower = {s.lower() for s in allowed_sources}
    unauthorized = external_tables - allowed_lower
    if unauthorized:
        raise SQLValidationError(
            f"Query references source(s) not in the routed set: {sorted(unauthorized)}. "
            f"Allowed: {sorted(allowed_lower)}."
        )

    if stmt.args.get("limit") is None:
        stmt = stmt.limit(row_limit)

    return stmt.sql(dialect=DIALECT)
