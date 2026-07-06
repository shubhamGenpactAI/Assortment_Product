"""
copilot.py
AI Merchant Copilot — generates executive-quality decision summaries.

Produces 4 sections from real data:
  1. LAUNCH OVERVIEW    — what this product is, who it competes with
  2. MARKET OPPORTUNITY — where the demand is strongest
  3. RISK ASSESSMENT    — what could go wrong, ranked by severity
  4. STRATEGIC RECOMMENDATION — concrete merchant action recommendation

Language is concise, data-grounded, professional.
No generic AI filler phrases.
"""

from __future__ import annotations
from typing import Any


# ---------------------------------------------------------------------------
# Confidence qualifier
# ---------------------------------------------------------------------------
def _conf_qualifier(conf: float) -> str:
    if conf >= 0.75:
        return "with high confidence"
    elif conf >= 0.50:
        return "with moderate confidence"
    else:
        return "directionally (low analog coverage)"


def _risk_qualifier(risk: str) -> str:
    return {"High": "significant", "Medium": "moderate", "Low": "limited"}.get(risk, "some")


def _cannib_qualifier(rate: float) -> str:
    if rate >= 0.60:
        return "high"
    elif rate >= 0.35:
        return "moderate"
    else:
        return "low"


# ---------------------------------------------------------------------------
# Section generators
# ---------------------------------------------------------------------------

def _gen_launch_overview(
    new_sku_id:      str,
    new_sku_attrs:   dict,
    similarity_data: dict,
    forecast_data:   dict,
) -> str:
    name      = new_sku_attrs.get("Product_Name", new_sku_id)
    brand     = new_sku_attrs.get("Brand",        "Unknown Brand")
    sub_cat   = new_sku_attrs.get("Sub_Category", "Hair Care")
    segment   = new_sku_attrs.get("Segment",      "")
    price_band= new_sku_attrs.get("Price_Band",   "Mid-Tier")
    claim     = new_sku_attrs.get("Attribute_Claim", "")

    # Best analog
    best_analog_name = ""
    best_analog_score = 0.0
    if similarity_data and "top_analogs" in similarity_data:
        top = similarity_data["top_analogs"]
        if top:
            best_analog_name  = top[0].get("product_name", "")
            best_analog_score = top[0].get("similarity_score", 0)

    ent_units   = forecast_data.get("summary", {}).get("enterprise_total", {}).get("Units", 0) if forecast_data else 0
    ent_revenue = forecast_data.get("summary", {}).get("enterprise_total", {}).get("Revenue", 0) if forecast_data else 0
    avg_conf    = forecast_data.get("avg_confidence", 0.5) if forecast_data else 0.5
    n_stores    = forecast_data.get("summary", {}).get("store_count", 0) if forecast_data else 0

    parts = [
        f"{name} ({brand}) is a {price_band.lower()} {sub_cat} product"
        + (f" in the {segment} segment" if segment else "")
        + (f", positioned on {claim}" if claim else "") + ".",
    ]

    if best_analog_name:
        parts.append(
            f"Closest analog is {best_analog_name} "
            f"(similarity: {best_analog_score*100:.0f}%), "
            f"providing the primary demand reference for this forecast."
        )

    if ent_units > 0:
        parts.append(
            f"Base case forecast: {round(ent_units):,} units / ${ent_revenue:,.0f} revenue "
            f"over {forecast_data.get('summary', {}).get('week_count', 6)} weeks across "
            f"{n_stores} stores {_conf_qualifier(avg_conf)}."
        )

    return " ".join(parts)


def _gen_market_opportunity(
    forecast_data:    dict,
    store_rec_data:   dict,
    whitespace_data:  dict,
    cannib_data:      dict,
) -> str:
    parts = []

    # Best cluster
    cluster_sum = forecast_data.get("summary", {}).get("by_cluster", {}) if forecast_data else {}
    if cluster_sum:
        best_c = max(cluster_sum, key=lambda k: cluster_sum[k].get("Units", 0))
        best_c_units = cluster_sum[best_c].get("Units", 0)
        parts.append(
            f"Demand is concentrated in the '{best_c}' cluster "
            f"({round(best_c_units):,} units — highest velocity stores)."
        )

    # Store recommendation
    n_rec   = store_rec_data.get("n_recommended", 0)   if store_rec_data else 0
    n_total = store_rec_data.get("n_total",       0)   if store_rec_data else 0
    if n_rec and n_total:
        fit_pct = n_rec / max(n_total, 1) * 100
        parts.append(
            f"{n_rec} of {n_total} stores ({fit_pct:.0f}%) score above the launch threshold, "
            f"supporting a phased rollout strategy."
        )

    # Incrementality opportunity
    increm_rate = cannib_data.get("incrementality_rate", 0) if cannib_data else 0
    if increm_rate >= 0.50:
        parts.append(
            f"Strong category incrementality: ~{increm_rate*100:.0f}% of demand is expected to be new to the category."
        )

    # Whitespace
    top_ws = whitespace_data.get("top_opportunity", {}) if whitespace_data else {}
    if top_ws:
        parts.append(
            f"Whitespace opportunity: {top_ws.get('gap_label', 'adjacent assortment gap')} "
            f"remains under-served in the current range."
        )

    return " ".join(parts) if parts else "Insufficient data to assess market opportunity."


def _gen_risk_assessment(
    cannib_data:    dict,
    forecast_data:  dict,
    store_rec_data: dict,
    risks_data:     dict,
) -> str:
    parts = []

    if risks_data:
        high_risks   = [r for r in risks_data.get("risks", []) if r["severity"] == "High"]
        medium_risks = [r for r in risks_data.get("risks", []) if r["severity"] == "Medium"]

        if high_risks:
            parts.append("Critical risks: " + "; ".join(r["factor"] for r in high_risks[:2]) + ".")
        if medium_risks:
            parts.append("Watch: " + "; ".join(r["factor"] for r in medium_risks[:2]) + ".")

    cannib_rate  = cannib_data.get("cannibalization_rate", 0) if cannib_data else 0
    cannib_qual  = _cannib_qualifier(cannib_rate)
    top_impacted = ""
    if cannib_data and cannib_data.get("impacted_skus"):
        top_impacted = cannib_data["impacted_skus"][0].get("product_name", "")

    if top_impacted:
        parts.append(
            f"{_risk_qualifier(cannib_data.get('risk_level', 'Medium')).capitalize()} cannibalization risk "
            f"against {top_impacted} "
            f"(~{cannib_rate*100:.0f}% demand transfer expected)."
        )

    avg_conf = forecast_data.get("avg_confidence", 0.5) if forecast_data else 0.5
    if avg_conf < 0.50:
        parts.append(
            f"Forecast reliability is limited ({avg_conf*100:.0f}% confidence) — "
            f"recommend small-scale test launch before full rollout."
        )

    return " ".join(parts) if parts else "No material risk factors identified. Proceed with standard launch protocol."


def _gen_strategic_recommendation(
    new_sku_attrs:  dict,
    forecast_data:  dict,
    cannib_data:    dict,
    store_rec_data: dict,
    risks_data:     dict,
) -> str:
    avg_conf   = forecast_data.get("avg_confidence",   0.5) if forecast_data else 0.5
    cannib_score = cannib_data.get("cannibalization_score", 0.3) if cannib_data else 0.3
    n_rec      = store_rec_data.get("n_recommended",    0)  if store_rec_data else 0
    n_total    = store_rec_data.get("n_total",          0)  if store_rec_data else 0
    fit_pct    = (n_rec / max(n_total, 1)) if n_total else 0

    high_risk  = risks_data.get("highest_severity") == "High" if risks_data else False

    # Decision logic
    if avg_conf >= 0.65 and cannib_score < 0.40 and fit_pct >= 0.60 and not high_risk:
        action = "Full national launch"
        rationale = (
            f"Strong analog coverage, low cannibalization risk, and broad store fit "
            f"({n_rec}/{n_total} stores) support a full rollout."
        )
        phases = [
            f"Phase 1: Immediate launch in {n_rec} qualifying stores.",
            "Phase 2: Monitor velocity weekly for 4 weeks.",
            "Phase 3: Expand to remaining stores if Phase 1 velocity exceeds forecast.",
        ]

    elif avg_conf >= 0.45 and fit_pct >= 0.35:
        top_cluster = ""
        cs = store_rec_data.get("cluster_summary", []) if store_rec_data else []
        if cs:
            top_cluster = cs[0].get("cluster_label", "")
        action = "Phased launch"
        rationale = (
            f"Moderate confidence and focused store fit suggest a staged approach. "
            + (f"Begin in '{top_cluster}' cluster where analog performance is strongest." if top_cluster else "")
        )
        phases = [
            f"Phase 1 (Weeks 1–4): Launch in top {min(n_rec, 5)} stores across best cluster.",
            "Phase 2 (Weeks 5–10): Expand based on Phase 1 sell-through rate.",
            "Phase 3 (Weeks 11+): Full rollout if Phase 2 velocity meets target.",
        ]

    else:
        action = "Test-and-learn pilot"
        rationale = (
            f"Low forecast confidence or high cannibalization risk ({cannib_score*100:.0f}%) "
            f"warrants a limited pilot before full commitment."
        )
        phases = [
            "Phase 1 (Weeks 1–6): 3–5 store pilot in highest-scoring stores.",
            "Phase 2: Evaluate sell-through, cannibalization impact, and basket metrics.",
            "Phase 3: Full launch or delist based on pilot data.",
        ]

    rec = f"RECOMMENDATION: {action}. {rationale}"
    rec += " Suggested rollout: " + " → ".join(phases)
    return rec


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def generate_copilot_summary(
    new_sku_id:       str,
    new_sku_attrs:    dict,
    similarity_data:  dict,
    forecast_data:    dict,
    cannib_data:      dict,
    store_rec_data:   dict,
    whitespace_data:  dict,
    risks_data:       dict,
) -> dict[str, Any]:
    """
    Generates a full 4-section executive briefing.

    Returns:
      launch_overview      — str
      market_opportunity   — str
      risk_assessment      — str
      recommendation       — str
      confidence_band      — High / Medium / Low
      decision_signal      — Go / Conditional Go / Test / No-Go
      one_liner            — ultra-short summary for dashboard card
    """
    launch_overview = _gen_launch_overview(
        new_sku_id, new_sku_attrs, similarity_data, forecast_data)

    market_opportunity = _gen_market_opportunity(
        forecast_data, store_rec_data, whitespace_data, cannib_data)

    risk_assessment = _gen_risk_assessment(
        cannib_data, forecast_data, store_rec_data, risks_data)

    recommendation = _gen_strategic_recommendation(
        new_sku_attrs, forecast_data, cannib_data, store_rec_data, risks_data)

    # Decision signal
    avg_conf     = forecast_data.get("avg_confidence",    0.5) if forecast_data else 0.5
    cannib_score = cannib_data.get("cannibalization_score", 0.3) if cannib_data else 0.3
    n_rec        = store_rec_data.get("n_recommended",    0) if store_rec_data else 0
    n_total      = store_rec_data.get("n_total",          1) if store_rec_data else 1
    fit_pct      = n_rec / max(n_total, 1)
    high_risk    = risks_data.get("highest_severity") == "High" if risks_data else False

    if avg_conf >= 0.65 and cannib_score < 0.40 and fit_pct >= 0.60 and not high_risk:
        decision_signal = "Go"
        confidence_band = "High"
    elif avg_conf >= 0.45 and fit_pct >= 0.35 and not high_risk:
        decision_signal = "Conditional Go"
        confidence_band = "Medium"
    elif high_risk or avg_conf < 0.35:
        decision_signal = "Test"
        confidence_band = "Low"
    else:
        decision_signal = "Conditional Go"
        confidence_band = "Medium"

    # One-liner
    ent_rev = forecast_data.get("summary", {}).get("enterprise_total", {}).get("Revenue", 0) if forecast_data else 0
    one_liner = (
        f"{decision_signal} — ${ent_rev:,.0f} revenue potential, "
        f"{_cannib_qualifier(cannib_score)} cannibalization risk, "
        f"{n_rec} stores recommended."
    )

    return {
        "launch_overview":    launch_overview,
        "market_opportunity": market_opportunity,
        "risk_assessment":    risk_assessment,
        "recommendation":     recommendation,
        "decision_signal":    decision_signal,
        "confidence_band":    confidence_band,
        "one_liner":          one_liner,
    }
