import axios from 'axios'

const B = '/api/agents'

// ── Types ──────────────────────────────────────────────────────────────────

export type WatchdogFilters = {
  store_id?: string
  sub_cat?:  string
  cluster?:  string
  top_n?:    number
}

export type RootCause = {
  root_cause:        'Forecast Accuracy' | 'Safety Stock' | 'Heavy Sales' | 'Supplier Fill Rate'
  root_cause_detail: string
  scores:            Record<string, number>
}

export type WatchItem = {
  priority_rank:         number
  priority_score:        number
  sku_id:                string
  store_id:              string
  product_name:          string
  signal_types:          string[]
  conflict:              boolean
  severity:              'red' | 'orange' | 'green'
  financial_impact_usd:  number
  suggested_action:      string
  narrative:             string
  source_signals:        Record<string, any>
  root_cause?:           RootCause | null
}

export type WatchdogDigest = {
  generated_at:    string
  filters_applied: Record<string, any>
  summary: {
    total_items:              number
    red:                      number
    orange:                   number
    green:                    number
    total_financial_impact_usd: number
  }
  items: WatchItem[]
}

export type ClusterBreakdown = {
  cluster_id:           string
  cluster_label:        string
  cluster_delist_score: number
  cluster_decision:     string
  store_count:          number
  cluster_revenue:      number
}

export type DivergentSKU = {
  sku_id:               string
  product_name:         string
  brand:                string
  sub_category:         string
  global_decision:      string
  global_delist_score:  number
  cluster_breakdown:    ClusterBreakdown[]
  divergence_flag:      boolean
  divergence_magnitude: number
  recommended_override: string
}

export type OverrideRequest = {
  sku_id:      string
  cluster_id:  string
  decision:    'approved' | 'rejected'
  note?:       string
  decided_by?: string
}

export type BriefSection = { heading: string; body: string }

export type VendorNegotiationRow = {
  supplier:               string
  sku_id:                 string
  ean_id:                 string
  sku_name:               string
  lead_time_target_days:  number | null
  fill_rate_pct:          number | null
  supplier_rating:        string
  sell_through_pct:       number | null
  margin_pct:             number | null
  sales_usd:              number
  confidence_score:       number | null
}

export type Brief = {
  brief_id:     string
  brief_type:   string
  scope:        { brand?: string; sub_cat?: string; sku_ids?: string[] }
  sections:     BriefSection[]
  vendor_table: VendorNegotiationRow[] | null
  generated_at: string
  generated_by: string
  polish_failed: boolean
  export:       { markdown: string; text: string }
}

export type BriefRequest = {
  brief_type:    string
  brand?:        string
  sub_cat?:      string
  sku_ids?:      string[]
  generated_by?: string
}

// ── Watchdog ───────────────────────────────────────────────────────────────

export const fetchWatchdogDigest = (f: WatchdogFilters = {}): Promise<WatchdogDigest> =>
  axios.get(`${B}/watchdog/digest`, {
    params: {
      store_id: f.store_id || undefined,
      sub_cat:  f.sub_cat  || undefined,
      cluster:  f.cluster  || undefined,
      top_n:    f.top_n    ?? 10,
    },
  }).then(r => r.data)

export async function streamWatchdogNarrative(
  filters:  WatchdogFilters,
  onToken:  (tok: string) => void,
  onDone:   () => void,
  onError:  (e: string)   => void,
) {
  try {
    const res = await fetch(`${B}/watchdog/narrative`, {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify(filters),
    })
    if (!res.ok || !res.body) { onError(`HTTP ${res.status}`); return }
    const reader  = res.body.getReader()
    const decoder = new TextDecoder()
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      for (const line of decoder.decode(value, { stream: true }).split('\n')) {
        if (!line.startsWith('data: ')) continue
        const payload = line.slice(6)
        if (payload === '[DONE]')        { onDone();          return }
        if (payload.startsWith('[ERROR')) { onError(payload); return }
        onToken(payload.replace(/\\n/g, '\n'))
      }
    }
    onDone()
  } catch (e: any) {
    onError(String(e))
  }
}

// ── Localization ───────────────────────────────────────────────────────────

export const fetchDivergence = (sub_cat?: string, min_divergence = 0.2): Promise<DivergentSKU[]> =>
  axios.get(`${B}/localization/divergence`, {
    params: { sub_cat: sub_cat || undefined, min_divergence },
  }).then(r => r.data)

export const postOverride = (req: OverrideRequest) =>
  axios.post(`${B}/localization/override`, req).then(r => r.data)

export const fetchOverrides = (sku_id?: string, cluster_id?: string) =>
  axios.get(`${B}/localization/overrides`, {
    params: { sku_id: sku_id || undefined, cluster_id: cluster_id || undefined },
  }).then(r => r.data)

// ── Brief ──────────────────────────────────────────────────────────────────

export const generateBrief = (req: BriefRequest): Promise<Brief> =>
  axios.post(`${B}/brief/generate`, req).then(r => r.data)

export const fetchBrief = (brief_id: string): Promise<Brief> =>
  axios.get(`${B}/brief/${brief_id}`).then(r => r.data)

export const fetchBriefs = (brand?: string, sub_cat?: string) =>
  axios.get(`${B}/brief`, {
    params: { brand: brand || undefined, sub_cat: sub_cat || undefined },
  }).then(r => r.data)

export async function streamBriefPolish(
  brief_id: string,
  onToken:  (tok: string) => void,
  onDone:   () => void,
  onError:  (e: string)   => void,
) {
  try {
    const res = await fetch(`${B}/brief/${brief_id}/polish`, { method: 'POST' })
    if (!res.ok || !res.body) { onError(`HTTP ${res.status}`); return }
    const reader  = res.body.getReader()
    const decoder = new TextDecoder()
    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      for (const line of decoder.decode(value, { stream: true }).split('\n')) {
        if (!line.startsWith('data: ')) continue
        const payload = line.slice(6)
        if (payload === '[DONE]')        { onDone();          return }
        if (payload.startsWith('[ERROR')) { onError(payload); return }
        onToken(payload.replace(/\\n/g, '\n'))
      }
    }
    onDone()
  } catch (e: any) {
    onError(String(e))
  }
}
