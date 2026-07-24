import { useState, useEffect, useCallback } from 'react'
import { Loader2, AlertTriangle, TrendingDown, Zap, RefreshCw, ChevronDown, ChevronUp } from 'lucide-react'
import {
  fetchWatchdogDigest, streamWatchdogNarrative,
  WatchdogDigest, WatchItem, WatchdogFilters,
} from '../../api/agentsApi'

type Props = { filters?: WatchdogFilters; topN?: number }

const SEV_COLOR: Record<string, string> = {
  red:    'bg-red-100 text-red-800 border-red-200',
  orange: 'bg-orange-100 text-orange-800 border-orange-200',
  green:  'bg-green-100 text-green-700 border-green-200',
}
const SEV_ICON: Record<string, React.ReactNode> = {
  red:    <AlertTriangle size={14} className="text-red-600" />,
  orange: <TrendingDown  size={14} className="text-orange-600" />,
  green:  <Zap           size={14} className="text-green-600" />,
}

function SeverityBadge({ severity }: { severity: string }) {
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-semibold border ${SEV_COLOR[severity] ?? ''}`}>
      {SEV_ICON[severity]}
      {severity.toUpperCase()}
    </span>
  )
}

function WatchCard({ item, index }: { item: WatchItem; index: number }) {
  const [open, setOpen] = useState(false)
  return (
    <div className={`rounded-xl border p-4 ${item.conflict ? 'border-red-300 bg-red-50/40' : 'border-gray-200 bg-white'}`}>
      <div className="flex items-start gap-3">
        <span className="flex-shrink-0 w-7 h-7 rounded-full bg-[#1A1D2E] text-white text-[11px] font-bold flex items-center justify-center">
          {index + 1}
        </span>
        <div className="flex-1 min-w-0">
          <div className="flex items-center flex-wrap gap-2 mb-1">
            <span className="font-semibold text-[13px] text-[#1A1D2E] truncate">{item.product_name}</span>
            <SeverityBadge severity={item.severity} />
            {item.conflict && (
              <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-bold bg-red-200 text-red-900 border border-red-300">
                ⚡ CONFLICT
              </span>
            )}
          </div>
          <div className="text-[11px] text-gray-500 mb-2">
            Store: {item.store_id} · {item.signal_types.join(' + ')}
          </div>
          <div className="flex flex-wrap gap-4 text-[12px] mb-2">
            <span className="text-gray-700">
              💰 <strong>${item.financial_impact_usd.toLocaleString()}</strong>
            </span>
            <span className="text-[#4F46E5] font-medium">{item.suggested_action}</span>
          </div>
          <p className="text-[12px] text-gray-600 italic leading-relaxed">{item.narrative.split('\n')[0]}</p>
          {item.root_cause && (
            <div className="mt-2 flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 px-2.5 py-1.5">
              <span className="text-[13px] leading-none">🔍</span>
              <p className="text-[11px] text-amber-900 leading-relaxed">
                <strong>Root Cause: {item.root_cause.root_cause}</strong> — {item.root_cause.root_cause_detail}
              </p>
            </div>
          )}
          {item.source_signals && Object.keys(item.source_signals).length > 0 && (
            <button
              onClick={() => setOpen(v => !v)}
              className="mt-2 flex items-center gap-1 text-[11px] text-gray-400 hover:text-gray-600"
            >
              {open ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
              {open ? 'Hide signals' : 'Show signals'}
            </button>
          )}
          {open && (
            <div className="mt-2 p-2 bg-gray-50 rounded-lg text-[11px] text-gray-500 font-mono">
              {Object.entries(item.source_signals).map(([k, v]) =>
                v != null ? <div key={k}>{k}: {String(v)}</div> : null
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export default function WatchdogPanel({ filters = {}, topN = 10 }: Props) {
  const [digest,    setDigest]    = useState<WatchdogDigest | null>(null)
  const [loading,   setLoading]   = useState(true)
  const [narrative, setNarrative] = useState('')
  const [streaming, setStreaming] = useState(false)
  const [conflict,  setConflict]  = useState(false)

  const load = useCallback(() => {
    setLoading(true)
    fetchWatchdogDigest({ ...filters, top_n: topN })
      .then(setDigest)
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [filters, topN])

  useEffect(() => { load() }, [load])

  const generateSummary = () => {
    setNarrative('')
    setStreaming(true)
    setConflict(false)
    streamWatchdogNarrative(
      { ...filters, top_n: topN },
      tok => setNarrative(p => p + tok),
      ()  => setStreaming(false),
      err => { setNarrative(err); setStreaming(false); setConflict(true) },
    )
  }

  if (loading) return (
    <div className="flex items-center justify-center py-16">
      <Loader2 size={24} className="text-[#4F46E5] animate-spin mr-3" />
      <span className="text-gray-500">Building watchdog digest…</span>
    </div>
  )

  if (!digest) return (
    <div className="text-center py-16 text-gray-400">Failed to load digest.</div>
  )

  const { summary, items } = digest

  return (
    <div className="space-y-4">
      {/* Summary strip */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        {[
          { label: 'Total Items',    value: summary.total_items },
          { label: '🔴 Critical',    value: summary.red,    cls: 'text-red-600' },
          { label: '🟠 Warning',     value: summary.orange, cls: 'text-orange-600' },
          { label: '$ At Risk',      value: `$${summary.total_financial_impact_usd.toLocaleString()}` },
        ].map(kpi => (
          <div key={kpi.label} className="bg-white border border-gray-200 rounded-xl p-3 text-center shadow-sm">
            <div className={`text-[20px] font-bold ${kpi.cls ?? 'text-[#1A1D2E]'}`}>{kpi.value}</div>
            <div className="text-[11px] text-gray-500 mt-0.5">{kpi.label}</div>
          </div>
        ))}
      </div>

      {/* Executive summary button + output */}
      <div className="bg-gradient-to-br from-[#1A1D2E] to-[#2D3250] rounded-xl p-4 text-white">
        <div className="flex items-center justify-between mb-3">
          <span className="font-semibold text-[13px]">🤖 Executive Summary (AI)</span>
          <div className="flex gap-2">
            <button
              onClick={load}
              className="flex items-center gap-1 px-3 py-1.5 rounded-full text-[11px] bg-white/10 hover:bg-white/20 transition-colors"
            >
              <RefreshCw size={12} /> Refresh
            </button>
            <button
              onClick={generateSummary}
              disabled={streaming}
              className="flex items-center gap-1 px-3 py-1.5 rounded-full text-[11px] bg-[#F2A93B] text-[#1A1D2E] font-bold hover:opacity-90 disabled:opacity-60"
            >
              {streaming ? <Loader2 size={12} className="animate-spin" /> : '✨'}
              {streaming ? 'Generating…' : 'Generate Summary'}
            </button>
          </div>
        </div>
        {narrative ? (
          <p className={`text-[12px] leading-relaxed whitespace-pre-wrap ${conflict ? 'text-red-300' : 'text-gray-200'}`}>
            {narrative}
            {streaming && <span className="animate-pulse">▌</span>}
          </p>
        ) : (
          <p className="text-[12px] text-gray-400 italic">
            Click "Generate Summary" to get an AI-powered executive briefing on today's priorities.
          </p>
        )}
      </div>

      {/* Ranked list */}
      {items.length === 0 ? (
        <div className="text-center py-10 text-gray-400">
          No watchdog items for the current filters.
        </div>
      ) : (
        <div className="space-y-3">
          {items.map((item, i) => <WatchCard key={`${item.sku_id}-${item.store_id}`} item={item} index={i} />)}
        </div>
      )}
    </div>
  )
}
