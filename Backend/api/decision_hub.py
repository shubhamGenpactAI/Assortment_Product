"""
decision_hub.py
===============
FastAPI router for the Category Decision Hub page.
All routes are prefixed with /api/decision-hub.
"""

from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse

from ..agents.data_copilot import orchestrator
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
# AI Copilot — Streaming (SSE), backed by the Data-Access Copilot pipeline
# (agents/data_copilot/orchestrator.py): Intent & Routing -> Query
# Generation -> Data Retrieval (DuckDB) -> Insight. Request/response shape
# is unchanged from the previous single-shot implementation.
# ---------------------------------------------------------------------------
@router.post("/copilot/stream")
async def hub_copilot_stream(req: CopilotRequest):
    trace_id = orchestrator.new_trace_id()
    filters = {"store_id": req.store_id, "sub_cat": req.sub_cat, "cluster": req.cluster}
    return StreamingResponse(
        orchestrator.run_copilot(req.question or "", filters, trace_id=trace_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "X-Copilot-Trace-Id": trace_id,
        },
    )


# ---------------------------------------------------------------------------
# AI Copilot — Explainability: the structured trace (intent, sources, SQL,
# row counts, retries) for a given /copilot/stream call, keyed by the
# X-Copilot-Trace-Id header returned on that call.
# ---------------------------------------------------------------------------
@router.get("/copilot/explain/{trace_id}")
def hub_copilot_explain(trace_id: str):
    trace = orchestrator.get_trace(trace_id)
    if trace is None:
        raise HTTPException(status_code=404, detail=f"No trace found for '{trace_id}' (expired or invalid).")
    return trace
