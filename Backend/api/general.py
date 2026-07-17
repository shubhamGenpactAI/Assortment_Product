"""
general.py — routes for stores, delisting risk, new-SKU similarity,
             and assortment decisions (Category Intelligence).
"""

import csv
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from ..schemas.general import AssortmentDecisionIn
from ..services.general_service import (
    get_store_list,
    get_delist_data,
    get_similarity_data, get_analog_forecast,
)

log = logging.getLogger(__name__)
router = APIRouter()

# Project root (Backend/routers/ → Backend/ → Assortment/)
_PROJ = Path(__file__).resolve().parent.parent.parent
_DECISIONS_CSV = _PROJ / "Outputs" / "Assortment decision.csv"

_DECISION_HEADERS = [
    "Timestamp", "Decision", "Decision_Type", "Comment",
    "SKU_ID", "Product_Name", "Brand", "Category", "Sub_Category",
    "View_Label", "Scope", "Granularity_Value", "Scope_Detail",
    "ABC_Class", "Health_Score", "Delist_Score", "GMROI",
    "Forecast_Growth_Pct", "Health_Band", "Delist_Band",
    "Basket_Role", "Total_Revenue", "Total_Margin",
    "Price_Band", "List_Price_USD", "Decision_Reason", "Recommended_Action",
]


# ── Common lookups ─────────────────────────────────────────────────────────
@router.get("/stores")
def stores(): return get_store_list()


# ── Delisting ──────────────────────────────────────────────────────────────
@router.get("/delist")
def delist(
    rec_filter: Optional[str] = None,
    sub_cat:    Optional[str] = None,
    abc_cls:    Optional[str] = None,
): return get_delist_data(rec_filter, sub_cat, abc_cls)


# ── New SKU / Similarity ───────────────────────────────────────────────────
@router.get("/similarity")
def similarity(): return get_similarity_data()

@router.get("/analog-forecast")
def analog_forecast(new_sku_id: str = Query(...)): return get_analog_forecast(new_sku_id)


# ── Assortment Decisions ───────────────────────────────────────────────────
@router.post("/assortment-decisions")
def save_assortment_decision(payload: AssortmentDecisionIn):
    # Scope_Detail: the concrete store number when scope is Store, or the
    # geography name when scope is Geography — blank for Global/other scopes.
    scope_detail = payload.granularity_value if payload.scope in ("Store", "Geography") else ""

    row = {
        "Timestamp":           datetime.now().isoformat(timespec="seconds"),
        "Decision":            payload.decision_label,
        "Decision_Type":       payload.decision_type or "",
        "Comment":             payload.comment or "",
        "SKU_ID":              payload.sku_id,
        "Product_Name":        payload.product_name or "",
        "Brand":               payload.brand or "",
        "Category":            payload.category or "",
        "Sub_Category":        payload.sub_category or "",
        "View_Label":          payload.view_label or "",
        "Scope":               payload.scope or "",
        "Granularity_Value":   payload.granularity_value or "",
        "Scope_Detail":        scope_detail or "",
        "ABC_Class":           payload.abc_class or "",
        "Health_Score":        payload.health_score,
        "Delist_Score":        payload.delist_score,
        "GMROI":               payload.gmroi,
        "Forecast_Growth_Pct": payload.forecast_growth_pct,
        "Health_Band":         payload.health_band or "",
        "Delist_Band":         payload.delist_band or "",
        "Basket_Role":         payload.basket_role or "",
        "Total_Revenue":       payload.total_revenue,
        "Total_Margin":        payload.total_margin,
        "Price_Band":          payload.price_band or "",
        "List_Price_USD":      payload.list_price_usd,
        "Decision_Reason":     payload.decision_reason or "",
        "Recommended_Action":  payload.recommended_action or "",
    }

    try:
        _DECISIONS_CSV.parent.mkdir(parents=True, exist_ok=True)
        write_header = not _DECISIONS_CSV.exists()
        with _DECISIONS_CSV.open("a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=_DECISION_HEADERS)
            if write_header:
                writer.writeheader()
            writer.writerow(row)
    except Exception as e:
        log.warning("Assortment decision CSV write failed: %s", e)
        raise HTTPException(
            status_code=500,
            detail=f"Could not save decision to CSV ({e}). Is 'Assortment decision.csv' currently open in Excel?",
        )

    return {"status": "saved"}


@router.get("/assortment-decisions")
def list_assortment_decisions():
    """Live read of the decisions CSV — always the current on-disk rows, no caching."""
    if not _DECISIONS_CSV.exists():
        return []
    try:
        with _DECISIONS_CSV.open("r", newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))
    except Exception as e:
        log.warning("Assortment decision CSV read failed: %s", e)
        raise HTTPException(status_code=503, detail=f"Could not read decisions CSV ({e}).")
