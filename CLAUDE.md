# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Hair Care Assortment Optimization MVP for retail category managers. The system generates data-driven SKU recommendations (Continue / Expand / Watch / Delist) using demand forecasting, basket analysis, new-product similarity scoring, and store clustering. All data is file-based (CSV/XLSX) — no external databases or APIs.

## Running the Application

```powershell
# Install dependencies (if not already in venv)
pip install streamlit pandas numpy plotly scikit-learn lightgbm openpyxl scipy

# Launch the Streamlit dashboard
streamlit run Frontend/app.py
```

## Running Backend Modules Independently

Each backend script writes its outputs to `Outputs/` and can be run standalone:

```powershell
python Backend/pipelines/forecasting/forecasting.py               # → Forecast_Output.csv, Forecast_Validation.csv, weekly_demand_output.csv
python Backend/pipelines/basket_abc_analysis/basket_analysis.py   # → association_rules.csv, sku_basket_insights.csv, demand_transfer_matrix.csv, delisting_recommendations.csv
python Backend/pipelines/basket_abc_analysis/similarity.py        # → new_sku_similarity_scores.csv, new_sku_analog_demand_forecast.csv
python Backend/pipelines/store_clustering/cluster.py               # → store_clusters.csv, store_clusters_summary.json
```

Run order matters: forecasting and clustering should complete before basket analysis if you need fresh weekly demand data.

## Architecture

### Data Pipeline (7 Steps — see `ProcessFlow.md` for full spec)

```
Raw_Input/ CSVs
  → ETL (quality gates: referential integrity, grain, nulls, calendar continuity)
  → Star Schema (Facts: Weekly_Sales, Weekly_Inventory; Dims: SKU, Store, Calendar)
  → 7 Backend Modules (run independently, produce Outputs/ CSVs)
  → Outputs/ CSVs (standardized contracts with explainability payloads)
  → Frontend/app.py (Streamlit serving layer)
```

### Backend Modules

| Module | File | Algorithm |
|--------|------|-----------|
| Demand Forecasting | `Backend/pipelines/forecasting/forecasting.py` | Dual-model per SKU×Store timeseries: LightGBM (n_estimators=500, lr=0.05) + Nixtla AutoETS. Holds out 6-week validation window; picks best by MAE. Nixtla is optional — skipped gracefully if not installed. |
| New SKU Similarity | `Backend/pipelines/basket_abc_analysis/similarity.py` | 4-group cosine/Jaccard similarity (Hierarchy 35%, Functional 25%, Ingredient 20%, Commercial 20%). Top-N analog matches drive cold-start demand forecasts per store cluster. |
| Basket & Delisting | `Backend/pipelines/basket_abc_analysis/basket_analysis.py` | Association rules (MIN_SUPPORT=0.5%), demand transfer matrix within sub-categories. 8-component composite delist score (ABC 15%, Revenue 20%, Margin 20%, Support 15%, Lift 10%, Dependency 10%, Substitution 10%). Generates NL explanations. |
| Store Clustering | `Backend/pipelines/store_clustering/cluster.py` | Ward linkage hierarchical clustering (≤500 stores); BIRCH + PCA for >500. Auto-detects cluster count (cap: 6). Current output: 3 clusters (Digital-First Urban, Affluent Suburban, Rural Remote). |

### Frontend (`Frontend/app.py`)

Single-file Streamlit app. Default landing page is a unified 3-column dashboard. Navigation via the dark left sidebar.

**Dashboard (default view) — matches Image1/Image2 design reference:**
- Filter bar: Store, Sub-Category, Brand, Scenario (+/−%)
- KPI strip: Stores · Active SKUs · 6-Week Forecast Qty · Delist Candidates · Top Basket Lift
- Left column: Manager Recommendations (4 insight cards — Product Optimization, Cross-Sell, New SKU, Risk Alerts)
- Center column: ABC Analysis Pareto → Market Basket Analytics (tabs) → Sales Trend & Forecast
- Right column: AI Category Assistant (static, no LLM — real data injected) + AI Recommendations metrics table + store ranking bar

**Sidebar pages:**
- 🟦 Store Forecast Treemap — interactive squarify treemap with auto drill-down
- 📋 SKU Performance — per-store forecast vs historical, brand share pie, demand tiers
- ✨ New SKU Similarity — manual form or file upload, analog store-level forecast
- 🧩 Assortment Recommendation — rule-based Continue/Expand/Watch/Delist per store
- 🚨 Delisting Risk Analysis — scatter + table from `delisting_recommendations.csv`
- 🩺 Data Quality — file status table, row/column counts, missing-column warnings

**Path resolution:** `APP_DIR = Frontend/`, `PROJECT_DIR = APP_DIR.parent` (Assortment root). `_find()` resolves all candidates relative to `PROJECT_DIR` first, then falls back to `APP_DIR`. File keys like `"Outputs/Forecast_Output.csv"` and `"Raw_Input/SKU_Master.csv"` work correctly when the app is launched from the project root.

### Key Data Files

| File | Grain | Dashboard use |
|------|-------|--------------|
| `Raw_Input/Sales_Tx.csv` | Transaction line (~200K rows) | ABC Pareto chart (ABC_Class + Net_Sales_USD) |
| `Raw_Input/SKU_Master.csv` | SKU (60 rows) | SKU name lookups, similarity scoring |
| `Raw_Input/Store_Master.csv` | Store (10 rows) | Store dimensions; drives clustering |
| `Outputs/weekly_demand_output.csv` | Week × Store × SKU | Sales Trend actual line; growth % calc |
| `Outputs/Forecast_Output.csv` | Week × Store × SKU (6-week) | Forecast line; KPI strip; treemap; store ranking |
| `Outputs/delisting_recommendations.csv` | SKU × granularity | Risk Alerts card; Delisting page; KPI count |
| `Outputs/association_rules.csv` | SKU pair | Cross-Sell card; Market Basket top pairs tab |
| `Outputs/sku_basket_insights.csv` | SKU | Market Basket insights tab |
| `Outputs/new_sku_similarity_scores.csv` | New SKU vs existing | New SKU card; similarity page |
| `Outputs/store_clusters.csv` | Store | Store labels in AI Recommendations bar chart |

## Placeholder / Unimplemented Areas

- `Backend/category_health/` — empty, reserved for future category health scoring
- `Backend/genai/` — empty, reserved for GenAI NL features
- Step 4.7 MILP optimization (OR-Tools) — described in `ProcessFlow.md` but not yet coded; must run last in pipeline

## Column Naming Conventions

- Time: `Year_WK` (weekly grain)
- Forecast: `Forecast_Week`, `Final_Forecast`, `Selected_Model`
- Demand: `Quantity_Sold`
- Recommendation: `delist_score` (0–1), `recommendation` (Continue/Watch/Expand/Delist), `nl_summary`
- Granularity: `granularity_level` (Channel, Store, Store_Cluster, etc.), `granularity_value`
