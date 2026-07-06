"""
whitespace_detector.py
Detects assortment gaps and whitespace opportunities.

A whitespace is an attribute combination with:
  - high market demand signals (growth, sentiment)
  - low or zero current SKU coverage

Algorithm
---------
1. Build attribute lattice: Sub_Category × Segment × Price_Band × Key_Claim
2. Mark cells with existing active SKUs
3. Score empty/sparse cells by:
     opportunity_score = 0.40 × market_growth_signal
                       + 0.25 × sentiment_signal
                       + 0.20 × category_trend_signal
                       + 0.15 × competitor_gap_signal
4. Rank and filter to top-N gaps

Inputs
------
  Raw_Input/SKU_Master.csv
  Raw_Input/Reviews_Social.csv
  Raw_Input/Market_Data.csv
  Raw_Input/Sales_Tx.csv
"""

from __future__ import annotations
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from ..database.connection import read_table_or_csv

_ROOT = Path(__file__).resolve().parent.parent.parent
_RAW  = _ROOT / "Raw_Input"
_OUT  = _ROOT / "Outputs"

_cache: dict[str, pd.DataFrame] = {}

def _load(key: str, path: Path) -> pd.DataFrame:
    if key not in _cache:
        _cache[key] = read_table_or_csv(path.stem.lower(), path)
    return _cache[key]

def _sku_master()  -> pd.DataFrame: return _load("sm",  _RAW / "SKU_Master.csv")
def _reviews()     -> pd.DataFrame: return _load("rev", _RAW / "Reviews_Social.csv")
def _market()      -> pd.DataFrame: return _load("mkt", _RAW / "Market_Data.csv")
def _sales_tx()    -> pd.DataFrame: return _load("tx",  _RAW / "Sales_Tx.csv")


# ---------------------------------------------------------------------------
# Signal builders
# ---------------------------------------------------------------------------

def _market_growth_signal() -> pd.DataFrame:
    """Returns DataFrame with (Sub_Category → growth_signal 0-1)."""
    mkt = _market()
    if mkt.empty:
        return pd.DataFrame(columns=["Sub_Category", "market_growth_signal"])

    col_subcat = "Sub_Category" if "Sub_Category" in mkt.columns else None
    col_growth = None
    for c in ["Category_Growth_Pct", "Category Growth %", "market_growth"]:
        if c in mkt.columns:
            col_growth = c
            break

    if not col_subcat or not col_growth:
        return pd.DataFrame(columns=["Sub_Category", "market_growth_signal"])

    mkt[col_growth] = pd.to_numeric(mkt[col_growth], errors="coerce")
    agg = mkt.groupby(col_subcat)[col_growth].mean().reset_index()
    agg.columns = ["Sub_Category", "raw_growth"]
    min_g, max_g = agg["raw_growth"].min(), agg["raw_growth"].max()
    agg["market_growth_signal"] = (agg["raw_growth"] - min_g) / max(max_g - min_g, 1e-6)
    return agg[["Sub_Category", "market_growth_signal"]]


def _sentiment_signal() -> pd.DataFrame:
    """Avg review sentiment per (Sub_Category, key keyword) → signal 0-1."""
    rev = _reviews()
    if rev.empty or "Sentiment_Score" not in rev.columns:
        return pd.DataFrame(columns=["Sub_Category", "Keyword", "sentiment_signal"])

    rev["Sentiment_Score"] = pd.to_numeric(rev["Sentiment_Score"], errors="coerce")
    grp_cols = [c for c in ["Sub_Category", "Keyword"] if c in rev.columns]
    if not grp_cols:
        return pd.DataFrame(columns=["Sub_Category", "Keyword", "sentiment_signal"])

    agg = rev.groupby(grp_cols)["Sentiment_Score"].mean().reset_index()
    agg.columns = grp_cols + ["raw_sentiment"]
    min_s, max_s = agg["raw_sentiment"].min(), agg["raw_sentiment"].max()
    agg["sentiment_signal"] = (agg["raw_sentiment"] - min_s) / max(max_s - min_s, 1e-6)
    return agg[grp_cols + ["sentiment_signal"]]


def _sales_trend_signal() -> pd.DataFrame:
    """Recent revenue growth per Sub_Category from Sales_Tx."""
    tx = _sales_tx()
    if tx.empty or "Sub_Category" not in tx.columns:
        return pd.DataFrame(columns=["Sub_Category", "sales_trend_signal"])

    if "Net_Sales_USD" not in tx.columns:
        return pd.DataFrame(columns=["Sub_Category", "sales_trend_signal"])

    tx["Net_Sales_USD"] = pd.to_numeric(tx["Net_Sales_USD"], errors="coerce").fillna(0)

    # Try to use time column if available
    date_col = None
    for c in ["Date", "Transaction_Date", "Year_WK"]:
        if c in tx.columns:
            date_col = c
            break

    agg = tx.groupby("Sub_Category")["Net_Sales_USD"].sum().reset_index()
    agg.columns = ["Sub_Category", "total_sales"]
    min_s, max_s = agg["total_sales"].min(), agg["total_sales"].max()
    agg["sales_trend_signal"] = (agg["total_sales"] - min_s) / max(max_s - min_s, 1e-6)
    return agg[["Sub_Category", "sales_trend_signal"]]


# ---------------------------------------------------------------------------
# Lattice builder
# ---------------------------------------------------------------------------

def _build_lattice() -> pd.DataFrame:
    """
    Return all meaningful attribute combinations from SKU_Master with:
      - Sub_Category, Segment, Price_Band, Attribute_Claim
      - sku_count (number of active SKUs in this cell)
    """
    sm = _sku_master()
    if sm.empty:
        return pd.DataFrame()

    dim_cols = [c for c in ["Sub_Category", "Segment", "Price_Band", "Attribute_Claim"] if c in sm.columns]
    if not dim_cols:
        return pd.DataFrame()

    sm_active = sm.copy()
    if "Status" in sm.columns:
        sm_active = sm_active[sm_active["Status"].str.lower().isin(["active", "1", "yes", "listed"]) |
                               sm_active["Status"].isna()]

    # Fill missing dimension values
    for c in dim_cols:
        sm_active[c] = sm_active[c].fillna("Not Specified")

    lattice = sm_active.groupby(dim_cols).size().reset_index(name="sku_count")
    return lattice


def _candidate_gaps(lattice: pd.DataFrame) -> pd.DataFrame:
    """
    Generate candidate gap cells: cross-product of dimension values minus covered cells.
    Limit to same-sub-category expansions.
    """
    if lattice.empty:
        return pd.DataFrame()

    sm = _sku_master()
    dim_cols = [c for c in ["Sub_Category", "Segment", "Price_Band", "Attribute_Claim"] if c in lattice.columns]

    # Get unique values for each dimension
    dim_values = {}
    for c in dim_cols:
        if c in sm.columns:
            dim_values[c] = sm[c].dropna().unique().tolist()
        else:
            dim_values[c] = lattice[c].unique().tolist()

    # Cross-product
    import itertools
    combos = list(itertools.product(*[dim_values[c] for c in dim_cols]))
    full_grid = pd.DataFrame(combos, columns=dim_cols)

    # Left join to find gaps
    full_grid = full_grid.merge(lattice, on=dim_cols, how="left")
    full_grid["sku_count"] = full_grid["sku_count"].fillna(0).astype(int)

    # Gap = sku_count == 0
    gaps = full_grid[full_grid["sku_count"] == 0].copy()
    return gaps


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def detect_whitespace(
    focus_sub_category: str | None = None,
    top_n: int = 15,
) -> dict[str, Any]:
    """
    Returns:
      whitespace_gaps  — ranked list of opportunity cells
      covered_cells    — existing SKU coverage stats
      top_opportunity  — single best gap with narrative
      summary          — merchant-friendly summary
    """
    lattice = _build_lattice()
    if lattice.empty:
        return {"error": "SKU Master not found or has no usable dimension columns."}

    # Filter to focus sub-category if provided
    if focus_sub_category and "Sub_Category" in lattice.columns:
        lattice_focus = lattice[lattice["Sub_Category"] == focus_sub_category]
        if lattice_focus.empty:
            lattice_focus = lattice
    else:
        lattice_focus = lattice

    gaps = _candidate_gaps(lattice_focus)
    if gaps.empty:
        return {
            "whitespace_gaps": [],
            "covered_cells":   len(lattice),
            "summary":         "No whitespace gaps detected — full attribute coverage in current assortment.",
        }

    # Attach signals
    growth_sig = _market_growth_signal()
    trend_sig  = _sales_trend_signal()

    if not growth_sig.empty and "Sub_Category" in gaps.columns:
        gaps = gaps.merge(growth_sig, on="Sub_Category", how="left")
    else:
        gaps["market_growth_signal"] = 0.5

    if not trend_sig.empty and "Sub_Category" in gaps.columns:
        gaps = gaps.merge(trend_sig, on="Sub_Category", how="left")
    else:
        gaps["sales_trend_signal"] = 0.5

    gaps["market_growth_signal"] = gaps["market_growth_signal"].fillna(0.5)
    gaps["sales_trend_signal"]   = gaps["sales_trend_signal"].fillna(0.5)

    # Attribute-level premium bonus
    def _claim_bonus(row: pd.Series) -> float:
        claim = str(row.get("Attribute_Claim", "") or "").lower()
        bonus = 0.0
        for kw in ["organic", "protein", "anti-frizz", "heat protect", "keratin"]:
            if kw in claim:
                bonus += 0.1
        return min(bonus, 0.30)

    gaps["attribute_signal"] = gaps.apply(_claim_bonus, axis=1)

    # Composite opportunity score
    gaps["opportunity_score"] = (
        0.40 * gaps["market_growth_signal"] +
        0.35 * gaps["sales_trend_signal"]   +
        0.25 * gaps["attribute_signal"]
    )
    gaps["opportunity_score"] = gaps["opportunity_score"].clip(0, 1).round(4)

    # Focus sub-cat filter for output
    if focus_sub_category and "Sub_Category" in gaps.columns:
        gaps_out = gaps[gaps["Sub_Category"] == focus_sub_category].nlargest(top_n, "opportunity_score")
    else:
        gaps_out = gaps.nlargest(top_n, "opportunity_score")

    # Build result list
    dim_cols = [c for c in ["Sub_Category", "Segment", "Price_Band", "Attribute_Claim"] if c in gaps_out.columns]
    gap_list = []
    for _, row in gaps_out.iterrows():
        label_parts = [str(row.get(c, "?")) for c in dim_cols]
        label = " → ".join(p for p in label_parts if p not in ("Not Specified", "?", "nan"))
        gap_list.append({
            "gap_label":        label,
            "opportunity_score": float(row["opportunity_score"]),
            "market_growth":    round(float(row["market_growth_signal"]), 4),
            "category_trend":   round(float(row["sales_trend_signal"]), 4),
            "attribute_signal": round(float(row["attribute_signal"]), 4),
            "dimensions":       {c: str(row.get(c, "")) for c in dim_cols},
        })

    top_opp = gap_list[0] if gap_list else {}

    # Top opportunity narrative
    if top_opp:
        top_nl = (
            f"Highest whitespace opportunity: {top_opp['gap_label']} "
            f"(opportunity score: {top_opp['opportunity_score']*100:.0f}/100). "
            f"Market growth signal: {top_opp['market_growth']*100:.0f}%. "
            f"No current SKUs cover this space."
        )
    else:
        top_nl = "No significant whitespace detected in the current assortment."

    return {
        "whitespace_gaps":   gap_list,
        "n_gaps_found":      len(gap_list),
        "covered_cells":     int(len(lattice_focus)),
        "top_opportunity":   top_opp,
        "top_opportunity_nl":top_nl,
        "summary": (
            f"Identified {len(gap_list)} whitespace gap(s) across "
            f"{len(gaps_out['Sub_Category'].unique()) if 'Sub_Category' in gaps_out.columns else '?'} sub-categories. "
            f"Top opportunity: {top_opp.get('gap_label', 'N/A')}."
        ),
    }
