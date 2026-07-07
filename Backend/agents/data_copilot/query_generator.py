"""
query_generator.py
===================
Agent 2: Query Generation.

Given the user's question and the FULL schema + sample rows + business
notes for only the sources the Intent & Routing Agent selected, generates
one validated-shape SQL query (DuckDB dialect). Supports a retry mode: if
the previously-generated SQL failed validation or execution, the error is
fed back so the model can fix that specific problem rather than starting
over blind.
"""
import json
from dataclasses import dataclass

from ...integrations.openai_client import call_json
from ...prompts.data_copilot_prompts import QUERY_GENERATOR_PROMPT
from . import catalog

QUERY_SCHEMA = {
    "type": "object",
    "properties": {
        "sql": {
            "type": ["string", "null"],
            "description": "The DuckDB SELECT query, or null if unanswerable from the given schema.",
        },
        "tables_used": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Exact source names referenced in the SQL (subset of the sources provided).",
        },
        "rationale": {
            "type": "string",
            "description": "One or two sentences on how the query answers the question (explainability).",
        },
        "reason": {
            "type": ["string", "null"],
            "description": "If sql is null, why the question can't be answered from the given schema.",
        },
    },
    "required": ["sql", "tables_used", "rationale", "reason"],
    "additionalProperties": False,
}


@dataclass
class QueryResult:
    sql: str | None
    tables_used: list[str]
    rationale: str
    reason: str | None


async def generate_sql(
    question: str,
    sources: list[str],
    *,
    prior_sql: str | None = None,
    prior_error: str | None = None,
) -> QueryResult:
    detail = catalog.get_source_detail(sources)

    payload: dict = {
        "question": question,
        "sources": detail,
    }
    if prior_sql and prior_error:
        payload["previous_attempt"] = {"sql": prior_sql, "error": prior_error}

    result = await call_json(
        QUERY_GENERATOR_PROMPT,
        json.dumps(payload, indent=2, default=str),
        schema_name="sql_generation",
        schema=QUERY_SCHEMA,
        max_tokens=1200,
        reasoning_effort="medium",
    )

    return QueryResult(
        sql=result.get("sql"),
        tables_used=[t for t in result.get("tables_used", []) if t in sources],
        rationale=result.get("rationale", ""),
        reason=result.get("reason"),
    )
