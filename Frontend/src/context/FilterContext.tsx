import { createContext, useContext, useState, useCallback, type ReactNode } from 'react'

export interface GlobalFilters {
  // Shared across Category Intelligence, Decision Hub, Agent Hub
  sub_cat:           string   // CI: Sub_Category  | DH/Hub: sub_cat
  store_id:          string   // CI: Store_Name     | DH/Hub: store_id
  cluster:           string   // CI: Cluster_Name   | DH/Hub: cluster
  brand:             string   // CI: Brand          | Brief: brand

  // Category Intelligence specific
  granularity_level: string
  abc_class:         string
  decision:          string
  health_band:       string
  delist_band:       string
  gmroi_band:        string
  basket_role:       string
  category:          string
  region_name:       string
  search_term:       string

  // Watchdog agent
  top_n: number

  // Localization agent
  min_divergence: number

  // Stakeholder Brief agent
  brief_type: string
}

export const DEFAULT_FILTERS: GlobalFilters = {
  sub_cat:           '',
  store_id:          '',
  cluster:           '',
  brand:             '',
  granularity_level: 'Global',
  abc_class:         '',
  decision:          '',
  health_band:       '',
  delist_band:       '',
  gmroi_band:        '',
  basket_role:       '',
  category:          '',
  region_name:       '',
  search_term:       '',
  top_n:             10,
  min_divergence:    0.04,
  brief_type:        'vendor_negotiation',
}

interface FilterContextValue {
  filters:      GlobalFilters
  setFilter:    <K extends keyof GlobalFilters>(key: K, value: GlobalFilters[K]) => void
  patchFilters: (patch: Partial<GlobalFilters>) => void
  clearFilters: () => void
}

const FilterContext = createContext<FilterContextValue | null>(null)

export function FilterProvider({ children }: { children: ReactNode }) {
  const [filters, setFilters] = useState<GlobalFilters>(DEFAULT_FILTERS)

  const setFilter = useCallback(
    <K extends keyof GlobalFilters>(key: K, value: GlobalFilters[K]) => {
      setFilters(prev => ({ ...prev, [key]: value }))
    },
    [],
  )

  const patchFilters = useCallback((patch: Partial<GlobalFilters>) => {
    setFilters(prev => ({ ...prev, ...patch }))
  }, [])

  const clearFilters = useCallback(() => setFilters(DEFAULT_FILTERS), [])

  return (
    <FilterContext.Provider value={{ filters, setFilter, patchFilters, clearFilters }}>
      {children}
    </FilterContext.Provider>
  )
}

export function useFilters(): FilterContextValue {
  const ctx = useContext(FilterContext)
  if (!ctx) throw new Error('useFilters must be used within FilterProvider')
  return ctx
}
