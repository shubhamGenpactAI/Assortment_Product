import axios from 'axios'

const B = '/api'

export const fetchDashboardKpis    = ()        => axios.get(`${B}/dashboard/kpis`).then(r => r.data)
export const fetchDashboardRecs    = ()        => axios.get(`${B}/dashboard/recommendations`).then(r => r.data)
export const fetchAbc              = (s?: string, sc?: string) =>
  axios.get(`${B}/dashboard/abc`, { params: { store_id: s, sub_cat: sc } }).then(r => r.data)
export const fetchBasketPairs      = ()        => axios.get(`${B}/dashboard/basket-pairs`).then(r => r.data)
export const fetchSalesTrend       = (s?: string, sc?: string) =>
  axios.get(`${B}/dashboard/sales-trend`, { params: { store_id: s, sub_cat: sc } }).then(r => r.data)
export const fetchStoreRanking     = ()        => axios.get(`${B}/dashboard/store-ranking`).then(r => r.data)
export const fetchStores           = ()        => axios.get(`${B}/stores`).then(r => r.data)
export const fetchSkuPerformance   = (s: string) => axios.get(`${B}/sku-performance`, { params: { store_id: s } }).then(r => r.data)
export const fetchBrandShare       = (s: string) => axios.get(`${B}/brand-share`,     { params: { store_id: s } }).then(r => r.data)
export const fetchDataQuality      = ()        => axios.get(`${B}/data-quality`).then(r => r.data)
export const fetchSimilarity       = ()        => axios.get(`${B}/similarity`).then(r => r.data)
export const fetchAnalogForecast   = (id: string) => axios.get(`${B}/analog-forecast`, { params: { new_sku_id: id } }).then(r => r.data)
