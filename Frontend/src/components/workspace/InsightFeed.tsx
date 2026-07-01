import { Zap, TrendingDown, AlertCircle, ShoppingCart, Star, RefreshCw } from 'lucide-react'
import type { SKURecommendation, WorkspaceSummary } from '../../types/assortment'

interface Insight {
  icon:  React.ReactNode
  color: string
  text:  string
}

function buildInsights(rows: SKURecommendation[], summary: WorkspaceSummary, skuNames: Record<string, string>): Insight[] {
  const global = rows.filter((r) => r.granularity_level === 'Global')
  const insights: Insight[] = []

  // Delist count
  const delistSKUs = global.filter((r) => r.Decision === 'DELIST')
  if (delistSKUs.length > 0) {
    insights.push({
      icon: <AlertCircle size={13} />, color: 'text-red-500',
      text: `${delistSKUs.length} SKU${delistSKUs.length > 1 ? 's' : ''} confirmed for delisting — immediate planogram action recommended.`,
    })
  }

  // GMROI declining
  const lowGMROI = global.filter((r) => r.GMROI_Band === 'LOW_GMROI')
  if (lowGMROI.length > 0) {
    insights.push({
      icon: <TrendingDown size={13} />, color: 'text-orange-500',
      text: `${lowGMROI.length} SKUs show below-average inventory return (GMROI). Review replenishment strategy.`,
    })
  }

  // Anchor basket roles under watch
  const anchorWatch = global.filter((r) => r.Basket_Role === 'Anchor' && (r.Decision === 'KEEP_WATCH' || r.Decision === 'PHASE_OUT'))
  if (anchorWatch.length > 0) {
    insights.push({
      icon: <ShoppingCart size={13} />, color: 'text-amber-500',
      text: `${anchorWatch.length} basket-anchor SKU${anchorWatch.length > 1 ? 's' : ''} under performance pressure — removal could disrupt co-purchase patterns.`,
    })
  }

  // High sentiment stars
  const highSentiment = global.filter((r) => r.SentimentIndex != null && r.SentimentIndex > 0.75 && r.Decision !== 'DELIST')
  if (highSentiment.length > 0) {
    const name = highSentiment[0].SKU_ID in skuNames ? skuNames[highSentiment[0].SKU_ID] : highSentiment[0].SKU_ID
    insights.push({
      icon: <Star size={13} />, color: 'text-indigo-500',
      text: `${highSentiment.length} SKU${highSentiment.length > 1 ? 's have' : ' has'} high consumer sentiment (>75%). ${name.split(' ').slice(0, 3).join(' ')} leads the set.`,
    })
  }

  // Expand candidates
  const expandCandidates = global.filter((r) => r.Decision === 'EXPAND' || r.Decision === 'FUTURE_STAR')
  if (expandCandidates.length > 0) {
    insights.push({
      icon: <Zap size={13} />, color: 'text-emerald-500',
      text: `${expandCandidates.length} SKU${expandCandidates.length > 1 ? 's qualify' : ' qualifies'} for expansion or accelerated investment — high growth + strong health.`,
    })
  }

  // Substitution / replacement opportunities
  const replaceable = global.filter((r) => r.Decision === 'REPLACE' && (r.Recapture_Potential ?? 0) > 0.4)
  if (replaceable.length > 0) {
    insights.push({
      icon: <RefreshCw size={13} />, color: 'text-sky-500',
      text: `${replaceable.length} SKU${replaceable.length > 1 ? 's' : ''} flagged for replacement with high recapture potential — in-category substitutes available.`,
    })
  }

  // Category avg forecast
  if (summary.avgForecastGrowth != null) {
    const dir = summary.avgForecastGrowth >= 0 ? 'positive' : 'negative'
    insights.push({
      icon: <TrendingDown size={13} />, color: summary.avgForecastGrowth >= 0 ? 'text-emerald-500' : 'text-red-400',
      text: `Category average forecast growth is ${dir} at ${summary.avgForecastGrowth >= 0 ? '+' : ''}${summary.avgForecastGrowth.toFixed(1)}% based on available SKU-level projections.`,
    })
  }

  return insights.slice(0, 6)
}

interface Props {
  rows:     SKURecommendation[]
  summary:  WorkspaceSummary
  skuNames: Record<string, string>
}

export function InsightFeed({ rows, summary, skuNames }: Props) {
  const insights = buildInsights(rows, summary, skuNames)
  if (insights.length === 0) return null

  return (
    <div className="px-6 py-3">
      <div className="flex items-center gap-2 mb-2">
        <Zap size={12} className="text-[#F2A93B]" />
        <span className="text-[10px] font-bold uppercase tracking-widest text-gray-400">AI Insight Feed</span>
      </div>
      <div className="flex gap-2 overflow-x-auto scrollbar-hide">
        {insights.map((ins, i) => (
          <div
            key={i}
            className="flex items-start gap-2 bg-white border border-gray-100 rounded-xl px-3 py-2.5 shadow-sm
                       hover:shadow-md hover:border-gray-200 transition-all cursor-default flex-1 min-w-0"
          >
            <span className={`flex-shrink-0 mt-0.5 ${ins.color}`}>{ins.icon}</span>
            <p className="text-[11px] text-gray-600 leading-relaxed">{ins.text}</p>
          </div>
        ))}
      </div>
    </div>
  )
}
