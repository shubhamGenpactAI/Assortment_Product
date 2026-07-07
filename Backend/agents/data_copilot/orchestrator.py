"""
orchestrator.py
================
Wires the 4 Data-Access Copilot agents together into one request flow,
and is the only piece that speaks the SSE wire format
('data: <text>\\n\\n' / 'data: [DONE]\\n\\n' / 'data: [ERROR: ...]\\n\\n')
that Backend/api/decision_hub.py's StreamingResponse and the existing
frontend (Frontend/src/api/decisionHubApi.ts::streamCopilot) already
expect — so no frontend change is required.

Flow per question:
  1. Layer-1 guardrail (tools.guardrails.is_injection) on the raw question.
  2. Intent & Routing Agent decides whether data is needed and which
     catalog sources are relevant.
  3. Query Generation Agent writes SQL against those sources' schemas.
  4. Data Retrieval Agent validates + executes it in DuckDB (1 retry on
     validation/execution failure, feeding the error back to step 3).
  5. Insight Agent streams the final answer grounded in the retrieved
     rows, then a "Sources: ..." line is appended so provenance is
     visible in the answer itself with zero frontend changes.

A structured trace (intent, sources, SQL, row counts, retries, errors) is
kept per trace_id for the companion GET /copilot/explain/{trace_id}
endpoint (api/decision_hub.py).
"""
import logging
import uuid
from collections import OrderedDict
from typing import AsyncGenerator

from ...tools.guardrails import REFUSAL, is_injection
from . import data_retriever, insight_agent, intent_router, query_generator
from .sql_guardrails import SQLValidationError

log = logging.getLogger(__name__)

MAX_QUERY_ATTEMPTS = 2  # 1 initial + 1 retry
_MAX_TRACES = 200
_traces: "OrderedDict[str, dict]" = OrderedDict()


def new_trace_id() -> str:
    return uuid.uuid4().hex


def get_trace(trace_id: str) -> dict | None:
    return _traces.get(trace_id)


def _store_trace(trace_id: str, trace: dict) -> None:
    _traces[trace_id] = trace
    _traces.move_to_end(trace_id)
    while len(_traces) > _MAX_TRACES:
        _traces.popitem(last=False)


def _sse(text: str) -> str:
    return f"data: {text.replace(chr(10), chr(92) + 'n')}\n\n"


async def run_copilot(
    question: str,
    filters: dict | None = None,
    *,
    trace_id: str | None = None,
) -> AsyncGenerator[str, None]:
    trace_id = trace_id or new_trace_id()
    filters = filters or {}
    trace: dict = {
        "trace_id": trace_id,
        "question": question,
        "filters": filters,
        "intent": None,
        "sources_used": [],
        "sql_used": None,
        "row_count": None,
        "retries": 0,
        "errors": [],
        "status": "started",
    }

    try:
        if question and is_injection(question):
            yield _sse(REFUSAL)
            yield "data: [DONE]\n\n"
            trace["status"] = "refused_injection"
            return

        routing = await intent_router.route(question)
        trace["intent"] = routing.intent

        if not routing.needs_data:
            yield _sse(REFUSAL)
            yield "data: [DONE]\n\n"
            trace["status"] = "refused_out_of_scope"
            return

        sources = [s.name for s in routing.sources]
        trace["sources_used"] = sources

        prior_sql: str | None = None
        prior_error: str | None = None
        retrieval = None
        query_result = None

        for attempt in range(1, MAX_QUERY_ATTEMPTS + 1):
            query_result = await query_generator.generate_sql(
                question, sources, prior_sql=prior_sql, prior_error=prior_error,
            )

            if not query_result.sql:
                trace["status"] = "unanswerable"
                trace["errors"].append(query_result.reason or "Query Generation Agent returned no SQL.")
                msg = (
                    "I can only answer questions based on the insights and data available "
                    f"in this application. {query_result.reason or ''}".strip()
                )
                yield _sse(msg)
                yield "data: [DONE]\n\n"
                return

            trace["sql_used"] = query_result.sql
            try:
                retrieval = data_retriever.execute(query_result.sql, query_result.tables_used or sources)
                break
            except SQLValidationError as exc:
                trace["errors"].append(f"attempt {attempt} validation error: {exc}")
                prior_sql, prior_error = query_result.sql, str(exc)
                retrieval = None
            except data_retriever.DataRetrievalError as exc:
                trace["errors"].append(f"attempt {attempt} execution error: {exc}")
                prior_sql, prior_error = query_result.sql, str(exc)
                retrieval = None

            trace["retries"] = attempt

        if retrieval is None:
            trace["status"] = "retrieval_failed"
            yield _sse(
                "I found the relevant data sources but couldn't build a valid query for this "
                "question. Please try rephrasing it."
            )
            yield "data: [DONE]\n\n"
            return

        trace["row_count"] = retrieval.row_count
        trace["sources_used"] = query_result.tables_used or sources

        async for delta in insight_agent.stream_answer(
            question,
            retrieval.dataframe,
            sql_used=retrieval.validated_sql,
            sources_used=trace["sources_used"],
        ):
            yield _sse(delta)

        yield _sse(f"\n\nSources: {', '.join(f'`{s}`' for s in trace['sources_used'])}")
        yield "data: [DONE]\n\n"
        trace["status"] = "answered"

    except Exception as exc:  # pragma: no cover - defensive, matches existing agent error handling
        log.exception("Data copilot pipeline failed")
        trace["status"] = "error"
        trace["errors"].append(str(exc))
        yield f"data: [ERROR: {str(exc)[:120]}]\n\n"

    finally:
        _store_trace(trace_id, trace)
