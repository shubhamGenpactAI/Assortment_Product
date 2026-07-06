"""
csv_upload_processor.py
Processes an uploaded CSV of new SKUs.

For each row in the uploaded file:
  1. Normalise column names
  2. Run the exact same 4-group similarity pipeline as similarity.py
     (reusing its functions directly — no duplication)
  3. Build analog demand forecast per store × week
  4. Store results in module-level in-memory cache

The cache is keyed by SKU_ID.  Any module that loads similarity scores
(sku_intelligence.py, hierarchical_forecast.py, cannibalization.py) calls
get_cached_sim_scores(sku_id) / get_cached_analog_demand(sku_id) to check
the cache before reading from CSV files.

Supported upload columns
------------------------
Required (at least one identifier):
  SKU_ID  OR  Product_Name

Strongly recommended (drives similarity quality):
  Sub_Category, Segment, Attribute_Claim, Brand, Price_Band
  Sulphate_Free_Flag, Paraben_Free_Flag, Organic_Flag
  Dandruff_Flag, Hair_Fall_Flag, Color_Protection_Flag
  Ingredient_1 … Ingredient_4
  List_Price_USD, Unit_Cost_USD, Pack_Size_ml

Optional enrichment:
  Hair_Type, Age_Group, Gender, Manufacturer, Ownership,
  Supplier, Margin_Pct, Case_Pack, Launch_Date, Status
"""

from __future__ import annotations
import io
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Path setup — import similarity functions from Backend/pipelines/basket_abc_analysis/
# ---------------------------------------------------------------------------
_ROOT     = Path(__file__).resolve().parent.parent.parent          # Assortment/
_SIM_DIR  = _ROOT / "Backend" / "pipelines" / "basket_abc_analysis"
_RAW      = _ROOT / "Raw_Input"
_OUT      = _ROOT / "Outputs"

if str(_SIM_DIR) not in sys.path:
    sys.path.insert(0, str(_SIM_DIR))

# Reuse similarity.py functions directly
from similarity import (                                            # noqa: E402
    normalize_column_names,
    build_attribute_matrix,
    calculate_hierarchy_similarity,
    calculate_functional_similarity,
    calculate_ingredient_similarity,
    calculate_commercial_similarity,
    calculate_weighted_similarity,
    _normalize_keys,
    ID_COL,
    DISPLAY_COLS,
)

# ---------------------------------------------------------------------------
# Module-level in-memory cache
# ---------------------------------------------------------------------------
_SIM_CACHE:    dict[str, pd.DataFrame] = {}   # sku_id → similarity_scores df
_ANALOG_CACHE: dict[str, pd.DataFrame] = {}   # sku_id → analog demand df
_ATTRS_CACHE:  dict[str, dict]         = {}   # sku_id → raw attrs dict

TOP_N_ANALOG = 5


# ---------------------------------------------------------------------------
# SKU master loader (searches both Raw_Input/ and pipelines/basket_abc_analysis/)
# ---------------------------------------------------------------------------
_MASTER_CACHE: dict[str, pd.DataFrame] = {}

def _load_sku_master() -> pd.DataFrame:
    if "master" in _MASTER_CACHE:
        return _MASTER_CACHE["master"]

    candidates = [
        _RAW / "SKU_Master.csv",
        _SIM_DIR / "Smililarity_SKU.xlsx",
        _SIM_DIR / "Similarity_SKU.xlsx",
        _SIM_DIR / "SKU_Master_Similarity.xlsx",
    ]
    for p in candidates:
        if p.exists():
            df = pd.read_excel(p) if p.suffix.lower() in (".xlsx", ".xls") else pd.read_csv(p)
            if not df.empty:
                df = normalize_column_names(df)
                _MASTER_CACHE["master"] = df
                return df

    return pd.DataFrame()


def _load_demand() -> pd.DataFrame | None:
    """Load the best available demand file for analog forecast."""
    candidates = [
        _OUT / "weekly_demand_output.csv",
        _OUT / "Forecast_Output.csv",
        _SIM_DIR / "weekly_demand_output.csv",
        _SIM_DIR / "weekly_demand_output.xlsx",
    ]
    for p in candidates:
        if p.exists():
            df = pd.read_excel(p) if p.suffix.lower() in (".xlsx", ".xls") else pd.read_csv(p)
            if not df.empty:
                return df
    return None


# ---------------------------------------------------------------------------
# Public cache accessors
# ---------------------------------------------------------------------------
def get_cached_sim_scores(sku_id: str) -> pd.DataFrame | None:
    return _SIM_CACHE.get(sku_id)


def get_cached_analog_demand(sku_id: str) -> pd.DataFrame | None:
    return _ANALOG_CACHE.get(sku_id)


def get_cached_attrs(sku_id: str) -> dict | None:
    return _ATTRS_CACHE.get(sku_id)


def list_uploaded_skus() -> list[str]:
    return list(_SIM_CACHE.keys())


def clear_cache() -> None:
    _SIM_CACHE.clear()
    _ANALOG_CACHE.clear()
    _ATTRS_CACHE.clear()


# ---------------------------------------------------------------------------
# Core: run similarity for one new SKU dict
# ---------------------------------------------------------------------------
def _run_similarity_for_sku(new_sku: dict, master: pd.DataFrame) -> pd.DataFrame:
    """Returns a ranked similarity DataFrame for new_sku vs master."""
    new_sku = _normalize_keys(new_sku)
    combined = build_attribute_matrix(master, new_sku)

    hier = calculate_hierarchy_similarity(combined)
    func = calculate_functional_similarity(combined)
    ingr = calculate_ingredient_similarity(combined)
    comm = calculate_commercial_similarity(combined)
    hier, func, ingr, comm, final = calculate_weighted_similarity(hier, func, ingr, comm)

    sku_id = str(new_sku.get(ID_COL, new_sku.get("SKU_ID", "UPLOAD_SKU")))

    out = pd.DataFrame({
        "New_SKU_ID":              sku_id,
        "Existing_SKU_ID":         master[ID_COL].values if ID_COL in master.columns else [""] * len(master),
        "Existing_Product_Name":   master.get("Product_Name",  pd.Series([""] * len(master))).values,
        "Existing_Brand":          master.get("Brand",          pd.Series([""] * len(master))).values,
        "Existing_Sub_Category":   master.get("Sub_Category",   pd.Series([""] * len(master))).values,
        "Existing_Segment":        master.get("Segment",        pd.Series([""] * len(master))).values,
        "Existing_Attribute_Claim":master.get("Attribute_Claim",pd.Series([""] * len(master))).values,
        "Hierarchy_Similarity":    np.round(hier, 4),
        "Functional_Similarity":   np.round(func, 4),
        "Ingredient_Similarity":   np.round(ingr, 4),
        "Commercial_Similarity":   np.round(comm, 4),
        "Final_Similarity_Score":  np.round(final, 4),
    })
    out = out.sort_values("Final_Similarity_Score", ascending=False).reset_index(drop=True)
    out["Similarity_Rank"] = out.index + 1
    return out


# ---------------------------------------------------------------------------
# Core: build analog demand for one new SKU from its similarity scores
# ---------------------------------------------------------------------------
def _run_analog_demand(scores_df: pd.DataFrame) -> pd.DataFrame | None:
    demand = _load_demand()
    if demand is None:
        return None

    week_col = next((c for c in ["Year_WK", "Forecast_Week", "Week"] if c in demand.columns), None)
    qty_col  = next((c for c in ["Quantity_Sold", "Final_Forecast", "Quantity"] if c in demand.columns), None)
    if not week_col or not qty_col:
        return None
    if "Store_ID" not in demand.columns or "SKU_ID" not in demand.columns:
        return None

    new_sku_id = str(scores_df["New_SKU_ID"].iloc[0])
    top        = scores_df.head(TOP_N_ANALOG).copy()
    w_total    = top["Final_Similarity_Score"].sum()
    if w_total <= 0:
        return None

    top["Similarity_Weight"] = top["Final_Similarity_Score"] / w_total
    weight_map = dict(zip(top["Existing_SKU_ID"], top["Similarity_Weight"]))
    analog_ids = list(weight_map.keys())

    d = demand[demand["SKU_ID"].isin(analog_ids)].copy()
    if d.empty:
        return None

    d[qty_col]        = pd.to_numeric(d[qty_col], errors="coerce").fillna(0)
    d["sim_weight"]   = d["SKU_ID"].map(weight_map)
    d["weighted_qty"] = d["sim_weight"] * d[qty_col]

    grouped = d.groupby(["Store_ID", week_col]).agg(
        weighted_sum   = ("weighted_qty", "sum"),
        present_weight = ("sim_weight",   "sum"),
        analog_skus_used = ("SKU_ID",     "nunique"),
    ).reset_index()
    grouped["Analog_Demand"] = (grouped["weighted_sum"] / grouped["present_weight"]).round(2)

    out = pd.DataFrame({
        "New_SKU_ID":      new_sku_id,
        "Store_ID":        grouped["Store_ID"],
        "Year_WK":         grouped[week_col],
        "Analog_Demand":   grouped["Analog_Demand"],
        "Analog_SKUs_Used":grouped["analog_skus_used"],
    }).sort_values(["Store_ID", "Year_WK"]).reset_index(drop=True)

    return out


# ---------------------------------------------------------------------------
# Column validation
# ---------------------------------------------------------------------------
REQUIRED_COLS  = [ID_COL]
IMPORTANT_COLS = [
    "Product_Name", "Sub_Category", "Segment", "Attribute_Claim",
    "Brand", "Price_Band", "List_Price_USD", "Unit_Cost_USD",
]
OPTIONAL_COLS  = [
    "Pack_Size_ml", "Margin_Pct", "Organic_Flag", "Sulphate_Free_Flag",
    "Paraben_Free_Flag", "Hair_Fall_Flag", "Dandruff_Flag",
    "Color_Protection_Flag", "Ingredient_1", "Ingredient_2",
    "Ingredient_3", "Ingredient_4", "Hair_Type", "Age_Group",
]

def _validate_columns(cols: list[str]) -> dict:
    norm_cols = [str(c).strip().replace(" ", "_") for c in cols]
    missing_required  = [c for c in REQUIRED_COLS  if c not in norm_cols]
    missing_important = [c for c in IMPORTANT_COLS if c not in norm_cols]
    found_optional    = [c for c in OPTIONAL_COLS  if c in norm_cols]

    # Accept Product_Name as a fallback identifier if SKU_ID is missing
    if "SKU_ID" in missing_required and "Product_Name" in norm_cols:
        missing_required = [c for c in missing_required if c != "SKU_ID"]

    return {
        "missing_required":  missing_required,
        "missing_important": missing_important,
        "found_optional":    found_optional,
        "found_cols":        norm_cols,
        "valid":             len(missing_required) == 0,
    }


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------
def process_uploaded_csv(
    file_bytes: bytes,
    filename:   str = "upload.csv",
) -> dict[str, Any]:
    """
    Parse a CSV upload, run similarity + analog demand for every row.

    Returns
    -------
    {
      status:         "ok" | "partial" | "error"
      filename:       str
      total_rows:     int
      processed_skus: [{ sku_id, product_name, status, warnings, similarity_top3 }]
      column_report:  { missing_required, missing_important, found_cols }
      errors:         [str]
      uploaded_sku_ids: [str]
    }
    """
    errors: list[str] = []

    # Parse
    try:
        if filename.lower().endswith((".xlsx", ".xls")):
            df = pd.read_excel(io.BytesIO(file_bytes))
        else:
            df = pd.read_csv(io.BytesIO(file_bytes))
    except Exception as e:
        return {"status": "error", "errors": [f"Could not parse file: {e}"], "uploaded_sku_ids": []}

    if df.empty:
        return {"status": "error", "errors": ["Uploaded file contains no rows."], "uploaded_sku_ids": []}

    # Normalise column names
    df = normalize_column_names(df)

    # Validate columns
    col_report = _validate_columns(df.columns.tolist())
    if not col_report["valid"]:
        return {
            "status":       "error",
            "errors":       [f"Missing required columns: {col_report['missing_required']}"],
            "column_report": col_report,
            "uploaded_sku_ids": [],
        }

    # Auto-generate SKU_ID from Product_Name if absent
    if ID_COL not in df.columns:
        df[ID_COL] = df["Product_Name"].astype(str).str.replace(r"\s+", "_", regex=True).str[:20] + "_UPLOAD"

    # Fill blank SKU_IDs
    df[ID_COL] = df[ID_COL].fillna("").astype(str)
    mask_empty = df[ID_COL].str.strip() == ""
    if mask_empty.any():
        df.loc[mask_empty, ID_COL] = (
            "UPLOAD_" + df.loc[mask_empty].index.astype(str)
        )

    # Load SKU master
    master = _load_sku_master()
    if master.empty:
        return {
            "status": "error",
            "errors": ["SKU master file not found. Ensure Raw_Input/SKU_Master.csv exists."],
            "column_report": col_report,
            "uploaded_sku_ids": [],
        }

    # Process each row
    processed_skus = []
    uploaded_ids: list[str] = []

    for idx, row in df.iterrows():
        new_sku = row.to_dict()
        sku_id  = str(new_sku.get(ID_COL, f"ROW_{idx}")).strip()
        product_name = str(new_sku.get("Product_Name", sku_id))
        row_warnings: list[str] = []

        try:
            # Run similarity
            scores_df = _run_similarity_for_sku(new_sku, master)

            # Run analog demand
            analog_df = _run_analog_demand(scores_df)

            # Store in cache
            _SIM_CACHE[sku_id]    = scores_df
            if analog_df is not None:
                _ANALOG_CACHE[sku_id] = analog_df
            else:
                row_warnings.append("Analog demand could not be computed — demand file missing.")
            _ATTRS_CACHE[sku_id]  = {k: str(v) for k, v in new_sku.items() if pd.notna(v)}

            # Top 3 for preview
            top3 = scores_df.head(3)[
                ["Existing_SKU_ID", "Existing_Product_Name", "Final_Similarity_Score"]
            ].to_dict(orient="records")

            uploaded_ids.append(sku_id)
            processed_skus.append({
                "sku_id":        sku_id,
                "product_name":  product_name,
                "status":        "ok",
                "warnings":      row_warnings,
                "similarity_top3": top3,
                "best_analog":   top3[0]["Existing_Product_Name"] if top3 else "",
                "best_score":    round(float(top3[0]["Final_Similarity_Score"]), 3) if top3 else 0,
            })

        except Exception as e:
            errors.append(f"Row {idx} ('{sku_id}'): {e}")
            processed_skus.append({
                "sku_id":       sku_id,
                "product_name": product_name,
                "status":       "error",
                "warnings":     [str(e)],
            })

    overall_status = "ok" if not errors else ("partial" if uploaded_ids else "error")

    return {
        "status":          overall_status,
        "filename":        filename,
        "total_rows":      len(df),
        "processed_skus":  processed_skus,
        "column_report":   col_report,
        "errors":          errors,
        "uploaded_sku_ids":uploaded_ids,
    }
