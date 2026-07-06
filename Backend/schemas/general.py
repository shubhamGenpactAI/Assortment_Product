"""Pydantic request models for api/general.py (moved out of the router)."""
from typing import Optional

from pydantic import BaseModel


class AssortmentDecisionIn(BaseModel):
    decision_label:      str
    decision_type:       Optional[str]   = None
    comment:             Optional[str]   = ""
    sku_id:              str
    product_name:        Optional[str]   = None
    brand:               Optional[str]   = None
    category:            Optional[str]   = None
    sub_category:        Optional[str]   = None
    view_label:          Optional[str]   = None
    scope:               Optional[str]   = None
    granularity_value:   Optional[str]   = None
    abc_class:           Optional[str]   = None
    health_score:        Optional[float] = None
    delist_score:        Optional[float] = None
    gmroi:               Optional[float] = None
    forecast_growth_pct: Optional[float] = None
    health_band:         Optional[str]   = None
    delist_band:         Optional[str]   = None
    basket_role:         Optional[str]   = None
    total_revenue:       Optional[float] = None
    total_margin:        Optional[float] = None
    price_band:          Optional[str]   = None
    list_price_usd:      Optional[float] = None
    decision_reason:     Optional[str]   = None
    recommended_action:  Optional[str]   = None
