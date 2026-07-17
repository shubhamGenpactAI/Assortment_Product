"""
agent_llm.py
============
Generic OpenAI streaming helper used by all three agents.
Parameterized by system prompt so each agent keeps its own voice.

Existing llm_service.py is UNCHANGED — this is a separate module.
"""
import json
import os
from typing import AsyncGenerator

from ..config.settings import load_env
from ..tools.guardrails import is_injection, REFUSAL

load_env()

OPENAI_API_KEY  = os.getenv("OPENAI_API_KEY", "")
LLM_MODEL       = os.getenv("LLM_MODEL", "o3-mini")
AGENT_MAX_TOKENS = int(os.getenv("AGENT_LLM_MAX_TOKENS", "1200"))


async def stream_agent_response(
    system_prompt: str,
    context: dict,
    question: str = "",
) -> AsyncGenerator[str, None]:
    """
    Async generator — yields SSE strings identical to llm_service.stream_copilot:
      'data: <token>\\n\\n'  |  'data: [DONE]\\n\\n'  |  'data: [ERROR: ...]\\n\\n'
    """
    if not OPENAI_API_KEY:
        yield "data: [ERROR: OPENAI_API_KEY not configured in .env]\n\n"
        return

    if question and is_injection(question):
        yield f"data: {REFUSAL}\n\n"
        yield "data: [DONE]\n\n"
        return

    try:
        from openai import AsyncOpenAI
        import httpx
    except ImportError:
        yield "data: [ERROR: openai package not installed — run: pip install openai]\n\n"
        return

    from ..integrations.openai_client import _resolve_ca_bundle

    http_client = httpx.AsyncClient(verify=_resolve_ca_bundle())

    client = AsyncOpenAI(
        api_key=OPENAI_API_KEY,
        **({"http_client": http_client} if http_client else {}),
    )

    ctx_str  = json.dumps(context, indent=2, default=str)
    user_msg = f"Data context:\n{ctx_str}"
    if question:
        user_msg += f"\n\nRequest: {question}"

    try:
        stream = await client.chat.completions.create(
            model=LLM_MODEL,
            max_completion_tokens=AGENT_MAX_TOKENS,
            stream=True,
            extra_body={"reasoning_effort": "medium"},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_msg},
            ],
        )

        async for chunk in stream:
            delta = chunk.choices[0].delta.content if chunk.choices else None
            if delta:
                safe = delta.replace("\n", "\\n")
                yield f"data: {safe}\n\n"

        yield "data: [DONE]\n\n"

    except Exception as exc:
        yield f"data: [ERROR: {str(exc)[:120]}]\n\n"

    finally:
        if http_client:
            await http_client.aclose()
