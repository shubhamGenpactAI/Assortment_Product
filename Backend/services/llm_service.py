"""
llm_service.py
==============
OpenAI-backed LLM streaming for the AI Copilot panel.
Model : o3-mini  (override via LLM_MODEL env var)
Auth  : OPENAI_API_KEY in .env at the project root
"""

import json
import os

from ..config.settings import load_env
from ..prompts.copilot_system_prompt import SYSTEM_PROMPT
from ..tools.guardrails import is_injection, REFUSAL as _REFUSAL

load_env()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
LLM_MODEL      = os.getenv("LLM_MODEL", "o3-mini")


# ---------------------------------------------------------------------------
# Public streaming function
# ---------------------------------------------------------------------------
async def stream_copilot(context: dict, question: str = ""):
    """
    Async generator that yields Server-Sent Event strings.
    Each chunk is:  'data: <text>\\n\\n'
    Terminator  :  'data: [DONE]\\n\\n'
    Error       :  'data: [ERROR: ...]\\n\\n'

    Caller wraps this in a FastAPI StreamingResponse.
    """
    if not OPENAI_API_KEY:
        yield "data: [ERROR: OPENAI_API_KEY not configured in .env]\n\n"
        return

    # ── Layer-1: reject obvious prompt-injection attempts immediately ─────────
    if question and is_injection(question):
        yield f"data: {_REFUSAL}\n\n"
        yield "data: [DONE]\n\n"
        return

    try:
        from openai import AsyncOpenAI
        import httpx
    except ImportError:
        yield "data: [ERROR: openai package not installed — run: pip install openai]\n\n"
        return

    # Corporate SSL certificate (optional — set CORP_CERT_PATH in .env if needed)
    corp_cert   = os.environ.get("CORP_CERT_PATH")
    http_client = httpx.AsyncClient(verify=corp_cert) if corp_cert else None

    client = AsyncOpenAI(
        api_key=OPENAI_API_KEY,
        **({"http_client": http_client} if http_client else {}),
    )

    ctx_str  = json.dumps(context, indent=2, default=str)
    user_msg = f"Current category data:\n{ctx_str}"
    if question:
        user_msg += f"\n\nCategory Manager question: {question}"

    try:
        stream = await client.chat.completions.create(
            model=LLM_MODEL,
            max_completion_tokens=3000,
            stream=True,
            extra_body={"reasoning_effort": "medium"},
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": user_msg},
            ],
        )

        async for chunk in stream:
            delta = chunk.choices[0].delta.content if chunk.choices else None
            if delta:
                # Escape newlines for SSE transport; frontend reverses this
                safe = delta.replace("\n", "\\n")
                yield f"data: {safe}\n\n"

        yield "data: [DONE]\n\n"

    except Exception as exc:
        yield f"data: [ERROR: {str(exc)[:120]}]\n\n"

    finally:
        if http_client:
            await http_client.aclose()
