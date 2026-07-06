"""
new_sku.py — FastAPI router for New SKU Intelligence API.

Endpoints
---------
POST /api/new-sku/intelligence        Full intelligence run (primary endpoint)
GET  /api/new-sku/list                List available new SKUs from similarity output
GET  /api/new-sku/forecast/{sku_id}   Hierarchical forecast only
GET  /api/new-sku/cannibalization/{sku_id}  Cannibalization analysis only
GET  /api/new-sku/stores/{sku_id}     Store recommendation only
POST /api/new-sku/scenario            Run custom scenario simulation
GET  /api/new-sku/whitespace          Whitespace / gap detection
GET  /api/new-sku/analogs/{sku_id}    Top analog SKUs with explanations
"""

from __future__ import annotations
from typing import Optional

from fastapi import APIRouter, Query, HTTPException, UploadFile, File

from ..schemas.new_sku import NewSKUAttrs, IntelligenceRequest, ScenarioRequest, CompareRequest
from ..services.new_sku_service import (
    get_new_sku_list,
    run_intelligence,
    get_forecast,
    get_cannibalization,
    get_store_recommendation,
    run_custom_scenario,
    get_whitespace,
    get_analogs,
    upload_csv,
    clear_upload_cache,
)

router = APIRouter()


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/list")
def list_new_skus():
    """Return all new SKU IDs available in the similarity output file."""
    return get_new_sku_list()


@router.post("/intelligence")
def full_intelligence(req: IntelligenceRequest):
    """
    Run the full new SKU intelligence pipeline and return unified payload.
    This is the primary endpoint — powers the New SKU Intelligence Hub page.
    """
    attrs = req.new_sku_attrs.model_dump(exclude_none=True) if req.new_sku_attrs else {}
    return run_intelligence(
        new_sku_id    = req.new_sku_id,
        new_sku_attrs = attrs,
        top_n_analogs = req.top_n_analogs or 5,
        top_n_stores  = req.top_n_stores  or 10,
    )


@router.get("/forecast/{sku_id}")
def forecast_endpoint(
    sku_id:         str,
    List_Price_USD: Optional[float] = Query(default=None),
    Unit_Cost_USD:  Optional[float] = Query(default=None),
    Sub_Category:   Optional[str]   = Query(default=None),
):
    """Return hierarchical forecast (store/cluster/region/enterprise) for a new SKU."""
    attrs = {}
    if List_Price_USD:  attrs["List_Price_USD"] = List_Price_USD
    if Unit_Cost_USD:   attrs["Unit_Cost_USD"]  = Unit_Cost_USD
    if Sub_Category:    attrs["Sub_Category"]   = Sub_Category
    return get_forecast(sku_id, attrs)


@router.get("/cannibalization/{sku_id}")
def cannibalization_endpoint(
    sku_id:              str,
    forecast_units_total: float = Query(default=1000.0),
    Sub_Category:        Optional[str]   = Query(default=None),
    List_Price_USD:      Optional[float] = Query(default=None),
):
    """Return cannibalization analysis for a new SKU."""
    attrs: dict = {}
    if Sub_Category:    attrs["Sub_Category"]   = Sub_Category
    if List_Price_USD:  attrs["List_Price_USD"] = List_Price_USD
    return get_cannibalization(sku_id, attrs, forecast_units_total)


@router.get("/stores/{sku_id}")
def stores_endpoint(
    sku_id:        str,
    Sub_Category:  Optional[str]   = Query(default=None),
    List_Price_USD: Optional[float] = Query(default=None),
    Price_Band:    Optional[str]   = Query(default=None),
    Age_Group:     Optional[str]   = Query(default=None),
    Organic_Flag:  Optional[int]   = Query(default=None),
):
    """Return store recommendation scores and rollout phases."""
    attrs: dict = {}
    if Sub_Category:   attrs["Sub_Category"]   = Sub_Category
    if List_Price_USD: attrs["List_Price_USD"] = List_Price_USD
    if Price_Band:     attrs["Price_Band"]     = Price_Band
    if Age_Group:      attrs["Age_Group"]      = Age_Group
    if Organic_Flag is not None: attrs["Organic_Flag"] = Organic_Flag
    return get_store_recommendation(sku_id, attrs)


@router.post("/scenario")
def scenario_endpoint(req: ScenarioRequest):
    """Run a custom what-if scenario for a new SKU."""
    attrs = req.new_sku_attrs.model_dump(exclude_none=True) if req.new_sku_attrs else {}
    return run_custom_scenario(
        new_sku_id          = req.new_sku_id,
        new_sku_attrs       = attrs,
        base_units          = req.base_units,
        price_delta_pct     = req.price_delta_pct,
        promo_intensity     = req.promo_intensity,
        pack_size_delta_pct = req.pack_size_delta_pct,
        geography_filter    = req.geography_filter,
        custom_elasticity   = req.custom_elasticity,
    )


@router.get("/whitespace")
def whitespace_endpoint(
    sub_category: Optional[str] = Query(default=None),
    top_n:        int           = Query(default=15),
):
    """Detect assortment gaps and whitespace opportunities."""
    return get_whitespace(sub_category, top_n)


@router.get("/analogs/{sku_id}")
def analogs_endpoint(
    sku_id: str,
    top_n:  int = Query(default=5),
):
    """Return top analog SKUs with similarity explanations."""
    return get_analogs(sku_id, top_n)


@router.post("/upload")
async def upload_endpoint(file: UploadFile = File(...)):
    """
    Upload a CSV (or XLSX) of new SKUs.
    Runs similarity scoring + analog demand for every row.
    Returns processed SKU list ready for intelligence analysis.
    """
    contents = await file.read()
    return upload_csv(contents, file.filename or "upload.csv")


@router.delete("/upload/cache")
def clear_cache_endpoint():
    """Clear the in-memory upload cache (e.g. start fresh session)."""
    return clear_upload_cache()


@router.get("/uploaded")
def uploaded_skus_endpoint():
    """Return list of SKU IDs currently in the upload cache."""
    from ..NewSKU.csv_upload_processor import list_uploaded_skus
    skus = list_uploaded_skus()
    return {"uploaded_skus": skus, "count": len(skus)}
