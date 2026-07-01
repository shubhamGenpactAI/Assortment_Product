# Strategy: AI-Powered Category Decision Hub

## What We Are Building

A new page — **Category Decision Hub** at route `/decision-hub` — that answers the 4 business questions from `prompt.md` in under 30 seconds. It implements all 17 features across 3 phases, with real LLM integration for the AI Copilot and driver explanations.

**Zero changes to existing pages.** All existing routes, components, and backend endpoints remain untouched.

---

## Tech Stack (Matches Existing Codebase)

| Layer        | Technology                                      |
|--------------|-------------------------------------------------|
| Frontend     | React + TypeScript + Vite + Tailwind CSS        |
| Charts       | Plotly (already installed)                      |
| Backend      | FastAPI (Python)                                |
| LLM          | Anthropic Claude API (or OpenAI — swap 1 line)  |
| Data         | Existing Outputs/ CSVs — no new data pipeline   |

---

## Data Available (No New Backend Processing Needed)

| File                              | Used For                                  |
|-----------------------------------|-------------------------------------------|
| `Outputs/Forecast_Output.csv`     | Forecasts, prediction intervals, margin   |
| `Outputs/weekly_demand_output.csv`| Actuals → trend, sell-through             |
| `Outputs/delisting_recommendations.csv` | Delist score, health score, nl_summary |
| `Outputs/association_rules.csv`   | Basket role, lift, cross-sell pairs       |
| `Outputs/sku_basket_insights.csv` | SKU-level basket dependency               |
| `Outputs/store_clusters.csv`      | Cluster labels per store                  |
| `Raw_Input/SKU_Master.csv`        | List_Price, Unit_Cost, Margin_Pct, Status |
| `Raw_Input/Store_Master.csv`      | Annual_Sales_Million, store attributes    |

---

## Page Layout (Matches prompt.md Recommended Layout)

```
┌─────────────────────────────────────────────────────────────────┐
│ HEADER: Forecast Period │ Category │ Store Cluster │ Search      │
├──────────┬──────────┬──────────┬──────────┬──────────┬──────────┤
│ ROW 1: 6 Executive KPI Cards                                     │
│ Fcst Revenue │ Fcst Margin │ Revenue@Risk │ Excess Inv │ Delist │ Growth │
├──────────────────────────────┬──────────────────────────────────┤
│ ROW 2: AI Copilot (LLM)      │ ROW 2: Exception Alerts          │
│ Streaming recommendations    │ 🔴🟠🟢 ranked by urgency         │
│ ranked by financial impact   │                                   │
├──────────────────────────────┴──────────────────────────────────┤
│ ROW 3: Forecast Opportunity & Risk Matrix (5-quadrant table)     │
│ Stock-out │ Excess │ Growth Opp │ Delist Candidate │ Transfer    │
├──────────────────────────────┬──────────────────────────────────┤
│ ROW 4L: Lost Sales Top-20    │ ROW 4R: Inventory Productivity   │
│ Bar chart: Revenue at Risk   │ Bubble scatter: WoC vs GMROI     │
├──────────────────────────────┴──────────────────────────────────┤
│ ROW 5: Delist & Rationalization Hub (Keep/Grow/Watch/Delist)    │
│ + Category Health Scores │ Forecast Fan Chart │ SKU Drilldown   │
└─────────────────────────────────────────────────────────────────┘
```

---

## New Files to Create

### Backend (4 new files)

```
Backend/
  routers/
    decision_hub.py          ← API route definitions
  services/
    decision_hub_service.py  ← All data computation logic
    llm_service.py           ← LLM API integration (streaming)
```

### Frontend (8 new files)

```
Frontend/src/
  pages/
    DecisionHubPage.tsx      ← Main page, layout, filter bar
  api/
    decisionHubApi.ts        ← All fetch calls to /api/decision-hub/*
  components/
    decision_hub/
      KpiHeader.tsx          ← Row 1: 6 KPI summary cards
      AICopilot.tsx          ← Row 2L: LLM streaming chat panel
      ExceptionAlerts.tsx    ← Row 2R: Colour-coded alert list
      RiskMatrix.tsx         ← Row 3: 5-bucket opportunity matrix table
      LostSalesChart.tsx     ← Row 4L: Top-20 revenue-at-risk bar chart
      InventoryScatter.tsx   ← Row 4R: GMROI vs WoC bubble scatter
      DelistHub.tsx          ← Row 5: Keep/Grow/Watch/Delist grid
```

### Modifications to Existing Files (3 files, minimal edits)

```
Backend/main.py              ← 2 new lines: import + include_router
Frontend/src/App.tsx         ← 2 new lines: lazy import + Route
Frontend/src/components/NavBar.tsx ← 1 new entry in the NAV array
```

---

## Implementation Plan — Phase by Phase

---

### Phase 0 — Environment Setup (10 minutes)

**Step 0.1 — Install Python dependency**
```
pip install anthropic          # or: pip install openai
```
Add to `requirements.txt`.

**Step 0.2 — Set API key**
```
# .env file in project root (never commit this)
LLM_API_KEY=sk-ant-...         # Anthropic key
LLM_PROVIDER=anthropic         # or "openai"
LLM_MODEL=claude-sonnet-4-6    # or gpt-4o
```
FastAPI will read via `os.getenv("LLM_API_KEY")`.

---

### Phase 1 — Backend Data Layer (No LLM) (~2 hours)

All computation is pure pandas over existing CSVs. No new data files needed.

#### Step 1.1 — `Backend/services/decision_hub_service.py`

Implement these functions (each reads the relevant CSV, computes, returns dict/list):

**`get_decision_hub_kpis(filters)`**
- Reads: `Forecast_Output.csv`, `delisting_recommendations.csv`, `weekly_demand_output.csv`
- Computes:
  - `forecast_revenue_usd` = sum(Final_Forecast × List_Price_USD) from SKU_Master join
  - `forecast_margin_usd` = sum(Final_Forecast × (List_Price − Unit_Cost))
  - `revenue_at_risk_usd` = sum(max(0, Final_Forecast − Qty_Available) × List_Price) — stock-out SKUs
  - `excess_inventory_value` = sum of inventory value where weeks_of_cover > 12
  - `delist_count` = count(delist_score > 0.7)
  - `growth_opportunities` = count(forecast_growth_pct > 15% AND gmroi > category_avg_gmroi)
- Returns: dict of 6 KPI values

**`get_risk_matrix(filters)`**
- Reads: `Forecast_Output.csv`, `delisting_recommendations.csv`, `sku_basket_insights.csv`
- Logic:
  ```
  weeks_of_cover = Quantity_Available / (Final_Forecast / 6)

  Stock-out Risk:   weeks_of_cover < 2
  Excess Inventory: weeks_of_cover > 12
  Growth Opp:       forecast_growth_pct > 15 AND health_score > 60
  Delist Candidate: delist_score > 0.7 AND forecast_growth_pct < -10
  Transfer:         high demand in Store A + excess in Store B (same SKU, cross-store)
  ```
- Returns: list of SKU rows with `bucket`, `action`, `sku_id`, `store_id`, `financial_impact_usd`

**`get_lost_sales(filters, top_n=20)`**
- Formula from prompt.md: `Lost_Units = max(0, Final_Forecast − Quantity_Available)`
- `Lost_Revenue = Lost_Units × List_Price_USD`
- `Lost_Margin = Lost_Units × (List_Price − Unit_Cost)`
- Returns: top N SKUs sorted by Lost_Revenue desc

**`get_inventory_productivity(filters)`**
- Joins Forecast_Output + SKU_Master
- Computes per SKU×Store:
  - `weeks_of_cover = Quantity_Available / (Final_Forecast / 6)`
  - `gmroi = (Forecast_Revenue − Forecast_Cost) / (Inventory_Value + 1)`
  - `sell_through = Quantity_Sold / (Quantity_Sold + Quantity_Available)`
  - `health_score` (from delisting_recommendations)
  - `revenue` = Final_Forecast × List_Price
- Returns: list for bubble scatter (x=WoC, y=GMROI, size=revenue, color=health_score)

**`get_delist_rationalization(filters)`**
- Reads: `delisting_recommendations.csv`, `association_rules.csv`
- Classification rules:
  ```
  Keep:   health_score > 65 AND delist_score < 0.4
  Grow:   forecast_growth_pct > 10 AND Margin_Pct > category_avg
  Watch:  delist_score 0.4–0.7 OR forecast_growth_pct < -10
  Delist: delist_score > 0.7 AND health_score < 40
  ```
- Adds `basket_role` from association_rules (if SKU is in top pairs → "Traffic Driver")
- Returns: dict with lists per bucket + insight string (e.g. "17 SKUs = 0.8% sales, 12% space")

**`get_exception_alerts(filters)`**
- Produces coloured alerts by scanning all computed metrics:
  - 🔴 Stockout within 2 weeks: weeks_of_cover < 2
  - 🟠 Forecast surge > 30%: forecast_growth_pct > 30
  - 🟠 Demand crash > 25%: forecast_growth_pct < -25
  - 🔴 GMROI below threshold (< 1.5)
  - 🔴 Delist candidate: delist_score > 0.8
  - 🟢 Growth opportunity: forecast_growth_pct > 20 AND low delist risk
- Returns: list of alerts sorted by severity and financial impact

**`get_category_health_scores()`**
- Groups by Sub_Category
- Composite score (0–100):
  - Forecast Growth (25%)
  - Avg Health Score (25%)
  - Avg GMROI normalised (20%)
  - Inventory Efficiency (sell-through) (20%)
  - Delist-free ratio (10%)
- Returns: list of {sub_category, score, components}

**`get_forecast_fan(sku_id, store_id)`**
- Reads: `Forecast_Output.csv`
- Returns: 6-week arrays for `Final_Forecast`, `Lower_Bound`, `Upper_Bound`
- Frontend renders as Plotly fan chart (filled area between bounds, line for point forecast)

**`get_sku_drilldown(sku_id, store_id)`**
- Joins all sources to build a single rich dict:
  - Forecast (6-week), actuals (22-week), fan bounds
  - GMROI, WoC, Sell-through, Margin_Pct
  - Health Score, Delist Score, nl_summary
  - Basket role (from association_rules)
  - SHAP-style driver breakdown (see Phase 2)
  - Recommended action

#### Step 1.2 — `Backend/routers/decision_hub.py`

```python
router = APIRouter()

@router.get("/kpis")
def hub_kpis(store_id=None, sub_cat=None, cluster=None):
    return get_decision_hub_kpis({...})

@router.get("/risk-matrix")
def hub_risk_matrix(store_id=None, sub_cat=None):
    return get_risk_matrix({...})

@router.get("/lost-sales")
def hub_lost_sales(store_id=None, top_n=20):
    return get_lost_sales({...}, top_n)

@router.get("/inventory-productivity")
def hub_inventory(store_id=None, sub_cat=None):
    return get_inventory_productivity({...})

@router.get("/delist-rationalization")
def hub_delist(store_id=None):
    return get_delist_rationalization({...})

@router.get("/exception-alerts")
def hub_alerts(store_id=None):
    return get_exception_alerts({...})

@router.get("/category-health")
def hub_health():
    return get_category_health_scores()

@router.get("/forecast-fan/{sku_id}/{store_id}")
def hub_fan(sku_id, store_id):
    return get_forecast_fan(sku_id, store_id)

@router.get("/sku-drilldown/{sku_id}/{store_id}")
def hub_drilldown(sku_id, store_id):
    return get_sku_drilldown(sku_id, store_id)

@router.post("/copilot/stream")          # Phase 2
async def hub_copilot_stream(request):
    return StreamingResponse(stream_llm_recommendations(request), ...)
```

#### Step 1.3 — Wire into `Backend/main.py`

```python
from .routers.decision_hub import router as decision_hub_router
app.include_router(decision_hub_router, prefix="/api/decision-hub", tags=["Decision Hub"])
```

---

### Phase 2 — LLM Integration (~1.5 hours)

#### Step 2.1 — `Backend/services/llm_service.py`

**Data context builder**
Pulls ~20 key facts from existing service functions and formats them into a concise JSON context:
```python
def build_llm_context(filters) -> dict:
    return {
        "kpis": get_decision_hub_kpis(filters),
        "top_stockout_risk": get_risk_matrix(filters) filtered to Stock-out, top 5,
        "top_lost_sales": get_lost_sales(filters, top_n=5),
        "top_delist": get_delist_rationalization(filters)["delist"][:5],
        "growth_opps": get_risk_matrix(filters) filtered to Growth, top 5,
    }
```

**Streaming recommendation generator**
```python
async def stream_llm_recommendations(context: dict, question: str = None):
    """
    Calls LLM with structured data context.
    Yields token-by-token SSE stream consumed by the frontend.
    """
    system_prompt = """
    You are an AI Copilot for a retail Category Manager.
    You will be given real sales forecast and inventory data.
    Generate 4-6 specific, actionable recommendations ranked by revenue impact.
    Format each as:
      [RANK]. [ACTION VERB] [SKU/Category]
         Impact: $X revenue protected / saved / at risk
         Reason: [1-sentence data-backed reason]
    Be direct and quantitative. Never be vague.
    """
    user_prompt = f"""
    Data as of this week:
    {json.dumps(context, indent=2)}

    {"User question: " + question if question else "Generate prioritised action recommendations."}
    """
    # Anthropic streaming
    async with anthropic.AsyncAnthropic(api_key=LLM_API_KEY).messages.stream(
        model=LLM_MODEL,
        max_tokens=1024,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    ) as stream:
        async for text in stream.text_stream:
            yield f"data: {text}\n\n"
```

**SHAP-style driver breakdown** (no actual SHAP — uses LLM to explain the LightGBM forecast in plain English based on the feature context):
```python
def get_forecast_drivers(sku_id, store_id) -> dict:
    """
    Builds a structured driver explanation:
    - Positive: {lag_1: 'strong recent sales momentum (+18%)', ...}
    - Negative: {rolling_std_4: 'high demand volatility', ...}
    Uses LLM to translate feature values into plain-English driver labels.
    """
```

#### Step 2.2 — Frontend: `AICopilot.tsx`

```tsx
// Uses EventSource (SSE) to stream LLM tokens into a growing text box
// Layout: left side = data context chips, right side = scrolling recommendation text
// Bottom: text input for "Ask a question" → sends to /api/decision-hub/copilot/stream
```

---

### Phase 3 — Frontend Page Assembly (~2 hours)

#### Step 3.1 — `Frontend/src/api/decisionHubApi.ts`

One fetch function per backend endpoint. Follows the exact same pattern as `generalApi.ts`:
```typescript
export const fetchHubKpis = (filters) => fetch(`/api/decision-hub/kpis?${qs(filters)}`).then(r => r.json())
export const fetchRiskMatrix = (filters) => fetch(`/api/decision-hub/risk-matrix?${qs(filters)}`).then(r => r.json())
// ... one per endpoint
```

#### Step 3.2 — Individual Components

**`KpiHeader.tsx`**
- 6-card strip (matches existing KpiCard pattern from DashboardPage)
- Cards: Forecast Revenue · Forecast Margin · Revenue at Risk · Excess Inv Value · Delist Count · Growth Opps
- Color-code: green = good, amber = watch, red = urgent

**`RiskMatrix.tsx`**
- Filterable table with 5 colour-coded bucket tabs across the top
- Columns: SKU | Store | Bucket | Action | Financial Impact | Weeks Cover
- Click row → opens `SkuDrilldownDrawer` (reuse pattern from WorkspacePage's `SKUDrawer`)

**`AICopilot.tsx`**
- Left panel: key data context shown as coloured chips (Revenue@Risk, Top Stockout, etc.)
- Right panel: scrolling LLM-generated text (SSE stream, typing animation)
- Bottom: text input for freeform questions
- Regenerate button: re-calls stream with same context

**`ExceptionAlerts.tsx`**
- Vertical list, grouped by severity (🔴 → 🟠 → 🟢)
- Each row: icon · SKU name · alert text · financial impact badge
- Max 20 alerts shown; collapse/expand

**`LostSalesChart.tsx`**
- Horizontal bar chart (Plotly) — top 20 SKUs by Lost Revenue
- Bars colored by bucket (stockout=red, near-stockout=amber)
- Tooltip: Lost Units · Lost Revenue · Lost Margin · Affected Stores

**`InventoryScatter.tsx`**
- Plotly bubble scatter: X = Weeks of Cover, Y = GMROI
- Bubble size = Revenue, Color = Health Score (green→red gradient)
- Quadrant overlays via shapes: "Overstocked Winners" / "Understocked Winners" / etc.
- Click bubble → opens SKU drilldown

**`DelistHub.tsx`**
- 4-column Kanban-style layout: Keep | Grow | Watch | Delist
- Each SKU card shows: SKU name, delist score bar, forecast trend sparkline, basket role tag
- Insight strip at bottom: "17 SKUs = 0.8% of sales, 12% of shelf space"

**`DecisionHubPage.tsx`**
- Filter bar: Store Cluster dropdown · Sub-Category dropdown · Period selector · Search input
- All components receive the same `filters` state object
- Loading skeleton while fetching (Loader2 spinner pattern)
- Layout uses Tailwind grid (same 2-col / full-width pattern as DashboardPage)

#### Step 3.3 — Wire into `Frontend/src/App.tsx`

```tsx
const DecisionHubPage = lazy(() => import('./pages/DecisionHubPage'))

// Inside the nested Routes:
<Route path="/decision-hub" element={<DecisionHubPage />} />
```

#### Step 3.4 — Add Nav Link in `Frontend/src/components/NavBar.tsx`

```tsx
{ to: '/decision-hub', label: '⚡ Decision Hub' }
```
Insert as second item in the `NAV` array (after `Category Intelligence`, before `Dashboard`).

---

## Feature→Implementation Mapping

| # | Feature (from prompt.md)         | Phase | Backend Function                  | Frontend Component       |
|---|----------------------------------|-------|-----------------------------------|--------------------------|
| 1 | Forecast Opportunity & Risk Matrix | 1  | `get_risk_matrix()`               | `RiskMatrix.tsx`         |
| 2 | AI Copilot Recommendation Center | 2     | `stream_llm_recommendations()`    | `AICopilot.tsx`          |
| 3 | Lost Sales & Revenue at Risk     | 1     | `get_lost_sales()`                | `LostSalesChart.tsx`     |
| 4 | Inventory Productivity Dashboard | 1     | `get_inventory_productivity()`    | `InventoryScatter.tsx`   |
| 5 | Delist & Rationalization Hub     | 1     | `get_delist_rationalization()`    | `DelistHub.tsx`          |
| 6 | Forecast Confidence Layer        | 1     | `get_forecast_fan()`              | Fan chart in Drilldown   |
| 7 | Forecast vs Capacity View        | Post  | Extend `get_inventory_productivity` | Tab in `InventoryScatter`|
| 8 | Demand Surge Detection           | 1     | Part of `get_exception_alerts()`  | `ExceptionAlerts.tsx`    |
| 9 | What-If Scenario Planning        | Post  | `simulate_scenario()`             | Slider panel in Drilldown|
| 10| Open-To-Buy Recommendation      | 1     | Part of `get_risk_matrix()`       | Column in `RiskMatrix`   |
| 11| Basket-Aware Insights            | 2     | `get_sku_drilldown()` + LLM       | Drilldown panel          |
| 12| Cannibalization Detection        | Post  | `detect_cannibalization()`        | Tab in `DelistHub`       |
| 13| Assortment Gap Detection         | 2     | LLM + cluster comparison          | Insight in `AICopilot`   |
| 14| Similar SKU Benchmarking         | 1     | Part of `get_sku_drilldown()`     | Benchmark card in Drawer |
| 15| Forecast Driver Breakdown (SHAP) | 2     | `get_forecast_drivers()` + LLM    | Waterfall in Drilldown   |
| 16| Exception-Based Management       | 1     | `get_exception_alerts()`          | `ExceptionAlerts.tsx`    |
| 17| Executive Category Health Score  | 1     | `get_category_health_scores()`    | Strip below KPI Header   |

---

## Execution Order

```
Day 1 (AM):  Phase 0 — env setup + Phase 1 backend service (Steps 1.1–1.3)
Day 1 (PM):  Phase 2 — llm_service.py + AICopilot.tsx streaming
Day 2 (AM):  Phase 3 — frontend components (KpiHeader, RiskMatrix, LostSales, InventoryScatter)
Day 2 (PM):  Phase 3 — DelistHub, ExceptionAlerts, DecisionHubPage assembly, Nav wiring
Day 3:       QA — filter interactions, LLM prompt tuning, mobile layout, edge cases (empty data)
Post-MVP:    Scenario planning (Feature 9), Cannibalization (Feature 12), Capacity view (Feature 7)
```

---

## Guardrails (Preserving Existing Pages)

- Every new file is a **new file** — no edits inside existing page or service files
- The 3 edits to existing files (`main.py`, `App.tsx`, `NavBar.tsx`) are purely additive (new lines only)
- New API routes are namespaced under `/api/decision-hub/*` — zero collision with existing `/api/forecast/*`, `/api/*`, `/api/new-sku/*`
- The new page has its own `api/decisionHubApi.ts` — no changes to `generalApi.ts` or `newSkuApi.ts`
- LLM key is read via `os.getenv()` — if missing, the copilot endpoint returns a 503 with a helpful message; all non-LLM features still work

---

## LLM Provider Swap (1-Line Change)

The `llm_service.py` will abstract provider behind a single `LLM_PROVIDER` env var:
```
LLM_PROVIDER=anthropic  →  uses anthropic.AsyncAnthropic
LLM_PROVIDER=openai     →  uses openai.AsyncOpenAI
```
Model ID and API key are also env vars — no code change needed to switch providers.
