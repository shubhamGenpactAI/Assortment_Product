import axios from 'axios'

const B = '/api'

export const fetchStores         = ()          => axios.get(`${B}/stores`).then(r => r.data)
export const fetchSimilarity     = ()          => axios.get(`${B}/similarity`).then(r => r.data)
export const fetchAnalogForecast = (id: string) =>
  axios.get(`${B}/analog-forecast`, { params: { new_sku_id: id } }).then(r => r.data)
