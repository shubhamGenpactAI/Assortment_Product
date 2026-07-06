"""
decision_hub.py
===============
FastAPI router for the Category Decision Hub page.
All routes are prefixed with /api/decision-hub.
"""

from typing import Optional
from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from ..schemas.decision_hub import CopilotRequest
from ..services.decision_hub_service import (
    get_hub_kpis,
    get_risk_matrix,
    get_lost_sales,
    get_inventory_productivity,
    get_delist_rationalization,
    get_exception_alerts,
    get_category_health_scores,
    get_forecast_fan,
    get_sku_drilldown,
    build_copilot_context,
)
from ..services.llm_service import stream_copilot

router = APIRouter()


# ---------------------------------------------------------------------------
# KPIs
# ---------------------------------------------------------------------------
@router.get("/kpis")
def hub_kpis(
    store_id: Optional[str] = None,
    sub_cat:  Optional[str] = None,
    cluster:  Optional[str] = None,
):
    return get_hub_kpis(store_id, sub_cat, cluster)


# ---------------------------------------------------------------------------
# Risk Matrix
# ---------------------------------------------------------------------------
@router.get("/risk-matrix")
def hub_risk_matrix(
    store_id: Optional[str] = None,
    sub_cat:  Optional[str] = None,
    cluster:  Optional[str] = None,
):
    return get_risk_matrix(store_id, sub_cat, cluster)


# ---------------------------------------------------------------------------
# Lost Sales
# ---------------------------------------------------------------------------
@router.get("/lost-sales")
def hub_lost_sales(
    store_id: Optional[str] = None,
    sub_cat:  Optional[str] = None,
    top_n:    int = Query(default=20, ge=5, le=60),
):
    return get_lost_sales(store_id, sub_cat, top_n)


# ---------------------------------------------------------------------------
# Inventory Productivity
# ---------------------------------------------------------------------------
@router.get("/inventory-productivity")
def hub_inventory(
    store_id: Optional[str] = None,
    sub_cat:  Optional[str] = None,
    cluster:  Optional[str] = None,
):
    return get_inventory_productivity(store_id, sub_cat, cluster)


# ---------------------------------------------------------------------------
# Delist Rationalization
# ---------------------------------------------------------------------------
@router.get("/delist-rationalization")
def hub_delist(
    store_id: Optional[str] = None,
    sub_cat:  Optional[str] = None,
):
    return get_delist_rationalization(store_id, sub_cat)


# ---------------------------------------------------------------------------
# Exception Alerts
# ---------------------------------------------------------------------------
@router.get("/exception-alerts")
def hub_alerts(
    store_id: Optional[str] = None,
    sub_cat:  Optional[str] = None,
    cluster:  Optional[str] = None,
):
    return get_exception_alerts(store_id, sub_cat, cluster)


# ---------------------------------------------------------------------------
# Category Health Scores
# ---------------------------------------------------------------------------
@router.get("/category-health")
def hub_health():
    return get_category_health_scores()


# ---------------------------------------------------------------------------
# Forecast Fan Chart
# ---------------------------------------------------------------------------
@router.get("/forecast-fan/{sku_id}/{store_id}")
def hub_fan(sku_id: str, store_id: str):
    return get_forecast_fan(sku_id, store_id)


# ---------------------------------------------------------------------------
# SKU Drilldown
# ---------------------------------------------------------------------------
@router.get("/sku-drilldown/{sku_id}/{store_id}")
def hub_drilldown(sku_id: str, store_id: str):
    return get_sku_drilldown(sku_id, store_id)


# ---------------------------------------------------------------------------
# AI Copilot — Context (non-streaming snapshot)
# ---------------------------------------------------------------------------
@router.get("/copilot/context")
def hub_copilot_context(
    store_id: Optional[str] = None,
    sub_cat:  Optional[str] = None,
    cluster:  Optional[str] = None,
):
    return build_copilot_context(store_id, sub_cat, cluster)


# ---------------------------------------------------------------------------
# AI Copilot — Streaming (SSE)
# ---------------------------------------------------------------------------
@router.post("/copilot/stream")
async def hub_copilot_stream(req: CopilotRequest):
    context = build_copilot_context(req.store_id, req.sub_cat, req.cluster)
    return StreamingResponse(
        stream_copilot(context, req.question or ""),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
