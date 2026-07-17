// ---------------------------------------------------------------------------
// TypeScript types for the Category Intelligence Workspace
// ---------------------------------------------------------------------------

export type DecisionType =
  | 'EXPAND' | 'FUTURE_STAR' | 'CONTINUE' | 'CASH_COW'
  | 'INVESTIGATE' | 'KEEP_WATCH' | 'PHASE_OUT' | 'REPLACE' | 'DELIST'

export type HealthBand  = 'HIGH_HEALTH'  | 'MID_HEALTH'  | 'LOW_HEALTH'
export type DelistBand  = 'HIGH_DELIST'  | 'MID_DELIST'  | 'LOW_DELIST'
export type GMROIBand   = 'HIGH_GMROI'   | 'MID_GMROI'   | 'LOW_GMROI'
export type ForecastBand = 'STRONG_GROWTH' | 'GROWTH' | 'FLAT' | 'DECLINE' | 'SHARP_DECLINE'
export type BasketRole  = 'Anchor' | 'Complement' | 'Substitutable' | 'Solo'

export interface SKURecommendation {
  SKU_ID:                 string
  Sub_Category:           string | null
  ABC_Class:              string | null
  granularity_level:      string
  granularity_value:      string
  total_revenue:          number | null
  total_margin:           number | null
  support_in_group:       number | null
  avg_lift:               number | null
  basket_dependency_score:number | null
  substitution_score:     number | null
  delist_score:           number | null
  SalesIndex:             number | null
  MarginIndex:            number | null
  VelocityIndex:          number | null
  InventoryEfficiency:    number | null
  GMROI:                  number | null
  SentimentIndex:         number | null
  MarketStrengthIndex:    number | null
  Forecasted_Sales:       number | null
  Forecast_Growth_Pct:    number | null
  Trend_Direction:        string | null
  Forecast_Confidence:    number | null
  Health_Score:           number | null
  Health_Band:            HealthBand | null
  Delist_Band:            DelistBand | null
  GMROI_Band:             GMROIBand | null
  Forecast_Band:          ForecastBand | null
  Basket_Role:            BasketRole | null
  Recapture_Potential:    number | null
  Cannibalization_Risk:   number | null
  Decision:               DecisionType | null
  Decision_Reason:        string | null
  Recommended_Action:     string | null
  Recommendation_Narrative: string | null
}

export interface WeeklyDemandPoint { w: string; q: number | null }
export interface ForecastPoint     { w: string; fc: number | null; lo: number | null; hi: number | null }

export interface TransferCandidate {
  from_sku:             string
  to_sku:               string
  sub_category:         string | null
  transfer_confidence:  number | null
  transfer_lift:        number | null
  from_sku_total_revenue: number | null
  to_sku_total_revenue:   number | null
  revenue_ratio_B_over_A: number | null
  from_sku_status:      string | null
  to_sku_status:        string | null
}

export interface BasketInsight {
  SKU_ID:                   string
  Sub_Category:             string | null
  n_baskets_present:        number | null
  support:                  number | null
  basket_revenue_impact:    number | null
  basket_margin_impact:     number | null
  basket_dependency_score:  number | null
  substitution_score:       number | null
  demand_transfer_candidates: number | null
  promo_halo_impact:        number | null
}

export interface SKUMasterInfo {
  SKU_ID:         string
  Product_Name:   string
  Brand:          string | null
  Category:       string | null
  Sub_Category:   string | null
  Price_Band:     string | null
  List_Price_USD: number | null
  Unit_Cost_USD:  number | null
  Margin_Pct:     number | null
  Pack_Size_ml:   number | null
  Status:         string | null
  Launch_Date:    string | null
}

export interface WorkspaceSummary {
  totalSKUs:          number
  decisions:          Record<string, number>
  healthBands:        Record<string, number>
  delistBands:        Record<string, number>
  forecastBands:      Record<string, number>
  basketRoles:        Record<string, number>
  avgHealth:          number | null
  avgGMROI:           number | null
  avgForecastGrowth:  number | null
  avgSentiment:       number | null
  avgMarketStrength:  number | null
  totalRevenue:       number | null
  totalMargin:        number | null
}

export interface AssortmentData {
  meta:            { version: string; rows: number }
  summary:         WorkspaceSummary
  recommendations: SKURecommendation[]
  weeklyDemand:    Record<string, WeeklyDemandPoint[]>
  forecastData:    Record<string, ForecastPoint[]>
  basketInsights:  Record<string, BasketInsight>
  transferMatrix:  Record<string, TransferCandidate[]>
  skuMaster:       Record<string, SKUMasterInfo>
  storeClusters:   Array<{ Store_ID: string; Cluster_ID: number; Cluster_Label: string }>
}

export interface WorkspaceFilters {
  granularity_level?: string
  Brand?:             string
  Category?:          string
  Sub_Category?:      string
  ABC_Class?:         string
  Decision?:          string
  Health_Band?:       string
  Delist_Band?:       string
  GMROI_Band?:        string
  Basket_Role?:       string
  Store_Name?:        string
  Cluster_Name?:      string
  Region_Name?:       string
  searchTerm?:        string
}
