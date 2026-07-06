# New SKU Simulation & Assortment Intelligence — Architecture

## System Architecture

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                   AI ASSORTMENT DECISION INTELLIGENCE PLATFORM               │
├──────────────────────────────────────────────────────────────────────────────┤
│  PRESENTATION LAYER  (React/TypeScript + Vite → port 5173)                  │
│  ┌──────────────────────────────────────────────────────────────────────┐   │
│  │  NewSkuPage.tsx  — "New SKU Intelligence Hub"                        │   │
│  │  ├── AI Copilot Summary (4-card executive briefing)                  │   │
│  │  ├── Analog SKU Matching + Attribute Contribution Donut              │   │
│  │  ├── Hierarchical Forecast Panel (tabs: Enterprise/Cluster/Store)    │   │
│  │  ├── Cannibalization Analysis (donut + impacted SKU table)           │   │
│  │  ├── Store Launch Recommendation (scored + rollout phases)           │   │
│  │  ├── Scenario Simulation (6 pre-built + custom)                      │   │
│  │  ├── Risk Assessment (ranked + severity)                             │   │
│  │  └── Assortment White Space (opportunity gaps ranked)                │   │
│  └──────────────────────────────────────────────────────────────────────┘   │
├──────────────────────────────────────────────────────────────────────────────┤
│  API LAYER  (FastAPI → port 8000)                                           │
│  Backend/routers/new_sku.py                                                 │
│  POST /api/new-sku/intelligence  ← primary endpoint (full pipeline)         │
│  GET  /api/new-sku/list          ← available new SKUs                       │
│  GET  /api/new-sku/forecast/{id} ← hierarchical forecast only               │
│  GET  /api/new-sku/cannibalization/{id}                                     │
│  GET  /api/new-sku/stores/{id}   ← store recommendation                    │
│  POST /api/new-sku/scenario      ← custom what-if simulation               │
│  GET  /api/new-sku/whitespace    ← gap detection                           │
│  GET  /api/new-sku/analogs/{id}  ← top analogs + explanations              │
├──────────────────────────────────────────────────────────────────────────────┤
│  SERVICE LAYER                                                              │
│  Backend/services/new_sku_service.py — thin adapter                        │
├──────────────────────────────────────────────────────────────────────────────┤
│  ML / ENGINE LAYER  (Backend/NewSKU/)                                       │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────────────┐  │
│  │ sku_intelligence │  │hierarchical_     │  │ cannibalization.py       │  │
│  │ .py (orchestrator│  │forecast.py       │  │ demand transfer + increm.│  │
│  └──────────────────┘  └──────────────────┘  └──────────────────────────┘  │
│  ┌──────────────────┐  ┌──────────────────┐  ┌──────────────────────────┐  │
│  │ store_recommender│  │scenario_simulator│  │ explainer.py             │  │
│  │ .py (5 signals)  │  │.py (elasticity)  │  │ NL rule-based engine     │  │
│  └──────────────────┘  └──────────────────┘  └──────────────────────────┘  │
│  ┌──────────────────┐  ┌──────────────────┐                               │
│  │whitespace_       │  │ copilot.py       │                               │
│  │detector.py       │  │ executive summary│                               │
│  └──────────────────┘  └──────────────────┘                               │
├──────────────────────────────────────────────────────────────────────────────┤
│  EXISTING BACKEND MODULES (feeds into new modules)                         │
│  ├── similarity.py       → new_sku_similarity_scores.csv                   │
│  ├── forecasting.py      → new_sku_analog_demand_forecast.csv              │
│  ├── basket_analysis.py  → demand_transfer_matrix.csv, sku_basket_insights │
│  └── cluster.py          → store_clusters.csv                              │
├──────────────────────────────────────────────────────────────────────────────┤
│  DATA LAYER                                                                 │
│  Raw_Input/  SKU_Master, Store_Master, Sales_Tx, Reviews_Social, Market_Data│
│  Outputs/    new_sku_similarity_scores, new_sku_analog_demand_forecast,     │
│              demand_transfer_matrix, sku_basket_insights, store_clusters    │
└──────────────────────────────────────────────────────────────────────────────┘
```

## Module Responsibilities

| Module | Responsibility | Key Algorithm |
|--------|---------------|---------------|
| `hierarchical_forecast.py` | Aggregate analog demand Store→Cluster→Region→Enterprise | Weighted sum + confidence intervals from similarity quality |
| `cannibalization.py` | Estimate demand transfer from existing SKUs | Composite coef: 0.50×similarity + 0.25×price_proximity + 0.25×basket_sub |
| `store_recommender.py` | Score and rank stores for launch | 5-factor weighted score (velocity, demographics, cluster, penetration, price) |
| `scenario_simulator.py` | What-if simulations | Log-log OLS price elasticity per sub-category from Sales_Tx |
| `explainer.py` | Rule-based NL explanations | Template filling with actual data values |
| `whitespace_detector.py` | Gap detection | Attribute lattice + market growth + sentiment signals |
| `copilot.py` | Executive decision summary | Data-grounded narrative with Go/Conditional Go/Test signal |
| `sku_intelligence.py` | Orchestrator | Calls all engines, assembles unified payload |

## Data Flow

```
New SKU ID + Optional Attrs
          │
          ▼
   sku_intelligence.py (orchestrator)
          │
    ┌─────┴──────┐
    │            │
    ▼            ▼
similarity    hierarchical_forecast
  scores        (Store→Enterprise)
    │                │
    │           total_units
    │                │
    ▼                ▼
explainability   cannibalization    store_recommender
  (NL reasons)   (transfer %)       (launch scores)
                      │
                      ▼
               scenario_simulator  whitespace_detector
               (price/promo/pack)  (gap ranking)
                      │
                      ▼
                  copilot.py
                (Go/Test/No-Go)
                      │
                      ▼
              Unified JSON payload
                      │
              FastAPI /intelligence
                      │
              React NewSkuPage.tsx
```

## Cannibalization Methodology

```
cannib_coef(i) = 0.50 × similarity_score(i)
               + 0.25 × price_proximity(i)      [1 - |ΔPrice| / max_range]
               + 0.25 × basket_substitution(i)  [from sku_basket_insights]

If demand_transfer_matrix has historical data:
cannib_coef(i) = 0.40×sim + 0.20×price + 0.20×basket + 0.20×historical_transfer

cannibalization_rate = Σ(cannib_coef) / N  [capped at 0.90]
incrementality_rate  = 1 - cannibalization_rate
```

## Price Elasticity Estimation

```
Estimated from Sales_Tx.csv per sub-category:
  log(Quantity_Sold) = α + ε × log(implied_price)
  OLS regression, clamped to [-5.0, -0.1]
  Fallback: ε = -1.5 (CPG FMCG median)

Scenario demand:
  new_units = base_units × (1 + ε × Δ%price/100 + promo_intensity × promo_uplift)
```

## Store Scoring Formula

```
score = 0.35 × analog_velocity_score     (mean weekly demand, normalised)
      + 0.25 × demographic_fit_score      (income/organic/age alignment)
      + 0.20 × cluster_affinity_score     (cluster-level analog velocity)
      + 0.10 × category_penetration_score (sub-cat share of store revenue)
      + 0.10 × price_compatibility_score  (price/basket value ratio)

Launch phases:
  ≥0.70 → Phase 1 — Immediate
  ≥0.45 → Phase 2 — 4–8 Weeks
  ≥0.25 → Phase 3 — 8–16 Weeks
  <0.25  → Phase 4 — Do Not Launch
```

## Forecast Confidence

```
confidence = 0.6 × best_analog_similarity + 0.4 × (min(n_analogs, 5) / 5)
interval_half_width = (1 - confidence) × 0.40
Units_Lower = Units × (1 - interval_half_width)
Units_Upper = Units × (1 + interval_half_width)
sparse_analog_flag = True if n_analogs < 2
```

## Whitespace Detection

```
1. Build attribute lattice: Sub_Category × Segment × Price_Band × Attribute_Claim
2. Mark cells with existing active SKUs (sku_count > 0)
3. Score empty cells:
   opportunity_score = 0.40 × market_growth_signal
                     + 0.35 × sales_trend_signal
                     + 0.25 × attribute_signal (keyword bonus for premium claims)
4. Rank by opportunity_score descending
```

## Copilot Decision Signal Logic

```
Go              → avg_conf ≥ 0.65 AND cannib_score < 0.40 AND fit_pct ≥ 0.60 AND no_high_risk
Conditional Go  → avg_conf ≥ 0.45 AND fit_pct ≥ 0.35 AND no_high_risk
Test            → high_risk OR avg_conf < 0.35
No-Go           → (reserved for future rule)
```

## API Contract — /api/new-sku/intelligence

### Request
```json
{
  "new_sku_id": "SKU_NEW_001",
  "new_sku_attrs": {
    "Sub_Category": "Conditioner",
    "Price_Band": "Premium",
    "List_Price_USD": 12.99,
    "Unit_Cost_USD": 4.50,
    "Organic_Flag": 1
  },
  "top_n_analogs": 5,
  "top_n_stores": 10
}
```

### Response structure
```json
{
  "new_sku_id": "SKU_NEW_001",
  "new_sku_attrs": { ... },
  "similarity": { "top_analogs": [...], "n_analogs": 5 },
  "hierarchical_forecast": {
    "store": [...], "cluster": [...], "region": [...], "enterprise": [...],
    "summary": { "enterprise_total": {"Units": 1200, "Revenue": 15588, "Margin": 4800} },
    "avg_confidence": 0.72, "sparse_stores": []
  },
  "cannibalization": {
    "cannibalization_rate": 0.38, "incrementality_rate": 0.62,
    "cannibalized_units": 456, "incremental_units": 744,
    "risk_level": "Medium", "category_net_effect": "Positive",
    "impacted_skus": [...], "summary_nl": "..."
  },
  "store_recommendation": {
    "stores": [...], "cluster_summary": [...],
    "top_stores": [...], "n_recommended": 8, "n_total": 10
  },
  "scenarios": {
    "comparison": [...],
    "recommended_scenario": "Price −5%",
    "recommendation_reason": "..."
  },
  "explainability": {
    "similarity_explanations": [...],
    "difference_explanations": [...],
    "forecast_explanation": { "headline": "...", "drivers": [...] },
    "risk_explanation": { "risks": [...], "highest_severity": "Medium" },
    "attribute_contributions": { "ranked_detail": [...], "summary": "..." }
  },
  "whitespace": { "whitespace_gaps": [...], "top_opportunity": {...} },
  "copilot": {
    "launch_overview": "...", "market_opportunity": "...",
    "risk_assessment": "...", "recommendation": "...",
    "decision_signal": "Conditional Go", "confidence_band": "Medium",
    "one_liner": "Conditional Go — $15,588 revenue potential, moderate cannibalization risk, 8 stores recommended."
  },
  "status": "ok",
  "errors": []
}
```

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 18 + TypeScript + Vite |
| Charts | Plotly.js via react-plotly.js |
| Tables | AG Grid Community |
| Styling | Tailwind CSS |
| Backend API | FastAPI + Uvicorn |
| ML / Data | pandas, numpy, scikit-learn, lightgbm |
| Data store | CSV files (file-based, no database) |
| Routing | React Router v6 |
| HTTP client | Axios |

## MLOps Roadmap (Phase 2+)

1. **Embedding-based similarity** — replace one-hot with sentence-transformers on product descriptions
2. **Multimodal similarity** — image embeddings from product photos (CLIP)
3. **SHAP explainability** — true feature importance from LightGBM SHAP values
4. **Reinforcement learning** — optimise assortment decisions using historical launch outcomes
5. **Graph-based relationships** — Neo4j / networkX product relationship graph
6. **Feature store** — Feast or Tecton for real-time feature serving
7. **MLflow tracking** — experiment tracking, model versioning
8. **Temporal weighting** — exponential decay on historical demand for recency weighting
9. **Online elasticity** — Bayesian price elasticity updated as new transactions arrive
10. **Embedding drift monitoring** — Evidently AI for similarity score drift detection

## Security Considerations

- All data remains file-based and local — no external API calls
- FastAPI CORS restricted to localhost:5173 (dev); lock to specific origin in prod
- No PII in any output files
- Merchant access controlled at infrastructure level (VPN/SSO)
- No model serving endpoints exposed to public internet

## Performance Notes

- `sku_intelligence.py` runs all 8 engines sequentially — p90 < 2s on 10-store dataset
- Module-level `_cache` dicts prevent redundant CSV reads within a session
- For larger datasets (1000+ stores), add Redis caching layer on forecast outputs
- `whitespace_detector.py` itertools cross-product is O(D1×D2×D3×D4) — add sampling for >6 dimensions
