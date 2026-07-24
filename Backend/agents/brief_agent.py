"""
brief_agent.py
==============
Builds structured, exportable stakeholder briefs from existing Outputs/ CSVs.
Three brief types: vendor_negotiation | cross_sell | delist_rationale.
All text generation is deterministic (f-string templates); LLM is optional tone-polish only.
"""
from __future__ import annotations
import json
import logging
import uuid
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from ..database.connection import read_table_or_csv

# Supplier_Rating tiers, recomputed at SKU (not Store x SKU) grain here since
# the vendor table is one row per SKU — mirrors the thresholds used in
# Backend/pipelines/inventory_planning/safety_stock_supplier.py.
_SUPPLIER_RATING_A_CUTOFF = 0.70
_SUPPLIER_RATING_B_CUTOFF = 0.30

log = logging.getLogger(__name__)

_PROJ       = Path(__file__).resolve().parent.parent.parent
_OUT        = _PROJ / "Outputs"
_RAW        = _PROJ / "Raw_Input"
_BRIEFS_DIR = _OUT / "agent_briefs"

BRIEF_TYPES = ("vendor_negotiation", "cross_sell", "delist_rationale")


# ---------------------------------------------------------------------------
# Cached loaders
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _assoc():
    df = read_table_or_csv("association_rules", _OUT / "association_rules.csv")
    for c in ["lift", "confidence", "support_pair"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)
    return df


@lru_cache(maxsize=1)
def _basket():
    df = read_table_or_csv("sku_basket_insights", _OUT / "sku_basket_insights.csv")
    for c in ["basket_dependency_score", "promo_halo_impact", "basket_revenue_impact"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)
    return df


@lru_cache(maxsize=1)
def _delist():
    df = read_table_or_csv("delisting_recommendations", _OUT / "delisting_recommendations.csv")
    for c in ["delist_score", "total_revenue", "total_margin", "Health_Score"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)
    return df


@lru_cache(maxsize=1)
def _sku_master():
    return read_table_or_csv("sku_master", _RAW / "SKU_Master.csv")


@lru_cache(maxsize=1)
def _safety_supplier_sku_level():
    """
    Rolls Backend/pipelines/inventory_planning/safety_stock_supplier.py's
    Store_ID x SKU_ID output up to one row per SKU_ID (averaging across
    stores), and recomputes Supplier_Rating at that grain.
    """
    df = read_table_or_csv("safety_stock_supplier_scores", _OUT / "safety_stock_supplier_scores.csv")
    if df.empty:
        return df
    for c in ["Lead_Time_Target_Days", "SKU_Store_Fill_Rate_Pct_3M", "Sell_Through_Pct",
              "Margin_Pct", "Supplier_Confidence_Score"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    agg = df.groupby("SKU_ID").agg(
        EAN_ID=("EAN_ID", "first"),
        Product_Name=("Product_Name", "first"),
        Supplier=("Supplier", "first"),
        Lead_Time_Target_Days=("Lead_Time_Target_Days", "mean"),
        Fill_Rate_Pct=("SKU_Store_Fill_Rate_Pct_3M", "mean"),
        Sell_Through_Pct=("Sell_Through_Pct", "mean"),
        Margin_Pct=("Margin_Pct", "mean"),
        Supplier_Confidence_Score=("Supplier_Confidence_Score", "mean"),
    ).reset_index()

    n = len(agg)
    rank = agg["Supplier_Confidence_Score"].rank(pct=True, method="average") if n > 1 else pd.Series([1.0] * n)
    agg["Supplier_Rating"] = np.select(
        [rank >= _SUPPLIER_RATING_A_CUTOFF, rank >= _SUPPLIER_RATING_B_CUTOFF],
        ["A", "B"],
        default="C",
    )
    return agg


@lru_cache(maxsize=1)
def _sales_by_sku():
    """Total SKU-level Sales ($) — the 'Global' granularity row of delisting_recommendations.csv."""
    delist = _delist()
    if delist.empty or "granularity_level" not in delist.columns:
        return pd.DataFrame(columns=["SKU_ID", "Sales_USD"])
    sales = (delist[delist["granularity_level"] == "Global"]
             .drop_duplicates("SKU_ID")[["SKU_ID", "total_revenue"]]
             .rename(columns={"total_revenue": "Sales_USD"}))
    return sales


# ---------------------------------------------------------------------------
# Scope resolution
# ---------------------------------------------------------------------------

def _resolve_sku_ids(brand: Optional[str], sub_cat: Optional[str], sku_ids: Optional[list]) -> list[str]:
    sku = _sku_master()
    if sku.empty:
        delist = _delist()
        candidates = delist["SKU_ID"].unique().tolist()
    else:
        candidates = sku.copy()
        if brand:
            candidates = candidates[candidates["Brand"] == brand]
        if sub_cat:
            candidates = candidates[candidates["Sub_Category"] == sub_cat]
        candidates = candidates["SKU_ID"].tolist()

    if sku_ids:
        candidates = [s for s in candidates if s in sku_ids] if candidates != sku["SKU_ID"].tolist() else sku_ids

    return list(dict.fromkeys(candidates))


def _sku_name(sku_id: str) -> str:
    sku = _sku_master()
    if sku.empty:
        return sku_id
    row = sku[sku["SKU_ID"] == sku_id]
    return str(row.iloc[0]["Product_Name"]) if len(row) else sku_id


# ---------------------------------------------------------------------------
# Template generators
# ---------------------------------------------------------------------------

def _vendor_negotiation_sections(sku_ids: list[str], brand: str, sub_cat: str) -> list[dict]:
    assoc   = _assoc()
    delist  = _delist()
    sku     = _sku_master()

    sections = []

    # ── 1. Executive Overview ─────────────────────────────────────────────
    scope_label = brand or sub_cat or "Selected SKUs"
    sku_count   = len(sku_ids)
    overview    = (
        f"This brief covers {sku_count} SKU(s) within the {scope_label} portfolio. "
        "The following analysis provides data-backed talking points for vendor negotiation, "
        "structured around cross-sell performance, underperforming lines, and suggested commitments."
    )
    sections.append({"heading": "Executive Overview", "body": overview})

    # ── 2. Cross-sell strength ────────────────────────────────────────────
    if not assoc.empty and sku_ids:
        top_pairs = (
            assoc[assoc["antecedent_sku"].isin(sku_ids) | assoc["consequent_sku"].isin(sku_ids)]
            .nlargest(5, "lift")[["antecedent_sku", "consequent_sku", "lift", "confidence"]]
        )
        if not top_pairs.empty:
            lines = []
            for _, row in top_pairs.iterrows():
                a = _sku_name(row["antecedent_sku"])
                b = _sku_name(row["consequent_sku"])
                lines.append(
                    f"  • {a} → {b}: lift {row['lift']:.2f}x, "
                    f"confidence {row['confidence']*100:.1f}%"
                )
            sections.append({
                "heading": "Cross-Sell Strengths (Basket Analysis)",
                "body": "Top basket pairs support a joint-placement or bundle negotiation:\n" + "\n".join(lines),
            })
        else:
            sections.append({
                "heading": "Cross-Sell Strengths (Basket Analysis)",
                "body": "No statistically significant basket pairs found for the selected scope.",
            })

    # ── 3. Underperforming lines ──────────────────────────────────────────
    if not delist.empty and sku_ids:
        weak = (
            delist[delist["SKU_ID"].isin(sku_ids) & (delist["delist_score"] >= 0.6)]
            .drop_duplicates("SKU_ID")
            .nlargest(5, "delist_score")
        )
        if not weak.empty:
            lines = []
            for _, row in weak.iterrows():
                narr = str(row.get("Recommendation_Narrative", ""))[:120]
                lines.append(
                    f"  • {_sku_name(row['SKU_ID'])}: delist score {row['delist_score']:.2f}. "
                    f"{narr}..."
                )
            sections.append({
                "heading": "Lines Recommended for Rationalisation",
                "body": (
                    "The following SKUs underperform on health score, GMROI, and/or "
                    "basket dependency and should be addressed in negotiations:\n" + "\n".join(lines)
                ),
            })
        else:
            sections.append({
                "heading": "Lines Recommended for Rationalisation",
                "body": "No SKUs in this scope currently reach the rationalisation threshold (delist score ≥ 0.60).",
            })

    # ── 4. Suggested asks ─────────────────────────────────────────────────
    basket_df = _basket()
    if not basket_df.empty and sku_ids:
        anchors = basket_df[basket_df["SKU_ID"].isin(sku_ids)].nlargest(3, "basket_dependency_score")
        asks = []
        for _, row in anchors.iterrows():
            asks.append(
                f"  • Secure priority shelf placement for {_sku_name(row['SKU_ID'])} "
                f"(basket dependency score: {row['basket_dependency_score']:.0f})"
            )
        if asks:
            sections.append({"heading": "Suggested Negotiation Asks", "body": "\n".join(asks)})

    return sections


def _vendor_negotiation_table(sku_ids: list[str], brand: str, sub_cat: str) -> Optional[list[dict]]:
    """
    One row per SKU (Supplier, SKU ID, EAN ID, SKU Name, Lead Time Target,
    Fill Rate, Supplier Rating, Sell Through, Margin, Sales, Confidence
    Score), scoped to the SKUs matching the Vendor Negotiation brief's
    Brand/Sub-Category filters. Returns None when neither filter is set, or
    when no source data is available for the scope.
    """
    if not (brand or sub_cat) or not sku_ids:
        return None

    agg = _safety_supplier_sku_level()
    if agg.empty:
        return None

    scoped = agg[agg["SKU_ID"].isin(sku_ids)].copy()
    if scoped.empty:
        return None

    scoped = scoped.merge(_sales_by_sku(), on="SKU_ID", how="left")
    scoped["Sales_USD"] = pd.to_numeric(scoped["Sales_USD"], errors="coerce").fillna(0)
    scoped = scoped.sort_values("Sales_USD", ascending=False)

    rows = []
    for _, r in scoped.iterrows():
        rows.append({
            "supplier":              r.get("Supplier") or "",
            "sku_id":                r["SKU_ID"],
            "ean_id":                str(int(r["EAN_ID"])) if pd.notna(r.get("EAN_ID")) else "",
            "sku_name":              r.get("Product_Name") or r["SKU_ID"],
            "lead_time_target_days": round(r["Lead_Time_Target_Days"]) if pd.notna(r.get("Lead_Time_Target_Days")) else None,
            "fill_rate_pct":         round(r["Fill_Rate_Pct"] * 100, 1) if pd.notna(r.get("Fill_Rate_Pct")) else None,
            "supplier_rating":       r.get("Supplier_Rating") or "",
            "sell_through_pct":      round(r["Sell_Through_Pct"] * 100, 1) if pd.notna(r.get("Sell_Through_Pct")) else None,
            "margin_pct":            round(r["Margin_Pct"], 1) if pd.notna(r.get("Margin_Pct")) else None,
            "sales_usd":             round(r["Sales_USD"], 2),
            "confidence_score":      round(r["Supplier_Confidence_Score"] * 100, 1) if pd.notna(r.get("Supplier_Confidence_Score")) else None,
        })
    return rows


def _cross_sell_sections(sku_ids: list[str], brand: str, sub_cat: str) -> list[dict]:
    assoc  = _assoc()
    basket = _basket()

    sections = []

    scope_label = brand or sub_cat or "Selected Scope"
    sections.append({
        "heading": "Scope",
        "body": f"Cross-sell opportunities for {scope_label} ({len(sku_ids)} SKU(s)).",
    })

    # Top bundle pairs
    if not assoc.empty and sku_ids:
        top_pairs = (
            assoc[assoc["antecedent_sku"].isin(sku_ids)]
            .nlargest(8, "lift")[["antecedent_sku", "consequent_sku", "lift", "confidence", "co_occurrence_count"]]
        )
        if not top_pairs.empty:
            lines = []
            for _, row in top_pairs.iterrows():
                a = _sku_name(row["antecedent_sku"])
                b = _sku_name(row["consequent_sku"])
                lines.append(
                    f"  • {a} + {b}: lift {row['lift']:.2f}x, "
                    f"confidence {row['confidence']*100:.1f}%, "
                    f"{int(row['co_occurrence_count'])} co-occurrences"
                )
            sections.append({
                "heading": "Top Basket Pairs (by Lift)",
                "body": "\n".join(lines),
            })
        else:
            sections.append({
                "heading": "Top Basket Pairs (by Lift)",
                "body": "No statistically significant basket pairs found for this scope.",
            })

    # Promo halo candidates
    if not basket.empty and sku_ids:
        promo = (
            basket[basket["SKU_ID"].isin(sku_ids)]
            .assign(halo_abs=lambda df: df["promo_halo_impact"].abs())
            .nlargest(5, "halo_abs")
        )
        if not promo.empty:
            lines = []
            for _, row in promo.iterrows():
                direction = "lift" if row["promo_halo_impact"] >= 0 else "drag"
                lines.append(
                    f"  • {_sku_name(row['SKU_ID'])}: promo {direction} "
                    f"${abs(row['promo_halo_impact']):.0f}"
                )
            sections.append({"heading": "Promo Halo Candidates", "body": "\n".join(lines)})

    # Cross-category relationships
    if not basket.empty and sku_ids:
        cross = basket[basket["SKU_ID"].isin(sku_ids) & basket["cross_category_relationships"].notna()]
        if not cross.empty:
            lines = []
            for _, row in cross.head(5).iterrows():
                lines.append(
                    f"  • {_sku_name(row['SKU_ID'])}: {row['cross_category_relationships']}"
                )
            sections.append({"heading": "Cross-Category Placement Opportunities", "body": "\n".join(lines)})

    return sections


def _delist_rationale_sections(sku_ids: list[str], brand: str, sub_cat: str) -> list[dict]:
    delist = _delist()

    sections = []
    scope_label = brand or sub_cat or "Selected SKUs"
    sections.append({
        "heading": "Scope",
        "body": f"Delist rationale brief for {scope_label} ({len(sku_ids)} SKU(s)).",
    })

    if delist.empty or not sku_ids:
        sections.append({
            "heading": "Rationale",
            "body": "No qualifying data for this scope.",
        })
        return sections

    scoped = delist[delist["SKU_ID"].isin(sku_ids)].drop_duplicates("SKU_ID")
    if scoped.empty:
        sections.append({
            "heading": "Rationale",
            "body": "No qualifying data for this scope.",
        })
        return sections

    for _, row in scoped.nlargest(len(scoped), "delist_score").iterrows():
        narr   = str(row.get("Recommendation_Narrative", "N/A"))
        action = str(row.get("Recommended_Action", row.get("Decision", "Review")))
        reason = str(row.get("Decision_Reason", ""))
        name   = _sku_name(row["SKU_ID"])
        body   = (
            f"**Delist score:** {row['delist_score']:.2f}  |  "
            f"**Decision:** {row.get('Decision', 'N/A')}  |  "
            f"**Basket role:** {row.get('Basket_Role', 'Unknown')}\n\n"
            f"**Rationale:** {narr}\n\n"
            f"**Recommended action:** {action}"
        )
        if reason:
            body += f"\n\n**Decision reason:** {reason}"
        sections.append({"heading": f"SKU: {name}", "body": body})

    return sections


# ---------------------------------------------------------------------------
# Build brief
# ---------------------------------------------------------------------------

def build_brief(
    brief_type: str,
    brand:      Optional[str] = None,
    sub_cat:    Optional[str] = None,
    sku_ids:    Optional[list] = None,
    generated_by: str = "Category Manager",
) -> dict:
    if brief_type not in BRIEF_TYPES:
        raise ValueError(f"Unknown brief_type '{brief_type}'. Must be one of {BRIEF_TYPES}")

    resolved_sku_ids = _resolve_sku_ids(brand, sub_cat, sku_ids)
    if not resolved_sku_ids:
        sections = [{"heading": "No Data", "body": "No qualifying data for this scope."}]
    elif brief_type == "vendor_negotiation":
        sections = _vendor_negotiation_sections(resolved_sku_ids, brand or "", sub_cat or "")
    elif brief_type == "cross_sell":
        sections = _cross_sell_sections(resolved_sku_ids, brand or "", sub_cat or "")
    else:
        sections = _delist_rationale_sections(resolved_sku_ids, brand or "", sub_cat or "")

    vendor_table = (
        _vendor_negotiation_table(resolved_sku_ids, brand or "", sub_cat or "")
        if brief_type == "vendor_negotiation" else None
    )

    brief_id = str(uuid.uuid4())[:12]
    md  = _to_markdown(brief_type, brand, sub_cat, sections)
    txt = _to_text(sections)

    brief = {
        "brief_id":     brief_id,
        "brief_type":   brief_type,
        "scope":        {"brand": brand, "sub_cat": sub_cat, "sku_ids": resolved_sku_ids[:20]},
        "sections":     sections,
        "vendor_table": vendor_table,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generated_by": generated_by,
        "polish_failed": False,
        "export":       {"markdown": md, "text": txt},
    }

    _persist_brief(brief)
    return brief


def _to_markdown(brief_type: str, brand: str, sub_cat: str, sections: list[dict]) -> str:
    scope_label = brand or sub_cat or "All"
    title = brief_type.replace("_", " ").title()
    lines = [f"# {title} Brief — {scope_label}", ""]
    for s in sections:
        lines.append(f"## {s['heading']}")
        lines.append(s["body"])
        lines.append("")
    return "\n".join(lines)


def _to_text(sections: list[dict]) -> str:
    lines = []
    for s in sections:
        lines.append(s["heading"].upper())
        lines.append("-" * len(s["heading"]))
        lines.append(s["body"])
        lines.append("")
    return "\n".join(lines)


def _persist_brief(brief: dict) -> None:
    _BRIEFS_DIR.mkdir(parents=True, exist_ok=True)
    path = _BRIEFS_DIR / f"{brief['brief_id']}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(brief, f, indent=2, default=str)


# ---------------------------------------------------------------------------
# Retrieval
# ---------------------------------------------------------------------------

def get_brief(brief_id: str) -> Optional[dict]:
    path = _BRIEFS_DIR / f"{brief_id}.json"
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def list_briefs(brand: Optional[str] = None, sub_cat: Optional[str] = None) -> list[dict]:
    if not _BRIEFS_DIR.exists():
        return []
    summaries = []
    for p in sorted(_BRIEFS_DIR.glob("*.json"), key=lambda x: x.stat().st_mtime, reverse=True)[:50]:
        try:
            with open(p, encoding="utf-8") as f:
                b = json.load(f)
            scope = b.get("scope", {})
            if brand and scope.get("brand") != brand:
                continue
            if sub_cat and scope.get("sub_cat") != sub_cat:
                continue
            summaries.append({
                "brief_id":     b["brief_id"],
                "brief_type":   b["brief_type"],
                "scope":        scope,
                "generated_at": b["generated_at"],
                "generated_by": b.get("generated_by", ""),
            })
        except Exception:
            pass
    return summaries


def build_polish_context(brief: dict) -> dict:
    return {
        "brief_type": brief["brief_type"],
        "scope":      brief["scope"],
        "sections":   brief["sections"],
    }
