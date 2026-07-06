import { useState, useEffect, useCallback } from 'react'
import { useFilters } from '../../context/FilterContext'
import { Loader2, ChevronDown, ChevronUp, CheckCircle, XCircle, History } from 'lucide-react'
import {
  fetchDivergence, postOverride, fetchOverrides,
  DivergentSKU, ClusterBreakdown,
} from '../../api/agentsApi'

const SUB_CATS = [
  '', 'Shampoo', 'Conditioner', 'Hair Color', 'Hair Oil',
  'Hair Serum', 'Hair Mask', 'Anti-Dandruff Treatment',
]

function ClusterRow({ c }: { c: ClusterBreakdown }) {
  const decColor =
    c.cluster_decision === 'Keep'  ? 'text-green-700 bg-green-100' :
    c.cluster_decision === 'Watch' ? 'text-orange-700 bg-orange-100' :
                                     'text-red-700 bg-red-100'
  return (
    <tr className="border-t border-gray-100 text-[12px]">
      <td className="py-2 px-3 font-medium">{c.cluster_label}</td>
      <td className="py-2 px-3">
        <span className={`px-2 py-0.5 rounded-full font-semibold ${decColor}`}>
          {c.cluster_decision}
        </span>
      </td>
      <td className="py-2 px-3 text-right">{c.cluster_delist_score.toFixed(3)}</td>
      <td className="py-2 px-3 text-right">{c.store_count}</td>
      <td className="py-2 px-3 text-right">${c.cluster_revenue.toLocaleString()}</td>
    </tr>
  )
}

function SKURow({ sku, onOverride }: { sku: DivergentSKU; onOverride: () => void }) {
  const [open,       setOpen]       = useState(false)
  const [note,       setNote]       = useState('')
  const [loading,    setLoading]    = useState(false)
  const [decidedBy,  setDecidedBy]  = useState('Category Manager')
  const [confirmed,  setConfirmed]  = useState<string | null>(null)

  const globalDecColor =
    sku.global_decision === 'Keep'          ? 'text-green-700 bg-green-100' :
    sku.global_decision === 'DELIST' || sku.global_decision === 'Delist'
                                            ? 'text-red-700 bg-red-100' :
                                              'text-orange-700 bg-orange-100'

  const divColor =
    sku.divergence_magnitude >= 0.5 ? 'text-red-600 font-bold' :
    sku.divergence_magnitude >= 0.3 ? 'text-orange-600 font-semibold' :
                                      'text-gray-600'

  const handleDecision = async (decision: 'approved' | 'rejected') => {
    setLoading(true)
    try {
      const maxCluster = sku.cluster_breakdown[0]
      await postOverride({
        sku_id:     sku.sku_id,
        cluster_id: maxCluster.cluster_id,
        decision,
        note,
        decided_by: decidedBy,
      })
      setConfirmed(decision)
      onOverride()
    } catch (e) {
      console.error(e)
    } finally {
      setLoading(false)
    }
  }

  return (
    <>
      <tr
        className="border-t border-gray-200 hover:bg-gray-50 cursor-pointer"
        onClick={() => setOpen(v => !v)}
      >
        <td className="py-3 px-4">
          <div className="flex items-center gap-2">
            {open ? <ChevronUp size={14} className="text-gray-400" /> : <ChevronDown size={14} className="text-gray-400" />}
            <div>
              <div className="font-semibold text-[13px] text-[#1A1D2E]">{sku.product_name}</div>
              <div className="text-[11px] text-gray-500">{sku.sku_id} · {sku.brand}</div>
            </div>
          </div>
        </td>
        <td className="py-3 px-4 text-[12px]">{sku.sub_category}</td>
        <td className="py-3 px-4">
          <span className={`px-2 py-0.5 rounded-full text-[11px] font-semibold ${globalDecColor}`}>
            {sku.global_decision}
          </span>
        </td>
        <td className="py-3 px-4 text-[12px] font-mono">{sku.global_delist_score.toFixed(3)}</td>
        <td className={`py-3 px-4 text-[13px] font-mono ${divColor}`}>
          {sku.divergence_magnitude.toFixed(3)}
        </td>
        <td className="py-3 px-4 text-[11px] text-[#4F46E5] font-medium max-w-[200px]">
          {sku.recommended_override}
        </td>
      </tr>

      {open && (
        <tr>
          <td colSpan={6} className="bg-gray-50/80 px-6 py-4 border-b border-gray-200">
            {/* Cluster breakdown table */}
            <div className="mb-4">
              <h4 className="text-[12px] font-bold text-[#1A1D2E] mb-2 uppercase tracking-wide">
                Cluster Breakdown
              </h4>
              <table className="w-full text-left bg-white rounded-lg border border-gray-200 overflow-hidden">
                <thead className="bg-gray-100 text-[11px] text-gray-500 uppercase">
                  <tr>
                    <th className="py-2 px-3">Cluster</th>
                    <th className="py-2 px-3">Decision</th>
                    <th className="py-2 px-3 text-right">Score</th>
                    <th className="py-2 px-3 text-right">Stores</th>
                    <th className="py-2 px-3 text-right">Revenue (6wk)</th>
                  </tr>
                </thead>
                <tbody>
                  {sku.cluster_breakdown.map(c => (
                    <ClusterRow key={c.cluster_id} c={c} />
                  ))}
                </tbody>
              </table>
            </div>

            {/* Override action */}
            {confirmed ? (
              <div className={`flex items-center gap-2 text-[12px] font-semibold ${confirmed === 'approved' ? 'text-green-700' : 'text-red-600'}`}>
                {confirmed === 'approved'
                  ? <><CheckCircle size={16} /> Override approved and logged.</>
                  : <><XCircle    size={16} /> Override rejected and logged.</>
                }
              </div>
            ) : (
              <div className="flex flex-wrap gap-3 items-end">
                <div>
                  <label className="text-[11px] text-gray-500 block mb-1">Decided by</label>
                  <input
                    value={decidedBy}
                    onChange={e => setDecidedBy(e.target.value)}
                    className="text-[12px] border border-gray-300 rounded-lg px-3 py-1.5 w-44"
                  />
                </div>
                <div className="flex-1">
                  <label className="text-[11px] text-gray-500 block mb-1">Note (optional)</label>
                  <input
                    value={note}
                    onChange={e => setNote(e.target.value)}
                    placeholder="Add a reason…"
                    className="w-full text-[12px] border border-gray-300 rounded-lg px-3 py-1.5"
                  />
                </div>
                <button
                  onClick={() => handleDecision('approved')}
                  disabled={loading}
                  className="flex items-center gap-1.5 px-4 py-2 bg-green-600 text-white text-[12px] font-semibold rounded-lg hover:bg-green-700 disabled:opacity-60"
                >
                  {loading ? <Loader2 size={12} className="animate-spin" /> : <CheckCircle size={12} />}
                  Approve Override
                </button>
                <button
                  onClick={() => handleDecision('rejected')}
                  disabled={loading}
                  className="flex items-center gap-1.5 px-4 py-2 bg-red-100 text-red-700 text-[12px] font-semibold rounded-lg hover:bg-red-200 disabled:opacity-60"
                >
                  <XCircle size={12} /> Reject
                </button>
              </div>
            )}
          </td>
        </tr>
      )}
    </>
  )
}

export default function LocalizationTable() {
  const { filters: gf, setFilter } = useFilters()
  const subCat = gf.sub_cat
  const minDiv = gf.min_divergence

  const [data,      setData]      = useState<DivergentSKU[]>([])
  const [loading,   setLoading]   = useState(true)
  const [overrides, setOverrides] = useState<any[]>([])
  const [showHist,  setShowHist]  = useState(false)

  const load = useCallback(() => {
    setLoading(true)
    fetchDivergence(subCat || undefined, minDiv)
      .then(setData)
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [subCat, minDiv])

  useEffect(() => { load() }, [load])

  const loadHistory = () => {
    fetchOverrides().then(setOverrides).catch(console.error)
    setShowHist(true)
  }

  return (
    <div className="space-y-4">
      {/* Filter bar */}
      <div className="flex flex-wrap gap-3 items-end">
        <div>
          <label className="text-[11px] text-gray-500 block mb-1">Sub-Category</label>
          <select
            value={subCat}
            onChange={e => setFilter('sub_cat', e.target.value)}
            className="text-[12px] border border-gray-300 rounded-lg px-3 py-2 bg-white"
          >
            {SUB_CATS.map(s => <option key={s} value={s}>{s || 'All sub-categories'}</option>)}
          </select>
        </div>
        <div>
          <label className="text-[11px] text-gray-500 block mb-1">Min divergence</label>
          <select
            value={minDiv}
            onChange={e => setFilter('min_divergence', Number(e.target.value))}
            className="text-[12px] border border-gray-300 rounded-lg px-3 py-2 bg-white"
          >
            {[0.02, 0.04, 0.06, 0.08, 0.10, 0.15, 0.20].map(v => (
              <option key={v} value={v}>{v.toFixed(2)}</option>
            ))}
          </select>
        </div>
        <button
          onClick={loadHistory}
          className="flex items-center gap-1.5 px-4 py-2 text-[12px] border border-gray-300 rounded-lg hover:bg-gray-50 text-gray-600"
        >
          <History size={14} /> My Overrides
        </button>
      </div>

      {/* Override history */}
      {showHist && (
        <div className="bg-white border border-gray-200 rounded-xl p-4">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-[13px] font-bold text-[#1A1D2E]">Override History</h3>
            <button onClick={() => setShowHist(false)} className="text-[11px] text-gray-400 hover:text-gray-600">Close</button>
          </div>
          {overrides.length === 0 ? (
            <p className="text-[12px] text-gray-400 italic">No overrides recorded yet.</p>
          ) : (
            <table className="w-full text-[12px]">
              <thead className="text-[11px] text-gray-500 uppercase border-b border-gray-100">
                <tr>
                  <th className="py-1.5 text-left">SKU</th>
                  <th className="py-1.5 text-left">Cluster</th>
                  <th className="py-1.5 text-left">Decision</th>
                  <th className="py-1.5 text-left">By</th>
                  <th className="py-1.5 text-left">At</th>
                  <th className="py-1.5 text-left">Note</th>
                </tr>
              </thead>
              <tbody>
                {overrides.map(o => (
                  <tr key={o.override_id} className="border-t border-gray-50 hover:bg-gray-50">
                    <td className="py-1.5">{o.sku_id}</td>
                    <td className="py-1.5">{o.cluster_label}</td>
                    <td className={`py-1.5 font-semibold ${o.decision === 'approved' ? 'text-green-600' : 'text-red-600'}`}>
                      {o.decision}
                    </td>
                    <td className="py-1.5 text-gray-500">{o.decided_by}</td>
                    <td className="py-1.5 text-gray-400">{o.decided_at?.slice(0, 16).replace('T', ' ')}</td>
                    <td className="py-1.5 text-gray-400">{o.note}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {/* Main table */}
      {loading ? (
        <div className="flex items-center justify-center py-16">
          <Loader2 size={22} className="text-[#4F46E5] animate-spin mr-3" />
          <span className="text-gray-500">Analysing cluster divergence…</span>
        </div>
      ) : data.length === 0 ? (
        <div className="text-center py-16 text-gray-400">
          No SKUs show cluster divergence above {minDiv.toFixed(2)} for the selected scope.
        </div>
      ) : (
        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
          <table className="w-full text-left">
            <thead className="bg-gray-50 text-[11px] text-gray-500 uppercase border-b border-gray-200">
              <tr>
                <th className="py-3 px-4">SKU</th>
                <th className="py-3 px-4">Sub-Cat</th>
                <th className="py-3 px-4">Global Decision</th>
                <th className="py-3 px-4">Global Score</th>
                <th className="py-3 px-4">Divergence</th>
                <th className="py-3 px-4">Recommended Override</th>
              </tr>
            </thead>
            <tbody>
              {data.map(sku => (
                <SKURow key={sku.sku_id} sku={sku} onOverride={load} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
