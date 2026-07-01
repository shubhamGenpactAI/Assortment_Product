import { useState, useEffect, useMemo } from 'react'
import { AgGridReact } from 'ag-grid-react'
import type { ColDef } from 'ag-grid-community'
import PlotlyChart from '../components/ui/PlotlyChart'
import { fetchStores, fetchSkuPerformance, fetchBrandShare } from '../api/generalApi'

const COLORS = ['#4F46E5','#F2A93B','#27AE60','#E84040','#8B5CF6','#06B6D4','#F59E0B','#10B981']

export default function SkuPerformancePage() {
  const [stores, setStores]   = useState<string[]>([])
  const [store, setStore]     = useState('')
  const [rows, setRows]       = useState<any[]>([])
  const [brands, setBrands]   = useState<any[]>([])
  const [loading, setLoading] = useState(false)

  useEffect(() => { fetchStores().then(s => { setStores(s); setStore(s[0] || '') }) }, [])

  useEffect(() => {
    if (!store) return
    setLoading(true)
    Promise.all([fetchSkuPerformance(store), fetchBrandShare(store)])
      .then(([r, b]) => { setRows(r); setBrands(b) })
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [store])

  const colDefs = useMemo<ColDef[]>(() => [
    { field: 'Rank',        width: 65,  headerName: '#' },
    { field: 'SKU_ID',      width: 100 },
    { field: 'Product_Name',width: 200, headerName: 'Product' },
    { field: 'Brand',       width: 110 },
    { field: 'Sub_Category',width: 130, headerName: 'Sub-Cat' },
    { field: 'Hist_Qty',    width: 120, headerName: 'Hist Qty',   type: 'numericColumn', valueFormatter: p => p.value?.toLocaleString() },
    { field: 'FC_Qty',      width: 120, headerName: 'FC Qty',     type: 'numericColumn', valueFormatter: p => p.value?.toLocaleString(),
      cellStyle: { fontWeight: 700, color: '#4F46E5' } },
    { field: 'Growth_Pct',  width: 105, headerName: 'Growth %',  type: 'numericColumn',
      valueFormatter: p => p.value != null ? `${p.value > 0 ? '+' : ''}${p.value}%` : '—',
      cellStyle: (p: any) => ({ color: p.value >= 0 ? '#27AE60' : '#E84040', fontWeight: 600 }) },
    { field: 'Demand_Tier', width: 105, headerName: 'Tier',
      cellStyle: (p: any) => ({ color: p.value === 'High' ? '#27AE60' : p.value === 'Low' ? '#E84040' : '#F2A93B', fontWeight: 600 }) },
    { field: 'Margin_Pct',  width: 100, headerName: 'Margin %',  type: 'numericColumn', valueFormatter: p => p.value != null ? `${p.value}%` : '—' },
  ], [])

  // Top 10 bar
  const top10 = rows.slice(0, 10)
  const barTraces = [{
    x: top10.map(r => r.FC_Qty), y: top10.map(r => (r.Product_Name || r.SKU_ID)?.slice(0, 25)),
    type: 'bar' as const, orientation: 'h' as const, name: 'Forecast Qty',
    marker: { color: '#4F46E5' },
  }]

  // Brand pie
  const pieTraces = [{
    labels: brands.map((b: any) => b.name), values: brands.map((b: any) => b.value),
    type: 'pie' as const, hole: 0.45,
    marker: { colors: COLORS },
    textinfo: 'label+percent' as const, textfont: { size: 10 },
  }]

  return (
    <div className="px-5 py-5 max-w-[1600px] mx-auto">
      <div className="flex items-center gap-4 mb-4">
        <h2 className="text-2xl font-extrabold text-[#1A1D2E]">📋 SKU Performance</h2>
        <div className="flex items-center gap-2">
          <label className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Store</label>
          <select className="filter-select w-36" value={store} onChange={e => setStore(e.target.value)}>
            {stores.map(s => <option key={s} value={s}>{s}</option>)}
          </select>
        </div>
      </div>

      {loading ? (
        <div className="flex items-center justify-center h-48">
          <div className="w-8 h-8 border-4 border-indigo-200 border-t-indigo-600 rounded-full animate-spin" />
        </div>
      ) : (
        <>
          {/* SKU Table */}
          <div className="card mb-4">
            <p className="sec-hdr">SKU Summary — {store}</p>
            <div className="ag-theme-alpine" style={{ height: 380 }}>
              <AgGridReact rowData={rows} columnDefs={colDefs}
                defaultColDef={{ resizable: true, sortable: true, filter: true }}
                rowHeight={34} headerHeight={38} />
            </div>
          </div>

          {/* Charts row */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <div className="card">
              <p className="sec-hdr">Top 10 SKUs by Forecast Qty</p>
              <PlotlyChart traces={barTraces} height={300}
                layout={{ margin: { l: 180, r: 20, t: 10, b: 40 }, xaxis: { title: { text: 'Units' } } }} />
            </div>
            <div className="card">
              <p className="sec-hdr">Brand Demand Share</p>
              <PlotlyChart traces={pieTraces} height={300} layout={{ margin: { l: 20, r: 20, t: 20, b: 20 }, showlegend: true, legend: { font: { size: 10 } } }} />
            </div>
          </div>
        </>
      )}
    </div>
  )
}
