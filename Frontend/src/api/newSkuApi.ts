import axios from 'axios'

const B = '/api/new-sku'

export const fetchNewSkuList = () =>
  axios.get(`${B}/list`).then(r => r.data)

export const fetchIntelligence = (newSkuId: string, attrs?: Record<string, unknown>) =>
  axios.post(`${B}/intelligence`, {
    new_sku_id:    newSkuId,
    new_sku_attrs: attrs ?? {},
    top_n_analogs: 5,
    top_n_stores:  10,
  }).then(r => r.data)

export const fetchHierarchicalForecast = (newSkuId: string, attrs?: Record<string, unknown>) =>
  axios.get(`${B}/forecast/${newSkuId}`, { params: attrs }).then(r => r.data)

export const fetchCannibalization = (newSkuId: string, forecastUnits: number, attrs?: Record<string, unknown>) =>
  axios.get(`${B}/cannibalization/${newSkuId}`, {
    params: { forecast_units_total: forecastUnits, ...attrs }
  }).then(r => r.data)

export const fetchStoreRecommendation = (newSkuId: string, attrs?: Record<string, unknown>) =>
  axios.get(`${B}/stores/${newSkuId}`, { params: attrs }).then(r => r.data)

export const fetchScenario = (payload: {
  new_sku_id:           string
  base_units:           number
  price_delta_pct:      number
  promo_intensity:      number
  pack_size_delta_pct:  number
  new_sku_attrs?:       Record<string, unknown>
}) => axios.post(`${B}/scenario`, payload).then(r => r.data)

export const fetchWhitespace = (subCategory?: string, topN = 15) =>
  axios.get(`${B}/whitespace`, { params: { sub_category: subCategory, top_n: topN } }).then(r => r.data)

export const uploadNewSkuCsv = (file: File) => {
  const form = new FormData()
  form.append('file', file)
  return axios.post(`${B}/upload`, form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  }).then(r => r.data)
}

export const clearUploadCache = () =>
  axios.delete(`${B}/upload/cache`).then(r => r.data)

export const downloadCsvTemplate = () => {
  const headers = [
    'SKU_ID', 'Product_Name', 'Brand', 'Category', 'Sub_Category', 'Segment',
    'Attribute_Claim', 'Price_Band', 'List_Price_USD', 'Unit_Cost_USD',
    'Pack_Size_ml', 'Margin_Pct', 'Organic_Flag', 'Sulphate_Free_Flag',
    'Paraben_Free_Flag', 'Hair_Fall_Flag', 'Dandruff_Flag',
    'Color_Protection_Flag', 'Ingredient_1', 'Ingredient_2',
    'Ingredient_3', 'Ingredient_4', 'Hair_Type', 'Age_Group',
  ]
  const example = [
    'NEW_SKU_001', 'Rosemary Anti-Frizz Conditioner 300ml', 'YourBrand',
    'Hair Care', 'Conditioner', 'Anti-Frizz', 'Rosemary Biotin',
    'Premium', '9.99', '4.50', '300', '54.9',
    '1', '1', '1', '0', '0', '0',
    'Rosemary', 'Biotin', 'Argan Oil', '',
    'All Hair Types', 'Adult',
  ]
  const csv = [headers.join(','), example.join(',')].join('\n')
  const blob = new Blob([csv], { type: 'text/csv' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url; a.download = 'new_sku_upload_template.csv'; a.click()
  URL.revokeObjectURL(url)
}

export const fetchUploadedSkus = () =>
  axios.get(`${B}/uploaded`).then(r => r.data)
