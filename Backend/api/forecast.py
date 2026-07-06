"""
forecast.py — FastAPI router
Exposes four endpoints:
  GET /api/forecast/filters       → available filter option lists
  GET /api/forecast/chart         → actuals + forecast time-series data
  GET /api/forecast/table         → pivot table grouped by a hierarchy dimension
  GET /api/forecast/explainability→ "Why this Forecast?" signal package
"""

from typing import Optional
from fastapi import APIRouter, Query
from ..services.forecast_service import (
    get_filter_options,
    get_chart_data,
    get_table_data,
    get_explainability,
)

router = APIRouter()

# ---------------------------------------------------------------------------
# Shared helper — collect filter params into a plain dict
# ---------------------------------------------------------------------------
def _filters(
    Store_ID:        Optional[str] = None,
    SKU_ID:          Optional[str] = None,
    unique_id:       Optional[str] = None,
    Geography:       Optional[str] = None,
    Region:          Optional[str] = None,
    Cluster:         Optional[str] = None,
    Ownership:       Optional[str] = None,
    Category:        Optional[str] = None,
    Sub_Category:    Optional[str] = None,
    Segment:         Optional[str] = None,
    Attribute_Claim: Optional[str] = None,
    Brand:           Optional[str] = None,
) -> dict:
    return {
        k: v for k, v in {
            "Store_ID":        Store_ID,
            "SKU_ID":          SKU_ID,
            "unique_id":       unique_id,
            "Geography":       Geography,
            "Region":          Region,
            "Cluster":         Cluster,
            "Ownership":       Ownership,
            "Category":        Category,
            "Sub_Category":    Sub_Category,
            "Segment":         Segment,
            "Attribute_Claim": Attribute_Claim,
            "Brand":           Brand,
        }.items() if v is not None
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/filters")
def filters_endpoint():
    """Return all unique values per filterable dimension."""
    return get_filter_options()


@router.get("/chart")
def chart_endpoint(
    Store_ID:        Optional[str] = Query(default=None),
    SKU_ID:          Optional[str] = Query(default=None),
    unique_id:       Optional[str] = Query(default=None),
    Geography:       Optional[str] = Query(default=None),
    Region:          Optional[str] = Query(default=None),
    Cluster:         Optional[str] = Query(default=None),
    Ownership:       Optional[str] = Query(default=None),
    Category:        Optional[str] = Query(default=None),
    Sub_Category:    Optional[str] = Query(default=None),
    Segment:         Optional[str] = Query(default=None),
    Attribute_Claim: Optional[str] = Query(default=None),
    Brand:           Optional[str] = Query(default=None),
    scenario_pct:    float         = Query(default=0.0),
):
    """Return aggregated actuals (last 24 wks) and forecast (next 6 wks)."""
    return get_chart_data(
        _filters(Store_ID, SKU_ID, unique_id, Geography, Region, Cluster,
                 Ownership, Category, Sub_Category, Segment, Attribute_Claim, Brand),
        scenario_pct,
    )


@router.get("/table")
def table_endpoint(
    Store_ID:        Optional[str] = Query(default=None),
    SKU_ID:          Optional[str] = Query(default=None),
    unique_id:       Optional[str] = Query(default=None),
    Geography:       Optional[str] = Query(default=None),
    Region:          Optional[str] = Query(default=None),
    Cluster:         Optional[str] = Query(default=None),
    Ownership:       Optional[str] = Query(default=None),
    Category:        Optional[str] = Query(default=None),
    Sub_Category:    Optional[str] = Query(default=None),
    Segment:         Optional[str] = Query(default=None),
    Attribute_Claim: Optional[str] = Query(default=None),
    Brand:           Optional[str] = Query(default=None),
    roll_dim:        str           = Query(default="Store_ID"),
    scenario_pct:    float         = Query(default=0.0),
):
    """Return a pivot table grouped by roll_dim dimension."""
    return get_table_data(
        _filters(Store_ID, SKU_ID, unique_id, Geography, Region, Cluster,
                 Ownership, Category, Sub_Category, Segment, Attribute_Claim, Brand),
        roll_dim,
        scenario_pct,
    )


@router.get("/explainability")
def explainability_endpoint(
    Store_ID:        Optional[str] = Query(default=None),
    SKU_ID:          Optional[str] = Query(default=None),
    unique_id:       Optional[str] = Query(default=None),
    Geography:       Optional[str] = Query(default=None),
    Region:          Optional[str] = Query(default=None),
    Cluster:         Optional[str] = Query(default=None),
    Ownership:       Optional[str] = Query(default=None),
    Category:        Optional[str] = Query(default=None),
    Sub_Category:    Optional[str] = Query(default=None),
    Segment:         Optional[str] = Query(default=None),
    Attribute_Claim: Optional[str] = Query(default=None),
    Brand:           Optional[str] = Query(default=None),
    scenario_pct:    float         = Query(default=0.0),
):
    """Return explainability drivers and narrative for the insight card."""
    return get_explainability(
        _filters(Store_ID, SKU_ID, unique_id, Geography, Region, Cluster,
                 Ownership, Category, Sub_Category, Segment, Attribute_Claim, Brand),
        scenario_pct,
    )
