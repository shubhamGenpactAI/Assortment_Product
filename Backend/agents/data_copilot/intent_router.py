"""
intent_router.py
=================
Agent 1: Intent & Routing.

Given the user's question and the cheap catalog index (names + one-line
descriptions only — see catalog.get_catalog_index()), decides whether the
question needs real data at all, and if so, which catalog source(s) are
relevant. Deliberately does NOT see full schemas here — that's the Query
Generation Agent's job, once routing has narrowed the scope.
"""
import json
from dataclasses import dataclass, field

from ...integrations.openai_client import call_json
from ...prompts.data_copilot_prompts import ROUTER_PROMPT
from . import catalog

ROUTER_SCHEMA = {
    "type": "object",
    "properties": {
        "intent": {
            "type": "string",
            "description": "One sentence summarizing what the user is asking.",
        },
        "needs_data": {
            "type": "boolean",
            "description": "True if answering requires querying real data from the catalog.",
        },
        "sources": {
            "type": "array",
            "description": "Catalog source names relevant to this question. Empty if needs_data is false.",
            "items": {
                "type": "object",
                "properties": {
                    "name":   {"type": "string"},
                    "reason": {"type": "string"},
                },
                "required": ["name", "reason"],
                "additionalProperties": False,
            },
        },
        "mentioned_filters": {
            "type": ["string", "null"],
            "description": "Brief note of any filters mentioned (store, sub-category, date range, cluster, etc), or null.",
        },
    },
    "required": ["intent", "needs_data", "sources", "mentioned_filters"],
    "additionalProperties": False,
}


@dataclass
class RoutedSource:
    name: str
    reason: str


@dataclass
class RoutingResult:
    intent: str
    needs_data: bool
    sources: list[RoutedSource] = field(default_factory=list)
    mentioned_filters: str | None = None


async def route(question: str) -> RoutingResult:
    catalog_index = catalog.get_catalog_index()
    user_content = json.dumps({
        "question": question,
        "catalog": catalog_index,
    }, indent=2)

    result = await call_json(
        ROUTER_PROMPT,
        user_content,
        schema_name="routing_decision",
        schema=ROUTER_SCHEMA,
        max_tokens=600,
        reasoning_effort="low",
    )

    known = catalog.known_source_names()
    sources = [
        RoutedSource(name=s["name"], reason=s["reason"])
        for s in result.get("sources", [])
        if s["name"] in known  # defensive: drop any hallucinated source name
    ]

    return RoutingResult(
        intent=result["intent"],
        needs_data=result["needs_data"] and bool(sources),
        sources=sources,
        mentioned_filters=result.get("mentioned_filters"),
    )
