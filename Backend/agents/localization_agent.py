"""
localization_agent.py
=====================
Detects where a global Continue/Delist recommendation conflicts with a store
cluster's actual performance.  Entirely rule-based — no LLM calls.
"""
from __future__ import annotations
import csv
import logging
import uuid
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Optional

import pandas as pd

from ..database.connection import read_table_or_csv
from .agent_core import divergence_magnitude, score_to_decision

log = logging.getLogger(__name__)

_PROJ     = Path(__file__).resolve().parent.parent.parent
_OUT      = _PROJ / "Outputs"
_RAW      = _PROJ / "Raw_Input"
_OVERRIDE = _OUT / "agent_localization_overrides.csv"

_OVERRIDE_COLS = [
    "override_id", "sku_id", "cluster_id", "cluster_label",
    "decision", "note", "decided_by", "decided_at",
]


# ---------------------------------------------------------------------------
# Cached loaders
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _delist():
    df = read_table_or_csv("delisting_recommendations", _OUT / "delisting_recommendations.csv")
    df["delist_score"] = pd.to_numeric(df["delist_score"], errors="coerce").fillna(0)
    df["total_revenue"] = pd.to_numeric(df["total_revenue"], errors="coerce").fillna(0)
    return df


@lru_cache(maxsize=1)
def _clusters():
    return read_table_or_csv("store_clusters", _OUT / "store_clusters.csv")


@lru_cache(maxsize=1)
def _sku_master():
    return read_table_or_csv("sku_master", _RAW / "SKU_Master.csv")


# ---------------------------------------------------------------------------
# Main: find divergent SKUs
# ---------------------------------------------------------------------------

def find_divergent_skus(
    sub_cat: Optional[str] = None,
    min_divergence: float   = 0.04,
) -> list[dict]:
    delist   = _delist()
    clusters = _clusters()
    sku_meta = _sku_master()

    # Store-level rows
    store_rows = delist[delist["granularity_level"] == "Store"].copy()
    if sub_cat:
        store_rows = store_rows[store_rows["Sub_Category"] == sub_cat]

    if store_rows.empty:
        log.warning("No Store-level delist rows found for sub_cat=%s", sub_cat)
        return []

    if clusters.empty:
        log.warning("store_clusters.csv is empty or missing — cannot compute divergence")
        return []

    # Join store → cluster
    store_rows = store_rows.merge(
        clusters[["Store_ID", "Cluster_ID", "Cluster_Label"]],
        left_on="granularity_value",
        right_on="Store_ID",
        how="left",
    )
    store_rows = store_rows.dropna(subset=["Cluster_ID"])

    # Aggregate per SKU × Cluster
    cluster_agg = (
        store_rows.groupby(["SKU_ID", "Cluster_ID", "Cluster_Label"], as_index=False)
        .agg(
            cluster_delist_score=("delist_score", "median"),
            store_count=("Store_ID", "nunique"),
            cluster_revenue=("total_revenue", "sum"),
        )
    )

    # Global-level rows for the same SKUs
    global_rows = delist[delist["granularity_level"] == "Global"].copy()
    if sub_cat:
        global_rows = global_rows[global_rows["Sub_Category"] == sub_cat]

    if global_rows.empty:
        # Fall back to aggregating all granularities as a proxy global score
        proxy_global = (
            delist.groupby("SKU_ID", as_index=False)
            .agg(
                global_delist_score=("delist_score", "median"),
                global_decision=("Decision", lambda x: x.mode().iloc[0] if len(x) else "MONITOR"),
            )
        )
    else:
        proxy_global = global_rows[["SKU_ID", "delist_score", "Decision"]].copy()
        proxy_global.columns = ["SKU_ID", "global_delist_score", "global_decision"]
        proxy_global = proxy_global.drop_duplicates("SKU_ID")

    merged = cluster_agg.merge(proxy_global, on="SKU_ID", how="inner")
    merged["divergence_magnitude"] = merged.apply(
        lambda r: divergence_magnitude(r["cluster_delist_score"], r["global_delist_score"]),
        axis=1,
    )
    divergent = merged[merged["divergence_magnitude"] >= min_divergence].copy()

    if divergent.empty:
        return []

    # SKU metadata join
    if len(sku_meta) > 0:
        meta_cols = [c for c in ["SKU_ID", "Product_Name", "Brand", "Sub_Category", "Supplier"]
                     if c in sku_meta.columns]
        divergent = divergent.merge(sku_meta[meta_cols], on="SKU_ID", how="left")

    # Group by SKU → one result per SKU with cluster_breakdown list
    result = []
    for sku_id, grp in divergent.groupby("SKU_ID"):
        row0 = grp.iloc[0]
        cluster_breakdown = []
        for _, cr in grp.iterrows():
            cluster_breakdown.append({
                "cluster_id":           str(int(cr["Cluster_ID"])),
                "cluster_label":        cr["Cluster_Label"],
                "cluster_delist_score": round(float(cr["cluster_delist_score"]), 3),
                "cluster_decision":     score_to_decision(cr["cluster_delist_score"]),
                "store_count":          int(cr["store_count"]),
                "cluster_revenue":      round(float(cr["cluster_revenue"]), 0),
            })

        max_div = float(grp["divergence_magnitude"].max())
        global_score = float(row0["global_delist_score"])

        result.append({
            "sku_id":              sku_id,
            "product_name":        str(row0.get("Product_Name", sku_id)),
            "brand":               str(row0.get("Brand", "")),
            "sub_category":        str(row0.get("Sub_Category", sub_cat or "")),
            "global_decision":     str(row0["global_decision"]),
            "global_delist_score": round(global_score, 3),
            "cluster_breakdown":   cluster_breakdown,
            "divergence_flag":     True,
            "divergence_magnitude": round(max_div, 3),
            "recommended_override": _recommend_override(global_score, cluster_breakdown),
        })

    result.sort(key=lambda x: -x["divergence_magnitude"])
    return result


def _recommend_override(global_score: float, breakdown: list[dict]) -> str:
    keeps  = [c["cluster_label"] for c in breakdown if c["cluster_decision"] == "Continue"]
    delists = [c["cluster_label"] for c in breakdown if c["cluster_decision"] == "Delist"]

    if global_score >= 0.6 and keeps:
        return f"Continue in {', '.join(keeps)}; proceed with Delist elsewhere"
    if global_score < 0.4 and delists:
        return f"Consider Delist in {', '.join(delists)}; Continue elsewhere"
    if keeps and delists:
        return f"Differentiate: Continue in {', '.join(keeps)}, Delist in {', '.join(delists)}"
    return "Review cluster-level decisions individually"


# ---------------------------------------------------------------------------
# Override persistence
# ---------------------------------------------------------------------------

def _ensure_overrides_file() -> None:
    if not _OVERRIDE.exists():
        _OUT.mkdir(parents=True, exist_ok=True)
        with open(_OVERRIDE, "w", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=_OVERRIDE_COLS).writeheader()


def record_override(
    sku_id:      str,
    cluster_id:  str,
    decision:    str,
    note:        str = "",
    decided_by:  str = "Category Manager",
) -> dict:
    _ensure_overrides_file()
    row_id = str(uuid.uuid4())[:8]
    row = {
        "override_id": row_id,
        "sku_id":      sku_id,
        "cluster_id":  cluster_id,
        "cluster_label": _cluster_label(cluster_id),
        "decision":    decision,
        "note":        note or "",
        "decided_by":  decided_by,
        "decided_at":  datetime.now(timezone.utc).isoformat(),
    }
    with open(_OVERRIDE, "a", newline="", encoding="utf-8") as f:
        csv.DictWriter(f, fieldnames=_OVERRIDE_COLS).writerow(row)
    log.info("Override recorded: sku=%s cluster=%s decision=%s", sku_id, cluster_id, decision)
    return {"status": "recorded", "row_id": row_id}


def _cluster_label(cluster_id: str) -> str:
    clusters = _clusters()
    if clusters.empty:
        return cluster_id
    match = clusters[clusters["Cluster_ID"].astype(str) == str(cluster_id)]
    if len(match):
        return str(match.iloc[0].get("Cluster_Label", cluster_id))
    return cluster_id


def list_overrides(
    sku_id:     Optional[str] = None,
    cluster_id: Optional[str] = None,
) -> list[dict]:
    if not _OVERRIDE.exists():
        return []
    import pandas as pd
    df = pd.read_csv(_OVERRIDE, dtype=str).fillna("")
    if sku_id:
        df = df[df["sku_id"] == sku_id]
    if cluster_id:
        df = df[df["cluster_id"] == cluster_id]
    return df.to_dict("records")
