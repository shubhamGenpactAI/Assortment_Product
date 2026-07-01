# Category Decision Hub — Page Documentation

The **Category Decision Hub** (`/decision-hub`) is the primary command-and-control page for category managers. It consolidates all assortment signals — inventory health, demand forecasts, delist risk, and growth opportunities — into a single, filterable view with an AI copilot for natural-language querying.

---

## Filters (Top Bar)

| Filter | Values | Effect |
|--------|--------|--------|
| **Store** | All Stores / individual store ID | Scopes every chart and KPI to that store |
| **Sub-Category** | Shampoo, Conditioner, Hair Color, Hair Oil, Hair Serum, Hair Mask, Anti-Dandruff Treatment | Narrows data to one product sub-category |
| **Cluster** | Premium Urban, Emerging Growth, Affluent Suburban, Digital-First Urban, Rural Remote | Filters by the store cluster from `store_clusters.csv` |
| **Clear (✕)** | — | Resets all filters to show the full portfolio |

All six panels reload simultaneously whenever a filter changes.

---

## 1. Category Health Strip

A horizontal row of pill-badges — one per sub-category — sitting above the KPI header.

**What it shows:**
Each pill displays the sub-category name, a small progress bar, and a composite score (0–100).

**How the composite score is calculated** (`get_category_health_scores`):

| Component | Weight | Source |
|-----------|--------|--------|
| Health Score (avg across SKUs) | 25% | `Health_Score` from `delisting_recommendations.csv`, scaled to 0–100 |
| Growth Score (normalised forecast growth) | 25% | Calculated growth % vs historical, normalised between −30% and +30% |
| GMROI Score (normalised vs portfolio) | 20% | GMROI from `delisting_recommendations.csv`, normalised to 5th–95th percentile |
| Sell-Through Rate | 20% | `hist_qty / (hist_qty + current_inventory)` |
| Delist-Free % (SKUs with delist score < 0.4) | 10% | `delisting_recommendations.csv` |

**Colour coding:**
- **Green** (≥ 70) — healthy, no action needed
- **Amber** (45–69) — monitor, investigate lagging components
- **Red** (< 45) — at-risk category, requires intervention

---

## 2. KPI Header

Six summary cards that quantify the current assortment's financial state.

| KPI | Definition | Formula |
|-----|-----------|---------|
| **Forecast Revenue** | Total predicted revenue over the next 6 weeks | Sum of `Total_Sales` from `Forecast_Output.csv` across all filtered SKU × Store combinations |
| **Forecast Margin** | Total predicted gross margin over 6 weeks | Sum of `Total_Margin` from `Forecast_Output.csv` |
| **Revenue at Risk** | Revenue lost due to insufficient inventory (stockout gaps) | `Lost_Units × List_Price_USD` where `Lost_Units = max(0, forecast_6wk − current_inventory)` |
| **Excess Inventory Value** | Capital tied up in over-stocked SKUs | Inventory value (`current_inventory × List_Price_USD`) for all SKUs with Weeks of Cover > 12 |
| **Delist Candidates** | Count of distinct SKUs in the top 25% delist-risk tier | SKUs with `delist_score ≥ 75th percentile` of the filtered portfolio |
| **Growth Opportunities** | Count of high-growth SKUs with low delist risk | SKUs with forecast growth in top 25% AND `delist_score < portfolio median` |

> **Data source:** `Forecast_Output.csv`, `weekly_demand_output.csv`, `delisting_recommendations.csv`, `SKU_Master.csv`

---

## 3. AI Copilot Recommendations

A live-streaming chat panel powered by an LLM (OpenRouter API) that acts as a category analyst assistant.

**How it works:**
1. On load, `build_copilot_context()` assembles a structured JSON payload containing: summary KPIs, top 5 stockout-risk SKUs, top 5 lost-sales SKUs, top 3 growth opportunities, top 3 delist candidates, top 5 urgent (red) alerts, and top 5 category health scores.
2. This context is injected as the system prompt for the LLM (`llm_service.py`).
3. The user can type any question; the LLM answers using only the pre-built context — no raw data is sent.
4. Responses stream token-by-token via Server-Sent Events (SSE) to the frontend.

**What to ask:**
- "Which SKUs should I replenish this week?"
- "What's driving revenue at risk in Shampoo?"
- "Which stores have the most growth opportunities?"
- "Give me the top 3 SKUs to delist and why."

> **Copilot context respects the active filters** — switching store or sub-category updates the context the copilot sees.

---

## 4. Exception Alerts

A prioritised, colour-coded alert feed surfacing the most urgent assortment events. Shows up to 25 alerts, sorted by severity then financial impact.

### Alert Types

| Colour | Type | Trigger Condition | Financial Field |
|--------|------|-------------------|----------------|
| 🔴 Red | **Stockout Risk** | `WoC ≤ 20th percentile` of the filtered portfolio | Lost Revenue (USD) |
| 🟠 Orange | **Demand Surge** | Forecast growth > +30% vs historical weekly average | 6-week forecast sales |
| 🟠 Orange | **Demand Drop** | Forecast growth < −25% vs historical | 6-week forecast sales |
| 🔴 Red | **Delist Candidate** | `delist_score > 0.8` | 6-week forecast sales |
| 🟢 Green | **Growth Opportunity** | Forecast growth > +20% AND `delist_score < 0.3` | 6-week forecast sales |

Each alert card shows: SKU name, store ID, weeks of cover or growth %, and the dollar impact. Clicking an alert (where implemented) drills into the SKU Drilldown panel.

> **Data sources:** `Forecast_Output.csv`, `weekly_demand_output.csv`, `delisting_recommendations.csv`

---

## 5. Forecast Opportunity & Risk Matrix

A sortable table listing every non-Stable SKU × Store combination classified into one of five risk/opportunity buckets.

### Risk Buckets

| Bucket | Classification Logic | Recommended Action |
|--------|---------------------|-------------------|
| **Stock-out Risk** | `WoC ≤ 20th percentile` | Replenish Now |
| **Excess Inventory** | `WoC ≥ 80th percentile` | Reduce Orders |
| **Growth Opportunity** | Forecast growth in top 25% AND `delist_score < median` | Expand Assortment |
| **Delist Candidate** | `delist_score ≥ 75th percentile` | Review Delisting |
| **Transfer Candidate** | Same SKU has Stock-out Risk in one store AND Excess Inventory in another | Transfer Stock |

### Table Columns

| Column | Description |
|--------|-------------|
| SKU ID / Product Name | Identifier and display name |
| Store ID | Store where the condition is observed |
| Sub-Category / Brand | Product hierarchy |
| Risk Bucket | Classification from above |
| Action | Recommended action |
| Financial Impact (USD) | Lost Revenue for stockouts; inventory value for excess; 6-week forecast sales otherwise |
| WoC | Weeks of Cover = `current_inventory / avg_weekly_forecast` |
| Lost Revenue | Potential revenue lost due to insufficient stock |
| Growth % | `(avg_weekly_forecast − avg_weekly_historical) / avg_weekly_historical × 100` |
| Health Score | 0–100 composite health score for the SKU |
| Delist Score | 0–1 probability of needing delisting |

Rows are sorted by financial impact descending (top 200 shown).

> **Data sources:** `Forecast_Output.csv`, `weekly_demand_output.csv`, `delisting_recommendations.csv`

---

## 6. Lost Sales & Revenue at Risk

A horizontal bar chart of the top 20 SKUs ranked by total lost revenue across the filtered stores.

**How Lost Sales are computed:**

```
Lost_Units   = max(0, forecast_6wk − current_inventory)
Lost_Revenue = Lost_Units × List_Price_USD
Lost_Margin  = Lost_Units × (List_Price_USD − Unit_Cost_USD)
```

If `forecast_6wk ≤ current_inventory` the SKU has no lost sales and is excluded.

### Chart Columns

| Metric | Description |
|--------|-------------|
| Lost Revenue (USD) | Primary bar — total revenue gap across all affected stores |
| Lost Margin (USD) | Gross margin forfeited due to the stock gap |
| Lost Units | Volume not fulfilled |
| Affected Stores | Number of distinct stores with a stock gap for this SKU |

> Results are aggregated to SKU level (across all stores that match the active filter). Top 20 by Lost Revenue are displayed.

---

## 7. Inventory Productivity (GMROI vs Weeks of Cover)

A bubble scatter chart that maps every SKU's inventory efficiency in two dimensions simultaneously.

| Axis | Metric | Ideal Direction |
|------|--------|----------------|
| **X-axis** | Weeks of Cover (WoC) | Lower is leaner (< 4 weeks is typically optimal for fast-movers) |
| **Y-axis** | GMROI (Gross Margin Return on Inventory Investment) | Higher is better |
| **Bubble size** | 6-week forecast revenue | Larger = more important SKU |
| **Colour** (hover tooltip) | Health Score, Sell-Through, Delist Score, Growth % | — |

**GMROI formula:**
```
GMROI = Gross Margin / Average Inventory Cost
```
Sourced from `delisting_recommendations.csv`.

**Reading the quadrants:**

| Quadrant | Interpretation |
|----------|---------------|
| High GMROI + Low WoC | Star performers — efficient and profitable |
| High GMROI + High WoC | Over-stocked winners — reduce replenishment |
| Low GMROI + Low WoC | Marginal SKUs running lean — monitor |
| Low GMROI + High WoC | Dead inventory — strong delist candidates |

---

## 8. Delist & Rationalization Hub

A four-bucket Kanban-style view that gives every SKU a portfolio decision label based on combined delist risk and growth trajectory.

### Decision Buckets

| Bucket | Logic | Meaning |
|--------|-------|---------|
| **Keep** | `delist_score ≤ 25th percentile` | Healthy SKUs — no action needed |
| **Grow** | Forecast growth in top 25% AND `delist_score < median` | High-potential SKUs — expand ranging or promotional support |
| **Watch** | Neither Keep nor Grow nor Delist | Borderline SKUs — monitor next 4–6 weeks before deciding |
| **Delist** | `delist_score ≥ 75th percentile` | Underperformers — initiate ranging review or phase-out |

### Per-SKU Card Columns

| Field | Description |
|-------|-------------|
| SKU ID / Product Name | Identifier |
| Sub-Category / Brand | Hierarchy |
| Delist Score | 0–1 composite risk score (8 components — see below) |
| Health Score | 0–100 overall SKU health |
| Growth % | Forecast growth vs historical |
| GMROI | Margin return on inventory |
| Basket Role | Role in customer basket (Anchor, Complementary, Niche, etc.) |
| Revenue | 6-week forecast revenue |
| Recommended Action | NL action label from the backend |

**Delist Score components** (from `basket_analysis.py`):

| Component | Weight |
|-----------|--------|
| ABC class (revenue contribution) | 15% |
| Revenue rank | 20% |
| Margin rank | 20% |
| Market basket support | 15% |
| Basket lift | 10% |
| Basket dependency (other SKUs depend on this one) | 10% |
| Substitution availability | 10% |

> **Insight callout:** The panel also surfaces an auto-generated sentence e.g. *"14 SKUs contribute only 4.2% of forecast revenue but consume significant shelf space and working capital."*

---

## 9. Data Refresh & Caching

All service functions cache their underlying DataFrames in memory using Python `@lru_cache`. This means:
- The first request after a server start reads from disk (CSV files in `Outputs/`).
- Subsequent requests within the same server session are served from memory.
- To pick up new backend outputs (after re-running `forecasting.py`, `basket_analysis.py`, etc.), **restart the FastAPI server**.

---

## API Endpoints (Backend)

All routes are prefixed `/api/decision-hub`.

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/kpis` | 6 summary KPI values |
| GET | `/risk-matrix` | Non-Stable SKU × Store rows with risk bucket |
| GET | `/lost-sales` | Top N SKUs by lost revenue |
| GET | `/inventory-productivity` | SKU-level WoC + GMROI scatter data |
| GET | `/delist-rationalization` | Keep / Grow / Watch / Delist buckets |
| GET | `/exception-alerts` | Prioritised alert feed |
| GET | `/category-health` | Sub-category composite health scores |
| GET | `/forecast-fan/{sku_id}/{store_id}` | Actuals + 6-week forecast with confidence band |
| GET | `/sku-drilldown/{sku_id}/{store_id}` | Full SKU metrics + narrative for modal view |
| GET | `/copilot/context` | Structured JSON snapshot fed to the LLM |
| POST | `/copilot/stream` | SSE stream of LLM response for a given question |

Query parameters `store_id`, `sub_cat`, and `cluster` are accepted on all GET endpoints (except fan and drilldown, which use path parameters).
