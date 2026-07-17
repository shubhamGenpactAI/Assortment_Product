import type { AssortmentData } from '../types/assortment'

export async function loadAssortmentData(): Promise<AssortmentData> {
  const res = await fetch('/data/assortment_data.json', { cache: 'no-store' })
  if (!res.ok) throw new Error(`Failed to load workspace data: ${res.status}`)
  return (await res.json()) as AssortmentData
}

// ── Assortment Decision Save ───────────────────────────────────────────────

export interface AssortmentDecisionPayload {
  decision_label:      string
  decision_type?:      string | null
  comment?:            string
  sku_id:              string
  product_name?:       string | null
  brand?:              string | null
  category?:           string | null
  sub_category?:       string | null
  view_label?:         string | null
  scope?:              string | null
  granularity_value?:  string | null
  abc_class?:          string | null
  health_score?:       number | null
  delist_score?:       number | null
  gmroi?:              number | null
  forecast_growth_pct?: number | null
  health_band?:        string | null
  delist_band?:        string | null
  basket_role?:        string | null
  total_revenue?:      number | null
  total_margin?:       number | null
  price_band?:         string | null
  list_price_usd?:     number | null
  decision_reason?:    string | null
  recommended_action?: string | null
}

export interface AssortmentDecisionResult {
  status: string
}

export async function saveAssortmentDecision(payload: AssortmentDecisionPayload): Promise<AssortmentDecisionResult> {
  const res = await fetch('/api/assortment-decisions', {
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify(payload),
  })
  if (!res.ok) {
    const body = await res.json().catch(() => null)
    throw new Error(body?.detail ?? `Failed to save decision: ${res.status}`)
  }
  return res.json()
}

// ── Assortment Decision Log (live CSV read) ────────────────────────────────

export interface AssortmentDecisionRow {
  Timestamp?:         string
  Decision?:          string
  Decision_Type?:     string
  Comment?:           string
  SKU_ID?:            string
  Product_Name?:      string
  Brand?:             string
  Category?:          string
  Sub_Category?:      string
  View_Label?:        string
  Scope?:             string
  Granularity_Value?: string
  Scope_Detail?:      string
  ABC_Class?:         string
  Basket_Role?:       string
  [key: string]:      string | undefined
}

export async function fetchAssortmentDecisions(): Promise<AssortmentDecisionRow[]> {
  const res = await fetch('/api/assortment-decisions', { cache: 'no-store' })
  if (!res.ok) throw new Error(`Failed to load assortment decisions: ${res.status}`)
  return res.json()
}
