"""
openai_client.py
=================
Shared OpenAI (o3-mini) call helper for the Data-Access Copilot agents.

Two entry points:
  call_json(...)    Non-streaming, schema-forced structured output.
                     Used by the Intent & Routing Agent and the Query
                     Generation Agent, which must return machine-parseable
                     JSON rather than free text.
  stream_text(...)  Streaming plain-text deltas (no SSE framing — that is
                     the caller's concern). Used by the Insight Agent for
                     the final user-facing answer.

Both raise on failure; callers decide fallback/retry behavior. This
mirrors (and is intended to eventually absorb) the OpenAI-call plumbing
duplicated across services/agent_llm.py and services/llm_service.py.
"""
import json
import logging
import os
from pathlib import Path
from typing import Any, AsyncGenerator

from ..config.settings import load_env

load_env()

log = logging.getLogger(__name__)

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
LLM_MODEL      = os.getenv("LLM_MODEL", "o3-mini")


def _resolve_ca_bundle() -> str:
    """
    Pick a CA bundle that's guaranteed to exist. httpx's default transport
    reads the SSL_CERT_FILE/SSL_CERT_DIR env vars directly even when
    verify=None is passed — if those point at a missing file (as observed
    in this environment, likely a corporate cert that was deleted after a
    one-time setup step), httpx.AsyncClient() construction raises
    FileNotFoundError before any request is made. Always resolving an
    explicit, existing bundle avoids depending on that ambient env state.
    """
    corp_cert = os.environ.get("CORP_CERT_PATH")
    if corp_cert and Path(corp_cert).is_file():
        return corp_cert
    if corp_cert:
        log.warning("CORP_CERT_PATH is set but the file doesn't exist (%s) — "
                     "falling back to certifi's CA bundle.", corp_cert)

    import certifi
    return certifi.where()


def _client():
    from openai import AsyncOpenAI
    import httpx

    http_client = httpx.AsyncClient(verify=_resolve_ca_bundle())
    client = AsyncOpenAI(api_key=OPENAI_API_KEY, http_client=http_client)
    return client, http_client


def _require_key() -> None:
    if not OPENAI_API_KEY:
        raise RuntimeError("OPENAI_API_KEY not configured in .env")


async def call_json(
    system_prompt: str,
    user_content: str,
    *,
    schema_name: str,
    schema: dict[str, Any],
    max_tokens: int = 1000,
    reasoning_effort: str = "low",
) -> dict[str, Any]:
    """Structured-output call — the response is guaranteed to validate
    against `schema` (OpenAI structured outputs, strict mode)."""
    _require_key()
    client, http_client = _client()
    try:
        resp = await client.chat.completions.create(
            model=LLM_MODEL,
            max_completion_tokens=max_tokens,
            extra_body={"reasoning_effort": reasoning_effort},
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": schema_name,
                    "schema": schema,
                    "strict": True,
                },
            },
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
        )
        content = resp.choices[0].message.content
        return json.loads(content)
    finally:
        if http_client:
            await http_client.aclose()


async def stream_text(
    system_prompt: str,
    user_content: str,
    *,
    max_tokens: int = 3000,
    reasoning_effort: str = "medium",
) -> AsyncGenerator[str, None]:
    """Streams raw text deltas (no SSE framing). Raises on failure."""
    _require_key()
    client, http_client = _client()
    try:
        stream = await client.chat.completions.create(
            model=LLM_MODEL,
            max_completion_tokens=max_tokens,
            stream=True,
            extra_body={"reasoning_effort": reasoning_effort},
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
        )
        async for chunk in stream:
            delta = chunk.choices[0].delta.content if chunk.choices else None
            if delta:
                yield delta
    finally:
        if http_client:
            await http_client.aclose()
