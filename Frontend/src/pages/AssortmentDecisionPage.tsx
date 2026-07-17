import { useState, useEffect, useCallback, useRef } from 'react'
import { fetchAssortmentDecisions, type AssortmentDecisionRow } from '../api/assortmentData'

const POLL_MS = 4000

const COLUMNS: { key: keyof AssortmentDecisionRow; label: string }[] = [
  { key: 'Decision',      label: 'Decision' },
  { key: 'Decision_Type', label: 'Decision_Type' },
  { key: 'Comment',       label: 'Comment' },
  { key: 'SKU_ID',        label: 'SKU_ID' },
  { key: 'Product_Name',  label: 'Product_Name' },
  { key: 'Brand',         label: 'Brand' },
  { key: 'Category',      label: 'Category' },
  { key: 'Sub_Category',  label: 'Sub_Category' },
  { key: 'View_Label',    label: 'View_Label' },
  { key: 'Scope',         label: 'Scope' },
  { key: 'ABC_Class',     label: 'ABC_Class' },
  { key: 'Basket_Role',   label: 'Basket_Role' },
  { key: 'Scope_Detail',  label: 'Scope_Details' },
]

export default function AssortmentDecisionPage() {
  const [rows, setRows] = useState<AssortmentDecisionRow[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null)
  const firstLoad = useRef(true)

  const load = useCallback(() => {
    fetchAssortmentDecisions()
      .then((data) => {
        // Most recent decision first
        const sorted = [...data].sort((a, b) => (b.Timestamp ?? '').localeCompare(a.Timestamp ?? ''))
        setRows(sorted)
        setLastUpdated(new Date())
        setError('')
      })
      .catch((e) => setError(e instanceof Error ? e.message : 'Failed to load decisions'))
      .finally(() => {
        if (firstLoad.current) {
          setLoading(false)
          firstLoad.current = false
        }
      })
  }, [])

  useEffect(() => {
    load()
    const id = setInterval(load, POLL_MS)
    return () => clearInterval(id)
  }, [load])

  return (
    <div className="px-5 py-5 max-w-[1600px] mx-auto">
      <div className="flex items-center justify-between mb-4 flex-wrap gap-3">
        <div>
          <h2 className="text-2xl font-extrabold text-[#1A1D2E]">Assortment Decision</h2>
          <p className="text-[12px] text-gray-400 mt-0.5">
            Live log of confirmed assortment decisions — updates automatically.
          </p>
        </div>
        <div className="flex items-center gap-2 text-[11px] text-gray-400">
          <span className="relative flex h-2 w-2">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
            <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500" />
          </span>
          Live
          {lastUpdated && <span>&middot; updated {lastUpdated.toLocaleTimeString()}</span>}
        </div>
      </div>

      {error && (
        <div className="mb-4 p-3 rounded-xl bg-red-50 border border-red-200 text-[12px] text-red-700">
          {error}
        </div>
      )}

      <div className="bg-white border border-gray-200 rounded-xl shadow-sm overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center h-48">
            <div className="w-8 h-8 border-4 border-indigo-200 border-t-indigo-600 rounded-full animate-spin" />
          </div>
        ) : rows.length === 0 ? (
          <div className="text-center py-12 text-gray-400 text-sm">
            No assortment decisions recorded yet.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-[12px]">
              <thead>
                <tr className="bg-gray-50 border-b border-gray-200">
                  {COLUMNS.map((c) => (
                    <th key={c.key} className="text-left px-3 py-2 font-semibold text-gray-500 text-[10.5px] uppercase tracking-wider whitespace-nowrap">
                      {c.label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((r, i) => (
                  <tr key={i} className={`border-b border-gray-100 hover:bg-blue-50/40 transition-colors ${i % 2 === 0 ? 'bg-white' : 'bg-gray-50/30'}`}>
                    {COLUMNS.map((c) => (
                      <td key={c.key} className="px-3 py-2 text-gray-700 max-w-[220px] truncate" title={r[c.key] ?? ''}>
                        {r[c.key] || '—'}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}
