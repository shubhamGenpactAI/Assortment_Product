"""
agents.py
=========
FastAPI router for all three AI agents.
Prefix: /api/agents  (set in main.py)

All business logic lives in Backend/agents/*.py — this file is thin.
"""
import os
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from ..schemas.agents import WatchdogNarrativeRequest, OverrideRequest, BriefRequest
from ..agents.watchdog_agent import (
    build_digest,
    build_narrative_context,
)
from ..agents.localization_agent import (
    find_divergent_skus,
    record_override,
    list_overrides,
)
from ..agents.brief_agent import (
    build_brief,
    get_brief,
    list_briefs,
    build_polish_context,
)
from ..services.agent_llm import stream_agent_response
from ..prompts.agent_prompts import WATCHDOG_PROMPT, BRIEF_POLISH_PROMPT

router = APIRouter()

_WATCHDOG_ENABLED     = os.getenv("ENABLE_WATCHDOG_AGENT",     "true").lower() == "true"
_LOCALIZATION_ENABLED = os.getenv("ENABLE_LOCALIZATION_AGENT", "true").lower() == "true"
_BRIEF_ENABLED        = os.getenv("ENABLE_BRIEF_AGENT",        "true").lower() == "true"


def _check(enabled: bool, name: str) -> None:
    if not enabled:
        raise HTTPException(status_code=404, detail=f"{name} agent is disabled via feature flag")


# ============================================================
# WATCHDOG AGENT
# ============================================================

@router.get("/watchdog/digest")
def watchdog_digest(
    store_id: Optional[str] = None,
    sub_cat:  Optional[str] = None,
    cluster:  Optional[str] = None,
    top_n:    int = Query(default=10, ge=1, le=50),
):
    _check(_WATCHDOG_ENABLED, "Watchdog")
    return build_digest(store_id, sub_cat, cluster, top_n)


@router.post("/watchdog/narrative")
async def watchdog_narrative(req: WatchdogNarrativeRequest):
    _check(_WATCHDOG_ENABLED, "Watchdog")
    digest  = build_digest(req.store_id, req.sub_cat, req.cluster, req.top_n)
    context = build_narrative_context(digest)
    return StreamingResponse(
        stream_agent_response(WATCHDOG_PROMPT, context),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ============================================================
# LOCALIZATION AGENT
# ============================================================

@router.get("/localization/divergence")
def localization_divergence(
    sub_cat:        Optional[str] = None,
    min_divergence: float         = Query(default=0.04, ge=0.0, le=1.0),
):
    _check(_LOCALIZATION_ENABLED, "Localization")
    return find_divergent_skus(sub_cat, min_divergence)


@router.post("/localization/override")
def localization_override(req: OverrideRequest):
    _check(_LOCALIZATION_ENABLED, "Localization")
    if req.decision not in ("approved", "rejected"):
        raise HTTPException(status_code=422, detail="decision must be 'approved' or 'rejected'")
    return record_override(req.sku_id, req.cluster_id, req.decision, req.note or "", req.decided_by or "")


@router.get("/localization/overrides")
def localization_overrides(
    sku_id:     Optional[str] = None,
    cluster_id: Optional[str] = None,
):
    _check(_LOCALIZATION_ENABLED, "Localization")
    return list_overrides(sku_id, cluster_id)


# ============================================================
# STAKEHOLDER BRIEF AGENT
# ============================================================

@router.post("/brief/generate")
def brief_generate(req: BriefRequest):
    _check(_BRIEF_ENABLED, "Brief")
    try:
        return build_brief(req.brief_type, req.brand, req.sub_cat, req.sku_ids, req.generated_by or "")
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.post("/brief/{brief_id}/polish")
async def brief_polish(brief_id: str):
    _check(_BRIEF_ENABLED, "Brief")
    brief = get_brief(brief_id)
    if brief is None:
        raise HTTPException(status_code=404, detail=f"Brief '{brief_id}' not found")
    context = build_polish_context(brief)
    return StreamingResponse(
        stream_agent_response(BRIEF_POLISH_PROMPT, context),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/brief/{brief_id}")
def brief_get(brief_id: str):
    _check(_BRIEF_ENABLED, "Brief")
    brief = get_brief(brief_id)
    if brief is None:
        raise HTTPException(status_code=404, detail=f"Brief '{brief_id}' not found")
    return brief


@router.get("/brief")
def brief_list(
    brand:   Optional[str] = None,
    sub_cat: Optional[str] = None,
):
    _check(_BRIEF_ENABLED, "Brief")
    return list_briefs(brand, sub_cat)


# ============================================================
# Cache refresh (admin)
# ============================================================

@router.post("/admin/refresh-cache")
def refresh_cache():
    from ..services.decision_hub_service import (
        _base_frame, _demand_raw, _forecast_raw, _delist_raw,
        _sku, _store, _clusters, _assoc_raw, _basket_raw,
    )
    from ..agents.localization_agent import _delist, _clusters as _loc_clusters, _sku_master
    from ..agents.brief_agent import _assoc, _basket, _delist as _brief_delist, _sku_master as _brief_sku

    for fn in [
        _base_frame, _demand_raw, _forecast_raw, _delist_raw,
        _sku, _store, _clusters, _assoc_raw, _basket_raw,
        _delist, _loc_clusters, _sku_master,
        _assoc, _basket, _brief_delist, _brief_sku,
    ]:
        fn.cache_clear()

    return {"status": "cache cleared"}
