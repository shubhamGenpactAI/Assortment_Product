import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { AlertTriangle, Zap, ArrowRight, Loader2 } from 'lucide-react'
import { fetchWatchdogDigest, WatchItem } from '../../api/agentsApi'

const SEV_STYLES: Record<string, string> = {
  red:    'bg-red-50 border-red-200',
  orange: 'bg-orange-50 border-orange-200',
  green:  'bg-green-50 border-green-200',
}
const SEV_TEXT: Record<string, string> = {
  red:    'text-red-700',
  orange: 'text-orange-700',
  green:  'text-green-700',
}

function MiniCard({ item }: { item: WatchItem }) {
  return (
    <div className={`rounded-xl border p-3 flex-1 min-w-[200px] ${SEV_STYLES[item.severity] ?? ''}`}>
      <div className="flex items-center gap-1.5 mb-1">
        {item.severity === 'red'
          ? <AlertTriangle size={12} className="text-red-500 flex-shrink-0" />
          : <Zap size={12} className={`flex-shrink-0 ${SEV_TEXT[item.severity]}`} />
        }
        <span className={`text-[11px] font-bold ${SEV_TEXT[item.severity]}`}>
          #{item.priority_rank}
        </span>
        {item.conflict && (
          <span className="text-[10px] font-bold text-red-700 bg-red-200 px-1.5 py-0.5 rounded-full">CONFLICT</span>
        )}
      </div>
      <div className="text-[12px] font-semibold text-[#1A1D2E] truncate">{item.product_name}</div>
      <div className="text-[11px] text-gray-500">
        {item.signal_types.join(' + ')} · Store {item.store_id}
      </div>
      <div className="text-[11px] font-medium text-[#4F46E5] mt-1">
        ${item.financial_impact_usd.toLocaleString()}
      </div>
    </div>
  )
}

export default function WatchdogBanner() {
  const navigate  = useNavigate()
  const [top3, setTop3]       = useState<WatchItem[]>([])
  const [loading, setLoading] = useState(true)
  const [redCount, setRed]    = useState(0)

  useEffect(() => {
    fetchWatchdogDigest({ top_n: 3 })
      .then(d => {
        setTop3(d.items)
        setRed(d.summary.red)
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  if (loading) return (
    <div className="flex items-center gap-2 px-4 py-3 bg-[#1A1D2E]/5 rounded-xl border border-gray-200 mb-4 text-[12px] text-gray-400">
      <Loader2 size={14} className="animate-spin" /> Loading today's priorities…
    </div>
  )

  if (top3.length === 0) return null

  return (
    <div className="mb-4 bg-white rounded-2xl border border-[#4F46E5]/20 shadow-sm p-4">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className="text-[13px] font-bold text-[#1A1D2E]">🕵️ Today's Priorities</span>
          {redCount > 0 && (
            <span className="px-2 py-0.5 text-[11px] font-bold bg-red-100 text-red-700 rounded-full border border-red-200">
              {redCount} critical
            </span>
          )}
        </div>
        <button
          onClick={() => navigate('/agent-hub')}
          className="flex items-center gap-1 text-[11px] text-[#4F46E5] hover:underline font-medium"
        >
          View all <ArrowRight size={12} />
        </button>
      </div>
      <div className="flex flex-wrap gap-3">
        {top3.map(item => <MiniCard key={`${item.sku_id}-${item.store_id}`} item={item} />)}
      </div>
    </div>
  )
}
