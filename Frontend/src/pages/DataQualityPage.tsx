import { useState, useEffect, useMemo } from 'react'
import { AgGridReact } from 'ag-grid-react'
import type { ColDef } from 'ag-grid-community'
import { fetchDataQuality } from '../api/generalApi'

export default function DataQualityPage() {
  const [rows, setRows]     = useState<any[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetchDataQuality().then(setRows).catch(console.error).finally(() => setLoading(false))
  }, [])

  const colDefs = useMemo<ColDef[]>(() => [
    { field: 'File',            flex: 1,    headerName: 'File', cellStyle: { fontWeight: 600 } },
    { field: 'Rows',            width: 100, headerName: 'Rows', type: 'numericColumn', valueFormatter: p => p.value?.toLocaleString() },
    { field: 'Columns',         width: 100, headerName: 'Cols' },
    { field: 'Missing_Columns', flex: 1,    headerName: 'Missing Columns',
      cellStyle: (p: any) => ({ color: p.value && p.value !== '—' ? '#E84040' : '#27AE60' }) },
    { field: 'Status',          width: 140, headerName: 'Status',
      cellStyle: (p: any) => ({ fontWeight: 700,
        color: p.value?.includes('OK') ? '#27AE60' : p.value?.includes('Missing') ? '#E84040' : '#F2A93B' }) },
  ], [])

  const ok      = rows.filter(r => r.Status?.includes('OK')).length
  const missing = rows.filter(r => r.Status?.includes('Missing')).length
  const warn    = rows.filter(r => r.Status?.includes('missing')).length

  return (
    <div className="px-5 py-5 max-w-[1600px] mx-auto">
      <h2 className="text-2xl font-extrabold text-[#1A1D2E] mb-4">🩺 Data Quality / File Status</h2>

      <div className="flex gap-3 mb-4">
        <div className="kpi-box"><p className="text-[10px] text-gray-400 uppercase tracking-wide">Files OK</p>
          <p className="text-2xl font-extrabold text-[#27AE60]">{ok}</p></div>
        <div className="kpi-box"><p className="text-[10px] text-gray-400 uppercase tracking-wide">Missing</p>
          <p className="text-2xl font-extrabold text-[#E84040]">{missing}</p></div>
        <div className="kpi-box"><p className="text-[10px] text-gray-400 uppercase tracking-wide">Warnings</p>
          <p className="text-2xl font-extrabold text-[#F2A93B]">{warn}</p></div>
        <div className="kpi-box"><p className="text-[10px] text-gray-400 uppercase tracking-wide">Total Files</p>
          <p className="text-2xl font-extrabold text-[#1A1D2E]">{rows.length}</p></div>
      </div>

      {loading ? (
        <div className="flex items-center justify-center h-48">
          <div className="w-8 h-8 border-4 border-indigo-200 border-t-indigo-600 rounded-full animate-spin" />
        </div>
      ) : (
        <div className="card">
          <p className="sec-hdr">File Inventory</p>
          <div className="ag-theme-alpine" style={{ height: 420 }}>
            <AgGridReact rowData={rows} columnDefs={colDefs}
              defaultColDef={{ resizable: true, sortable: true }}
              rowHeight={36} headerHeight={38} />
          </div>
        </div>
      )}
    </div>
  )
}
