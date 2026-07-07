"""
llm_service.py
==============
Thin backward-compatible delegator to the Data-Access Copilot orchestrator
(Backend/agents/data_copilot/orchestrator.py). Kept as a stable import
point — its call signature and SSE-generator return shape are unchanged
from the previous single-shot implementation.

The `context` param (a build_copilot_context() snapshot) is only used to
recover the filters the caller had applied; the orchestrator does its own
data routing/retrieval per question rather than relying on a fixed
pre-trimmed context payload. New callers should prefer calling
agents.data_copilot.orchestrator.run_copilot() directly, which also
accepts a trace_id for the companion /copilot/explain endpoint.
"""
from ..agents.data_copilot import orchestrator


async def stream_copilot(context: dict, question: str = ""):
    """
    Async generator that yields Server-Sent Event strings.
    Each chunk is:  'data: <text>\\n\\n'
    Terminator  :  'data: [DONE]\\n\\n'
    Error       :  'data: [ERROR: ...]\\n\\n'

    Caller wraps this in a FastAPI StreamingResponse.
    """
    filters = context.get("filters_applied", {}) if isinstance(context, dict) else {}
    async for chunk in orchestrator.run_copilot(question, filters):
        yield chunk
