"""Pydantic request models for api/new_sku.py (moved out of the router)."""
from __future__ import annotations
from typing import Optional

from pydantic import BaseModel


class NewSKUAttrs(BaseModel):
    SKU_ID:              Optional[str]   = None
    Product_Name:        Optional[str]   = None
    Brand:               Optional[str]   = None
    Category:            Optional[str]   = None
    Sub_Category:        Optional[str]   = None
    Segment:             Optional[str]   = None
    Attribute_Claim:     Optional[str]   = None
    Price_Band:          Optional[str]   = None
    List_Price_USD:      Optional[float] = None
    Unit_Cost_USD:       Optional[float] = None
    Pack_Size_ml:        Optional[float] = None
    Organic_Flag:        Optional[int]   = None
    Sulphate_Free_Flag:  Optional[int]   = None
    Paraben_Free_Flag:   Optional[int]   = None
    Dandruff_Flag:       Optional[int]   = None
    Hair_Fall_Flag:      Optional[int]   = None
    Color_Protection_Flag: Optional[int] = None
    Ingredient_1:        Optional[str]   = None
    Ingredient_2:        Optional[str]   = None
    Ingredient_3:        Optional[str]   = None
    Ingredient_4:        Optional[str]   = None
    Hair_Type:           Optional[str]   = None
    Age_Group:           Optional[str]   = None
    Gender:              Optional[str]   = None


class IntelligenceRequest(BaseModel):
    new_sku_id:    str
    new_sku_attrs: Optional[NewSKUAttrs] = None
    top_n_analogs: Optional[int] = 5
    top_n_stores:  Optional[int] = 10


class ScenarioRequest(BaseModel):
    new_sku_id:           str
    new_sku_attrs:        Optional[NewSKUAttrs] = None
    base_units:           float
    price_delta_pct:      float = 0.0
    promo_intensity:      float = 0.0
    pack_size_delta_pct:  float = 0.0
    geography_filter:     Optional[list[str]] = None
    custom_elasticity:    Optional[float]     = None


class CompareRequest(BaseModel):
    new_sku_id:    str
    new_sku_attrs: Optional[NewSKUAttrs] = None
    base_units:    float
    scenarios:     list[dict]
