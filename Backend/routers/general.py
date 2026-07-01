"""
general.py — routes for all non-forecast pages
"""

from typing import Optional
from fastapi import APIRouter, Query
from ..services.general_service import (
    get_dashboard_kpis, get_manager_recommendations,
    get_abc_data, get_basket_top_pairs, get_sales_trend, get_store_ranking,
    get_sku_performance, get_brand_share, get_store_list,
    get_assortment_recs,
    get_delist_data,
    get_data_quality,
    get_similarity_data, get_analog_forecast,
)

router = APIRouter()

# ── Dashboard ──────────────────────────────────────────────────────────────
@router.get("/dashboard/kpis")
def dashboard_kpis(): return get_dashboard_kpis()

@router.get("/dashboard/recommendations")
def dashboard_recs(): return get_manager_recommendations()

@router.get("/dashboard/abc")
def dashboard_abc(store_id: Optional[str] = None, sub_cat: Optional[str] = None):
    return get_abc_data(store_id, sub_cat)

@router.get("/dashboard/basket-pairs")
def dashboard_basket(n: int = 8): return get_basket_top_pairs(n)

@router.get("/dashboard/sales-trend")
def dashboard_trend(store_id: Optional[str] = None, sub_cat: Optional[str] = None):
    return get_sales_trend(store_id, sub_cat)

@router.get("/dashboard/store-ranking")
def dashboard_ranking(): return get_store_ranking()

# ── Common lookups ─────────────────────────────────────────────────────────
@router.get("/stores")
def stores(): return get_store_list()

# ── SKU Performance ────────────────────────────────────────────────────────
@router.get("/sku-performance")
def sku_perf(store_id: str = Query(...)): return get_sku_performance(store_id)

@router.get("/brand-share")
def brand_share(store_id: str = Query(...)): return get_brand_share(store_id)

# ── Assortment ─────────────────────────────────────────────────────────────
@router.get("/assortment")
def assortment(store_id: str = Query(...)): return get_assortment_recs(store_id)

# ── Delisting ──────────────────────────────────────────────────────────────
@router.get("/delist")
def delist(
    rec_filter: Optional[str] = None,
    sub_cat:    Optional[str] = None,
    abc_cls:    Optional[str] = None,
): return get_delist_data(rec_filter, sub_cat, abc_cls)

# ── Data Quality ───────────────────────────────────────────────────────────
@router.get("/data-quality")
def data_quality(): return get_data_quality()

# ── New SKU / Similarity ───────────────────────────────────────────────────
@router.get("/similarity")
def similarity(): return get_similarity_data()

@router.get("/analog-forecast")
def analog_forecast(new_sku_id: str = Query(...)): return get_analog_forecast(new_sku_id)
