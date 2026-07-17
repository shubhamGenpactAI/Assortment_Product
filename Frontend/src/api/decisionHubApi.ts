import axios from 'axios'

const B = '/api/decision-hub'

type Filters = { store_id?: string; sub_cat?: string; cluster?: string }

const qs = (f: Filters) => ({
  params: { store_id: f.store_id || undefined, sub_cat: f.sub_cat || undefined, cluster: f.cluster || undefined },
})

export const fetchHubKpis             = (f: Filters = {}) => axios.get(`${B}/kpis`,                    qs(f)).then(r => r.data)
export const fetchRiskMatrix          = (f: Filters = {}) => axios.get(`${B}/risk-matrix`,             qs(f)).then(r => r.data)
export const fetchLostSales           = (f: Filters & { top_n?: number } = {}) =>
  axios.get(`${B}/lost-sales`, { params: { ...qs(f).params, top_n: f.top_n ?? 20 } }).then(r => r.data)
export const fetchInventoryProductivity = (f: Filters = {}) => axios.get(`${B}/inventory-productivity`, qs(f)).then(r => r.data)
export const fetchDelistRationalization = (f: Filters = {}) => axios.get(`${B}/delist-rationalization`, qs(f)).then(r => r.data)
export const fetchExceptionAlerts     = (f: Filters = {}) => axios.get(`${B}/exception-alerts`,        qs(f)).then(r => r.data)
export const fetchCategoryHealth      = ()                 => axios.get(`${B}/category-health`).then(r => r.data)
export const fetchForecastFan         = (skuId: string, storeId: string) =>
  axios.get(`${B}/forecast-fan/${skuId}/${storeId}`).then(r => r.data)
export const fetchSkuDrilldown        = (skuId: string, storeId: string) =>
  axios.get(`${B}/sku-drilldown/${skuId}/${storeId}`).then(r => r.data)
export const fetchCopilotContext      = (f: Filters = {}) => axios.get(`${B}/copilot/context`,         qs(f)).then(r => r.data)
export const fetchCompetitiveIntelligence = () => axios.get(`${B}/competitive-intelligence`).then(r => r.data)
export const fetchCompetitiveDrilldown = (productName: string, categoryKey: string) =>
  axios.get(`${B}/competitive-intelligence/drilldown`, { params: { product_name: productName, category_key: categoryKey } }).then(r => r.data)

export async function streamCopilot(
  filters: Filters,
  question: string,
  onToken: (tok: string) => void,
  onDone: () => void,
  onError: (e: string) => void,
) {
  try {
    const res = await fetch(`${B}/copilot/stream`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...filters, question }),
    })
    if (!res.ok || !res.body) { onError(`HTTP ${res.status}`); return }

    const reader  = res.body.getReader()
    const decoder = new TextDecoder()

    while (true) {
      const { done, value } = await reader.read()
      if (done) break
      const chunk = decoder.decode(value, { stream: true })
      for (const line of chunk.split('\n')) {
        if (!line.startsWith('data: ')) continue
        const payload = line.slice(6)
        if (payload === '[DONE]') { onDone(); return }
        if (payload.startsWith('[ERROR')) { onError(payload); return }
        onToken(payload.replace(/\\n/g, '\n'))
      }
    }
    onDone()
  } catch (e: any) {
    onError(String(e))
  }
}
