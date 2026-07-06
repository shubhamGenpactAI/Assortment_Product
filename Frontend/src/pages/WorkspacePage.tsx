import { useState, useEffect, useMemo, useCallback } from 'react'
import { Loader2 } from 'lucide-react'
import { loadAssortmentData } from '../api/assortmentData'
import type { AssortmentData, SKURecommendation, WorkspaceFilters } from '../types/assortment'
import { ExecutiveSummary } from '../components/workspace/ExecutiveSummary'
import { SmartFilterBar }  from '../components/workspace/SmartFilterBar'
import { InsightFeed }     from '../components/workspace/InsightFeed'
import { SKUTable }        from '../components/workspace/SKUTable'
import { SKUDrawer }       from '../components/workspace/SKUDrawer'
import { useFilters }      from '../context/FilterContext'

function matchesFilters(
  row:             SKURecommendation,
  f:               WorkspaceFilters,
  skuNames:        Record<string, string>,
  brandMap:        Record<string, string>,
  categoryMap:     Record<string, string>,
  storeClusterMap: Record<string, string>,
): boolean {
  if (f.granularity_level && row.granularity_level !== f.granularity_level) return false
  if (f.Sub_Category      && row.Sub_Category      !== f.Sub_Category)      return false
  if (f.ABC_Class         && row.ABC_Class          !== f.ABC_Class)         return false
  if (f.Decision          && row.Decision           !== f.Decision)          return false
  if (f.Health_Band       && row.Health_Band        !== f.Health_Band)       return false
  if (f.Delist_Band       && row.Delist_Band        !== f.Delist_Band)       return false
  if (f.GMROI_Band        && row.GMROI_Band         !== f.GMROI_Band)        return false
  if (f.Basket_Role       && row.Basket_Role        !== f.Basket_Role)       return false
  if (f.Brand    && brandMap[row.SKU_ID]    !== f.Brand)    return false
  if (f.Category && categoryMap[row.SKU_ID] !== f.Category) return false
  if (f.Store_Name) {
    if (row.granularity_level !== 'Store' || row.granularity_value !== f.Store_Name) return false
  }
  if (f.Cluster_Name) {
    if (row.granularity_level !== 'Store') return false
    if (storeClusterMap[row.granularity_value] !== f.Cluster_Name) return false
  }
  if (f.Region_Name) {
    if (row.granularity_level !== 'Geography' || row.granularity_value !== f.Region_Name) return false
  }
  if (f.searchTerm) {
    const q    = f.searchTerm.toLowerCase()
    const name = (skuNames[row.SKU_ID] ?? '').toLowerCase()
    if (!row.SKU_ID.toLowerCase().includes(q) && !name.includes(q)) return false
  }
  return true
}

export default function WorkspacePage() {
  const [data,     setData]     = useState<AssortmentData | null>(null)
  const [error,    setError]    = useState<string | null>(null)
  const [loading,  setLoading]  = useState(true)
  const [selected, setSelected] = useState<SKURecommendation | null>(null)

  const { filters: gf, patchFilters } = useFilters()

  // Translate global filter state → WorkspaceFilters shape expected by SmartFilterBar / matchesFilters
  const filters = useMemo<WorkspaceFilters>(() => ({
    granularity_level: gf.granularity_level || 'Global',
    Brand:             gf.brand       || undefined,
    Category:          gf.category    || undefined,
    Sub_Category:      gf.sub_cat     || undefined,
    ABC_Class:         gf.abc_class   || undefined,
    Decision:          gf.decision    || undefined,
    Health_Band:       gf.health_band || undefined,
    Delist_Band:       gf.delist_band || undefined,
    GMROI_Band:        gf.gmroi_band  || undefined,
    Basket_Role:       gf.basket_role || undefined,
    Store_Name:        gf.store_id    || undefined,
    Cluster_Name:      gf.cluster     || undefined,
    Region_Name:       gf.region_name || undefined,
    searchTerm:        gf.search_term || undefined,
  }), [
    gf.granularity_level, gf.brand, gf.category, gf.sub_cat,
    gf.abc_class, gf.decision, gf.health_band, gf.delist_band,
    gf.gmroi_band, gf.basket_role, gf.store_id, gf.cluster,
    gf.region_name, gf.search_term,
  ])

  // Translate WorkspaceFilters → global filter state on every SmartFilterBar change
  const handleFilterChange = useCallback((wf: WorkspaceFilters) => {
    patchFilters({
      granularity_level: wf.granularity_level ?? 'Global',
      brand:             wf.Brand             ?? '',
      category:          wf.Category          ?? '',
      sub_cat:           wf.Sub_Category      ?? '',
      abc_class:         wf.ABC_Class         ?? '',
      decision:          wf.Decision          ?? '',
      health_band:       wf.Health_Band       ?? '',
      delist_band:       wf.Delist_Band       ?? '',
      gmroi_band:        wf.GMROI_Band        ?? '',
      basket_role:       wf.Basket_Role       ?? '',
      store_id:          wf.Store_Name        ?? '',
      cluster:           wf.Cluster_Name      ?? '',
      region_name:       wf.Region_Name       ?? '',
      search_term:       wf.searchTerm        ?? '',
    })
  }, [patchFilters])

  useEffect(() => {
    loadAssortmentData()
      .then(setData)
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false))
  }, [])

  const skuNames = useMemo<Record<string, string>>(() => {
    if (!data) return {}
    return Object.fromEntries(
      Object.entries(data.skuMaster).map(([id, info]) => [id, info.Product_Name ?? id])
    )
  }, [data])

  const brandMap = useMemo<Record<string, string>>(() => {
    if (!data) return {}
    return Object.fromEntries(
      Object.entries(data.skuMaster).map(([id, info]) => [id, info.Brand ?? ''])
    )
  }, [data])

  const categoryMap = useMemo<Record<string, string>>(() => {
    if (!data) return {}
    return Object.fromEntries(
      Object.entries(data.skuMaster).map(([id, info]) => [id, info.Category ?? ''])
    )
  }, [data])

  const storeClusterMap = useMemo<Record<string, string>>(() => {
    if (!data) return {}
    return Object.fromEntries(data.storeClusters.map((c) => [c.Store_ID, c.Cluster_Label]))
  }, [data])

  const filteredRows = useMemo(() => {
    if (!data) return []
    return data.recommendations.filter((r) =>
      matchesFilters(r, filters, skuNames, brandMap, categoryMap, storeClusterMap)
    )
  }, [data, filters, skuNames, brandMap, categoryMap, storeClusterMap])

  const handleRowClick = useCallback((row: SKURecommendation) => {
    setSelected((prev) =>
      prev?.SKU_ID === row.SKU_ID && prev?.granularity_value === row.granularity_value ? null : row
    )
  }, [])

  const closeDrawer = useCallback(() => setSelected(null), [])

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center h-screen bg-gradient-to-br from-[#0F1629] to-[#1A1D2E]">
        <Loader2 size={40} className="text-[#F2A93B] animate-spin mb-4" />
        <p className="text-gray-300 text-sm font-medium">Loading Category Intelligence…</p>
      </div>
    )
  }

  if (error || !data) {
    return (
      <div className="flex flex-col items-center justify-center h-screen bg-gray-50">
        <p className="text-red-500 font-semibold text-sm mb-2">Failed to load workspace data</p>
        <p className="text-gray-400 text-xs max-w-sm text-center">
          {error || 'Unknown error'}. Run <code className="bg-gray-100 px-1 rounded">python generate_workspace_data.py</code> first.
        </p>
      </div>
    )
  }

  const drawerOpen = selected !== null

  return (
    <div className="flex flex-col overflow-hidden bg-[#F0F2F8]" style={{ height: 'calc(100vh - 96px)' }}>
      {/* Header */}
      <ExecutiveSummary summary={data.summary} />

      {/* Sticky filter bar */}
      <SmartFilterBar
        rows={data.recommendations}
        skuMaster={data.skuMaster}
        storeClusters={data.storeClusters}
        filters={filters}
        onChange={handleFilterChange}
      />

      {/* Main scrollable area */}
      <div
        className="flex-1 overflow-y-auto transition-all duration-300"
        style={{ marginRight: drawerOpen ? '500px' : '0' }}
      >
        {/* AI insight feed */}
        <InsightFeed rows={data.recommendations} summary={data.summary} skuNames={skuNames} />

        {/* Table header */}
        <div className="flex items-center justify-between px-6 py-2">
          <div className="flex items-center gap-2">
            <span className="text-[10px] font-bold uppercase tracking-widest text-gray-400">
              SKU Intelligence Table
            </span>
            <span className="bg-indigo-100 text-indigo-700 text-[10px] font-black px-2 py-0.5 rounded-full">
              {filteredRows.length} SKUs
            </span>
          </div>
          <p className="text-[11px] text-gray-400">Click a row to open the AI insight drawer →</p>
        </div>

        {/* AG Grid table */}
        <div className="px-6 pb-6">
          <div className="bg-white rounded-2xl shadow-sm overflow-hidden border border-gray-100" style={{ height: 'calc(100vh - 380px)', minHeight: '400px' }}>
            <SKUTable
              rows={filteredRows}
              skuNames={skuNames}
              selectedId={selected?.SKU_ID}
              onRowClick={handleRowClick}
            />
          </div>
        </div>
      </div>

      {/* Right drawer */}
      <SKUDrawer
        open={drawerOpen}
        sku={selected}
        data={data}
        skuNames={skuNames}
        onClose={closeDrawer}
      />
    </div>
  )
}
