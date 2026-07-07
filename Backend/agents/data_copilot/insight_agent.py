"""
insight_agent.py
=================
Agent 4: Insight generation.

Given the user's question and the ACTUAL rows retrieved by Agent 3 (never
anything else), streams a grounded final answer. The system prompt
(prompts/data_copilot_prompts.py::INSIGHT_AGENT_PROMPT) hard-enforces
answering only from the provided data and citing sources — the same
guardrail-first pattern already proven in prompts/copilot_system_prompt.py.

Yields raw text deltas (no SSE framing — orchestrator.py owns that).
"""
import json
from typing import AsyncGenerator

import pandas as pd

from ...integrations.openai_client import stream_text
from ...prompts.data_copilot_prompts import INSIGHT_AGENT_PROMPT

MAX_ROWS_TO_MODEL = 200


def _rows_for_model(df: pd.DataFrame) -> tuple[list[dict], bool]:
    shown = df.head(MAX_ROWS_TO_MODEL).copy()
    for col in shown.columns:
        if pd.api.types.is_datetime64_any_dtype(shown[col]):
            shown[col] = shown[col].astype(str)
    records = shown.where(pd.notna(shown), None).to_dict(orient="records")
    truncated_for_model = len(df) > MAX_ROWS_TO_MODEL
    return records, truncated_for_model


async def stream_answer(
    question: str,
    df: pd.DataFrame,
    *,
    sql_used: str,
    sources_used: list[str],
) -> AsyncGenerator[str, None]:
    records, truncated_for_model = _rows_for_model(df)

    payload = {
        "question": question,
        "sources_used": sources_used,
        "sql_used": sql_used,
        "row_count": len(df),
        "rows_shown_to_you": len(records),
        "note": (
            f"Only the first {MAX_ROWS_TO_MODEL} of {len(df)} rows are shown "
            "below; the row_count above reflects the true total."
            if truncated_for_model else None
        ),
        "data": records,
    }

    async for delta in stream_text(
        INSIGHT_AGENT_PROMPT,
        json.dumps(payload, indent=2, default=str),
        max_tokens=1200,
        reasoning_effort="medium",
    ):
        yield delta
