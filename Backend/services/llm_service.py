"""
llm_service.py
==============
OpenRouter-backed LLM streaming for the AI Copilot panel.
Uses the OpenAI-compatible API provided by OpenRouter.
"""

import json
import os
from pathlib import Path


def _load_env():
    env_path = Path(__file__).parent.parent.parent / ".env"
    if env_path.exists():
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if "=" in line and not line.startswith("#"):
                    k, _, v = line.partition("=")
                    os.environ.setdefault(k.strip(), v.strip())


_load_env()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
LLM_MODEL          = os.getenv("LLM_MODEL", "google/gemini-2.0-flash-001")
OPENROUTER_BASE    = "https://openrouter.ai/api/v1"

SYSTEM_PROMPT = """\
You are an AI Copilot embedded inside a retail Category Manager's assortment dashboard.
You receive real forecast, inventory, and commercial data. Your job is to produce
4-8 crisp, RANKED, actionable recommendations — each grounded in the numbers provided.

Format EXACTLY as:
**1. [ACTION VERB in caps] [SKU name or category]**
Revenue impact: $X,XXX | [1-sentence data-backed reason]

**2. [ACTION VERB] ...**
...

Rules:
- Always quantify the financial impact (use the data given).
- Be direct. Never say "consider" or "may". Use "Replenish", "Delist", "Expand", "Transfer", "Promote".
- If a user question is present, answer it first, then give recommendations.
- Maximum 350 words total.
"""


async def stream_copilot(context: dict, question: str = "") -> any:
    """
    Async generator that yields Server-Sent Event strings.
    Yields token chunks from the LLM as they arrive.
    Caller wraps this in a FastAPI StreamingResponse.
    """
    if not OPENROUTER_API_KEY:
        yield "data: [ERROR: OPENROUTER_API_KEY not configured]\n\n"
        return

    try:
        from openai import AsyncOpenAI
    except ImportError:
        yield "data: [ERROR: openai package not installed — run: pip install openai]\n\n"
        return
    
    CORP_CERT_PATH = os.environ.get("CORP_CERT_PATH")

    client = AsyncOpenAI(
        api_key=OPENROUTER_API_KEY,
        base_url=OPENROUTER_BASE,
        http_client=httpx.Client(verify=CORP_CERT_PATH)
    )

    ctx_str = json.dumps(context, indent=2, default=str)
    user_msg = f"Current category data:\n{ctx_str}"
    if question:
        user_msg += f"\n\nCategory Manager question: {question}"

    try:
        async with client.chat.completions.stream(
            model=LLM_MODEL,
            max_tokens=600,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user",   "content": user_msg},
            ],
            extra_headers={
                "HTTP-Referer": "http://localhost:5173",
                "X-Title": "Retail Assortment AI Copilot",
            },
        ) as stream:
            async for chunk in stream:
                delta = chunk.choices[0].delta.content if chunk.choices else None
                if delta:
                    # Escape newlines for SSE; frontend replaces back
                    safe = delta.replace("\n", "\\n")
                    yield f"data: {safe}\n\n"

        yield "data: [DONE]\n\n"

    except Exception as exc:
        yield f"data: [ERROR: {str(exc)[:120]}]\n\n"
