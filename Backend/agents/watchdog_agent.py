"""
watchdog_agent.py
=================
Merges exception alerts + risk matrix signals into one ranked worklist.
Detects conflicts (same SKU appearing with opposing signals) and computes
a priority score for each item.
"""
from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional

from ..services.decision_hub_service import (
    get_exception_alerts,
    get_risk_matrix,
    get_lost_sales,
    get_category_health_scores,
)
from .agent_core import priority_score, dedupe_by_key, trim

_CONFLICT_PAIRS = [
    {"Stock-out Risk", "Delist Candidate"},
    {"Stock-out Risk", "Delist Candidate"},
    {"Growth Opportunity", "Delist Candidate"},
    {"Demand Surge", "Delist Candidate"},
]


def _risk_to_severity(risk_bucket: str) -> str:
    if risk_bucket in ("Stock-out Risk", "Delist Candidate"):
        return "red"
    if risk_bucket in ("Excess Inventory", "Transfer Candidate", "Demand Drop", "Demand Surge"):
        return "orange"
    return "green"


def _signal_from_alert_title(title: str) -> str:
    if "Stockout Risk" in title or "Stock-out" in title:
        return "Stock-out Risk"
    if "Demand Surge" in title:
        return "Demand Surge"
    if "Demand Drop" in title:
        return "Demand Drop"
    if "Delist Candidate" in title:
        return "Delist Candidate"
    if "Growth Opportunity" in title:
        return "Growth Opportunity"
    return "Alert"


def _is_conflict(signal_types: list[str]) -> bool:
    signal_set = set(signal_types)
    for pair in _CONFLICT_PAIRS:
        if pair.issubset(signal_set):
            return True
    return False


def _suggested_action(item: dict) -> str:
    if item["conflict"]:
        return "Escalate: conflicting signals — resolve before reordering"
    sig = item["signal_types"][0] if item["signal_types"] else ""
    mapping = {
        "Stock-out Risk":      "Replenish Now",
        "Delist Candidate":    "Review Delisting",
        "Growth Opportunity":  "Expand Assortment",
        "Demand Surge":        "Increase Replenishment",
        "Demand Drop":         "Reduce Open Orders",
        "Excess Inventory":    "Reduce Orders / Transfer",
        "Transfer Candidate":  "Transfer Stock",
    }
    return mapping.get(sig, "Review")


def _narrative(item: dict) -> str:
    name  = item.get("product_name", item.get("sku_id", ""))[:35]
    store = item.get("store_id", "")
    sigs  = " and ".join(item.get("signal_types", []))
    fin   = item.get("financial_impact_usd", 0)
    src   = item.get("source_signals", {})

    if item["conflict"]:
        pairs = " AND ".join(item["signal_types"])
        return (
            f"{name} (Store {store}) has conflicting signals: {pairs}. "
            f"Financial exposure: ${fin:,.0f}. Resolve conflict before taking action."
        )

    sig = item["signal_types"][0] if item["signal_types"] else ""
    if sig == "Stock-out Risk":
        woc = src.get("WoC") or src.get("woc")
        woc_str = f" — {woc:.1f} weeks cover remaining" if woc else ""
        return f"{name} (Store {store}) is at Stockout Risk{woc_str}. Lost revenue exposure: ${fin:,.0f}."
    if sig == "Delist Candidate":
        ds = src.get("delist_score")
        ds_str = f" (delist score {ds:.2f})" if ds else ""
        return f"{name} (Store {store}) is a Delist Candidate{ds_str}. Forecast revenue: ${fin:,.0f}."
    if sig == "Growth Opportunity":
        return f"{name} (Store {store}) shows a Growth Opportunity with ${fin:,.0f} in forecast revenue."
    if sig in ("Demand Surge", "Demand Drop"):
        return f"{name} (Store {store}) has a {sig}. Forecast revenue: ${fin:,.0f}."

    return f"{name} (Store {store}): {sigs}. Financial impact: ${fin:,.0f}."


def build_digest(
    store_id: Optional[str] = None,
    sub_cat:  Optional[str] = None,
    cluster:  Optional[str] = None,
    top_n:    int = 10,
) -> dict:
    top_n = max(1, min(top_n, 50))

    # ── Pull all signal sources ───────────────────────────────────────────
    alerts = get_exception_alerts(store_id, sub_cat, cluster)
    matrix = get_risk_matrix(store_id, sub_cat, cluster)

    # ── Build item index keyed by (sku_id, store_id) ─────────────────────
    idx: dict[tuple, dict] = {}

    for a in alerts:
        key = (a["sku_id"], a["store_id"])
        sig = _signal_from_alert_title(a["title"])
        if key not in idx:
            idx[key] = {
                "sku_id":              a["sku_id"],
                "store_id":            a["store_id"],
                "product_name":        a["title"].split("–")[-1].strip() if "–" in a["title"] else a["title"],
                "signal_types":        [sig],
                "severity":            a["severity"],
                "financial_impact_usd": float(a["financial"]),
                "source_signals":      {"detail": a.get("detail", "")},
            }
        else:
            ex = idx[key]
            if sig not in ex["signal_types"]:
                ex["signal_types"].append(sig)
            if a["severity"] == "red" and ex["severity"] != "red":
                ex["severity"] = "red"
            ex["financial_impact_usd"] = max(ex["financial_impact_usd"], float(a["financial"]))

    for r in matrix:
        key = (r["SKU_ID"], r["Store_ID"])
        sig = r["risk_bucket"]
        sev = _risk_to_severity(sig)
        fin = float(r.get("financial_impact_usd") or 0)
        if key not in idx:
            idx[key] = {
                "sku_id":              r["SKU_ID"],
                "store_id":            r["Store_ID"],
                "product_name":        r.get("Product_Name", r["SKU_ID"]),
                "signal_types":        [sig],
                "severity":            sev,
                "financial_impact_usd": fin,
                "source_signals":      {
                    "risk_bucket":  sig,
                    "action":       r.get("action"),
                    "WoC":          r.get("WoC"),
                    "delist_score": r.get("delist_score"),
                },
            }
        else:
            ex = idx[key]
            if sig not in ex["signal_types"]:
                ex["signal_types"].append(sig)
            if sev == "red" and ex["severity"] != "red":
                ex["severity"] = "red"
            ex["financial_impact_usd"] = max(ex["financial_impact_usd"], fin)
            ex["source_signals"].update({
                "risk_bucket":  sig,
                "WoC":          r.get("WoC"),
                "delist_score": r.get("delist_score"),
            })

    # ── Score and rank ────────────────────────────────────────────────────
    all_items = list(idx.values())
    max_fin   = max((i["financial_impact_usd"] for i in all_items), default=1) or 1

    for item in all_items:
        item["conflict"] = _is_conflict(item["signal_types"])
        item["priority_score"] = priority_score(
            item["severity"],
            item["financial_impact_usd"],
            max_fin,
            item["conflict"],
        )
        item["suggested_action"] = _suggested_action(item)
        item["narrative"]        = _narrative(item)

    ranked = sorted(all_items, key=lambda x: (-x["priority_score"], -x["financial_impact_usd"]))
    top    = ranked[:top_n]
    for i, item in enumerate(top):
        item["priority_rank"] = i + 1

    red    = sum(1 for x in top if x["severity"] == "red")
    orange = sum(1 for x in top if x["severity"] == "orange")
    green  = sum(1 for x in top if x["severity"] == "green")
    total_fin = round(sum(x["financial_impact_usd"] for x in top), 0)

    return {
        "generated_at":   datetime.now(timezone.utc).isoformat(),
        "filters_applied": {"store_id": store_id, "sub_cat": sub_cat, "cluster": cluster},
        "summary": {
            "total_items":              len(top),
            "red":                      red,
            "orange":                   orange,
            "green":                    green,
            "total_financial_impact_usd": total_fin,
        },
        "items": top,
    }


def build_narrative_context(digest: dict) -> dict:
    """Trim the digest to a safe LLM context (no raw transaction data)."""
    return {
        "summary": digest["summary"],
        "top_items": trim(digest["items"][:10], [
            "priority_rank", "sku_id", "product_name", "store_id",
            "signal_types", "conflict", "severity",
            "financial_impact_usd", "suggested_action", "narrative",
        ]),
        "filters": digest["filters_applied"],
    }
