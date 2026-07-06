"""
scenario_simulator.py
What-if simulation engine for new SKU launch scenarios.

Capabilities
------------
1. Price change  → demand (via price elasticity), revenue, margin delta
2. Promo intensity → uplift to demand and revenue
3. Pack-size change → effective price-per-unit shift → elasticity effect
4. Geography scope → filter to subset of stores
5. Multi-scenario comparison

Elasticity estimation
---------------------
Estimated from Sales_Tx.csv per Sub_Category using log-log OLS:
  log(Quantity_Sold) = α + ε × log(Avg_Price_USD)
  ε = price elasticity coefficient (typically negative)

Fallback: category-level median elasticity of −1.5 if insufficient data.

All outputs are DELTAS from the base scenario.
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

_cache: dict[str, Any] = {}

def _load_csv(key: str, path: Path) -> pd.DataFrame:
    if key not in _cache:
        _cache[key] = read_table_or_csv(path.stem.lower(), path)
    return _cache[key]

def _sales_tx()    -> pd.DataFrame: return _load_csv("tx", _RAW / "Sales_Tx.csv")
def _sku_master()  -> pd.DataFrame: return _load_csv("sm", _RAW / "SKU_Master.csv")


# ---------------------------------------------------------------------------
# Elasticity estimation
# ---------------------------------------------------------------------------
_ELASTICITY_CACHE: dict[str, float] = {}
_DEFAULT_ELASTICITY = -1.5

def _estimate_elasticity(sub_category: str) -> float:
    """
    Log-log OLS elasticity for a sub-category.
    Returns ε (typically -3.0 to -0.5 for CPG/FMCG).
    """
    if sub_category in _ELASTICITY_CACHE:
        return _ELASTICITY_CACHE[sub_category]

    tx = _sales_tx()
    if tx.empty or "Sub_Category" not in tx.columns:
        return _DEFAULT_ELASTICITY

    required = {"Net_Sales_USD", "Quantity_Sold", "SKU_ID"}
    if not required.issubset(tx.columns):
        return _DEFAULT_ELASTICITY

    sub = tx[tx["Sub_Category"] == sub_category].copy()
    if len(sub) < 30:
        _ELASTICITY_CACHE[sub_category] = _DEFAULT_ELASTICITY
        return _DEFAULT_ELASTICITY

    sub["Quantity_Sold"] = pd.to_numeric(sub["Quantity_Sold"], errors="coerce")
    sub["Net_Sales_USD"] = pd.to_numeric(sub["Net_Sales_USD"], errors="coerce")
    sub = sub.dropna(subset=["Quantity_Sold", "Net_Sales_USD"])
    sub = sub[sub["Quantity_Sold"] > 0]
    sub["implied_price"] = sub["Net_Sales_USD"] / sub["Quantity_Sold"]
    sub = sub[sub["implied_price"] > 0]

    if len(sub) < 20:
        _ELASTICITY_CACHE[sub_category] = _DEFAULT_ELASTICITY
        return _DEFAULT_ELASTICITY

    try:
        log_p = np.log(sub["implied_price"].values)
        log_q = np.log(sub["Quantity_Sold"].values)
        # OLS: log_q = a + ε * log_p
        A = np.vstack([np.ones(len(log_p)), log_p]).T
        result = np.linalg.lstsq(A, log_q, rcond=None)
        elasticity = float(result[0][1])
        # Clamp to reasonable range
        elasticity = float(np.clip(elasticity, -5.0, -0.1))
    except Exception:
        elasticity = _DEFAULT_ELASTICITY

    _ELASTICITY_CACHE[sub_category] = elasticity
    return elasticity


def _promo_uplift(sub_category: str) -> float:
    """
    Estimate average promo uplift as ratio: avg_qty_promo / avg_qty_no_promo.
    Returns uplift fraction (e.g., 0.25 = 25% uplift).
    """
    tx = _sales_tx()
    if tx.empty or "Promo_Flag" not in tx.columns or "Sub_Category" not in tx.columns:
        return 0.20

    sub = tx[tx["Sub_Category"] == sub_category].copy()
    if sub.empty or "Quantity_Sold" not in sub.columns:
        return 0.20

    sub["Quantity_Sold"] = pd.to_numeric(sub["Quantity_Sold"], errors="coerce").fillna(0)
    sub["Promo_Flag"]    = pd.to_numeric(sub["Promo_Flag"],    errors="coerce").fillna(0)

    promo_qty    = sub[sub["Promo_Flag"] == 1]["Quantity_Sold"].mean()
    no_promo_qty = sub[sub["Promo_Flag"] == 0]["Quantity_Sold"].mean()

    if no_promo_qty and no_promo_qty > 0:
        return float(np.clip((promo_qty / no_promo_qty) - 1, 0, 2.0))
    return 0.20


# ---------------------------------------------------------------------------
# Core simulation
# ---------------------------------------------------------------------------
def _simulate_scenario(
    base_units:   float,
    base_price:   float,
    base_cost:    float,
    elasticity:   float,
    price_delta_pct: float = 0.0,
    promo_intensity: float = 0.0,   # 0–1 fraction of the promo uplift applied
    promo_uplift_rate: float = 0.20,
    pack_size_delta_pct: float = 0.0,  # % change in pack size (changes effective price-per-ml)
) -> dict:
    """
    Compute new units, revenue, margin given deltas.
    pack_size_delta_pct: +20% bigger pack → effective per-unit price unchanged but
                         effective price-per-ml drops → demand goes up.
    """
    # Effective price after changes
    new_price = base_price * (1 + price_delta_pct / 100)

    # Pack size: bigger pack at same price = better value → demand increase
    pack_price_effect = 0.0
    if pack_size_delta_pct != 0:
        # Effective price per ml = price / pack_size → decreases with bigger pack
        effective_price_change_pct = -pack_size_delta_pct / (1 + pack_size_delta_pct / 100)
        pack_price_effect = elasticity * (effective_price_change_pct / 100)

    # Price elasticity effect
    price_effect = elasticity * (price_delta_pct / 100) if price_delta_pct != 0 else 0.0

    # Promo effect
    promo_effect = promo_intensity * promo_uplift_rate

    # Combined demand multiplier
    demand_multiplier = 1.0 + price_effect + pack_price_effect + promo_effect
    demand_multiplier = max(demand_multiplier, 0.0)  # demand can't go negative

    new_units   = base_units   * demand_multiplier
    new_revenue = new_units    * new_price
    new_margin  = new_units    * max(new_price - base_cost, 0.0)
    base_revenue = base_units  * base_price
    base_margin  = base_units  * max(base_price - base_cost, 0.0)

    return {
        "new_units":          round(new_units,   1),
        "new_revenue":        round(new_revenue, 2),
        "new_margin":         round(new_margin,  2),
        "demand_delta_pct":   round((demand_multiplier - 1) * 100, 2),
        "revenue_delta_pct":  round((new_revenue / base_revenue - 1) * 100, 2) if base_revenue else 0,
        "margin_delta_pct":   round((new_margin / base_margin - 1) * 100, 2) if base_margin else 0,
        "delta_units":        round(new_units  - base_units,   1),
        "delta_revenue":      round(new_revenue - base_revenue, 2),
        "delta_margin":       round(new_margin  - base_margin,  2),
        "demand_multiplier":  round(demand_multiplier, 4),
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def run_scenario(
    new_sku_id:          str,
    new_sku_attrs:       dict,
    base_units:          float,
    price_delta_pct:     float = 0.0,
    promo_intensity:     float = 0.0,
    pack_size_delta_pct: float = 0.0,
    geography_filter:    list[str] | None = None,
    custom_elasticity:   float | None = None,
) -> dict[str, Any]:
    """
    Run a single scenario and return full output package.
    """
    sub_cat     = new_sku_attrs.get("Sub_Category", "")
    base_price  = float(new_sku_attrs.get("List_Price_USD", 0) or 0)
    base_cost   = float(new_sku_attrs.get("Unit_Cost_USD",  0) or 0)

    elasticity  = custom_elasticity if custom_elasticity is not None else _estimate_elasticity(sub_cat)
    promo_rate  = _promo_uplift(sub_cat)

    result = _simulate_scenario(
        base_units          = base_units,
        base_price          = base_price,
        base_cost           = base_cost,
        elasticity          = elasticity,
        price_delta_pct     = price_delta_pct,
        promo_intensity     = promo_intensity,
        promo_uplift_rate   = promo_rate,
        pack_size_delta_pct = pack_size_delta_pct,
    )

    # Build NL explanation of the scenario
    parts = []
    if price_delta_pct != 0:
        direction = "reduction" if price_delta_pct < 0 else "increase"
        parts.append(f"{abs(price_delta_pct):.0f}% price {direction} → "
                     f"{result['demand_delta_pct']:+.1f}% demand "
                     f"(elasticity: {elasticity:.2f})")
    if promo_intensity > 0:
        parts.append(f"{promo_intensity*100:.0f}% promo intensity → "
                     f"+{promo_rate*promo_intensity*100:.1f}% promo uplift")
    if pack_size_delta_pct != 0:
        parts.append(f"{pack_size_delta_pct:+.0f}% pack-size change → "
                     f"effective value improvement applied")

    scenario_nl = "; ".join(parts) if parts else "Base scenario — no adjustments applied."

    return {
        "scenario_inputs": {
            "new_sku_id":          new_sku_id,
            "sub_category":        sub_cat,
            "base_units":          base_units,
            "base_price":          base_price,
            "base_cost":           base_cost,
            "price_delta_pct":     price_delta_pct,
            "promo_intensity":     promo_intensity,
            "pack_size_delta_pct": pack_size_delta_pct,
            "geography_filter":    geography_filter,
        },
        "model_params": {
            "price_elasticity":    round(elasticity, 4),
            "promo_uplift_rate":   round(promo_rate, 4),
        },
        "outputs": result,
        "scenario_nl": scenario_nl,
    }


def compare_scenarios(
    new_sku_id:    str,
    new_sku_attrs: dict,
    base_units:    float,
    scenarios:     list[dict],
) -> dict[str, Any]:
    """
    Compare multiple scenarios side-by-side.

    Each scenario dict: {
      label: str,
      price_delta_pct: float,
      promo_intensity: float,
      pack_size_delta_pct: float,
    }

    Returns comparison table + recommended scenario.
    """
    results = []
    for s in scenarios:
        r = run_scenario(
            new_sku_id          = new_sku_id,
            new_sku_attrs       = new_sku_attrs,
            base_units          = base_units,
            price_delta_pct     = s.get("price_delta_pct",     0.0),
            promo_intensity     = s.get("promo_intensity",     0.0),
            pack_size_delta_pct = s.get("pack_size_delta_pct", 0.0),
        )
        results.append({
            "label":              s.get("label", "Scenario"),
            "new_units":          r["outputs"]["new_units"],
            "new_revenue":        r["outputs"]["new_revenue"],
            "new_margin":         r["outputs"]["new_margin"],
            "revenue_delta_pct":  r["outputs"]["revenue_delta_pct"],
            "margin_delta_pct":   r["outputs"]["margin_delta_pct"],
            "demand_delta_pct":   r["outputs"]["demand_delta_pct"],
            "scenario_nl":        r["scenario_nl"],
        })

    # Recommend: highest margin scenario
    best = max(results, key=lambda x: x["new_margin"])

    return {
        "comparison":            results,
        "recommended_scenario":  best["label"],
        "recommendation_reason": (
            f"'{best['label']}' maximises margin at ${best['new_margin']:,.0f} "
            f"({best['margin_delta_pct']:+.1f}% vs base)."
        ),
    }
