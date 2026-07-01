interface SkuCard {
  SKU_ID: string
  Product_Name?: string
  Sub_Category?: string
  Brand?: string
  delist_score: number
  Health_Score_100: number
  Calc_Growth_Pct?: number
  GMROI?: number
  Basket_Role?: string
  Revenue?: number
  Recommended_Action?: string
}

interface DelistData {
  Keep:    SkuCard[]
  Grow:    SkuCard[]
  Watch:   SkuCard[]
  Delist:  SkuCard[]
  insight: string
}

interface Props { data: DelistData | null }

const BUCKET_CONFIG = {
  Keep:   { bg: 'bg-emerald-50', border: 'border-emerald-200', badge: 'bg-emerald-500', icon: '✅' },
  Grow:   { bg: 'bg-blue-50',    border: 'border-blue-200',    badge: 'bg-blue-500',    icon: '📈' },
  Watch:  { bg: 'bg-amber-50',   border: 'border-amber-200',   badge: 'bg-amber-500',   icon: '👀' },
  Delist: { bg: 'bg-red-50',     border: 'border-red-200',     badge: 'bg-red-500',     icon: '🗑' },
}

const fmtRevenue = (n?: number) => {
  if (!n) return '—'
  return n >= 1_000_000 ? `$${(n / 1_000_000).toFixed(1)}M` : n >= 1_000 ? `$${(n / 1_000).toFixed(0)}K` : `$${Math.round(n)}`
}

function SkuPill({ card, bucket }: { card: SkuCard; bucket: string }) {
  const cfg = BUCKET_CONFIG[bucket as keyof typeof BUCKET_CONFIG]
  return (
    <div className={`rounded-lg border ${cfg.border} ${cfg.bg} px-3 py-2.5 mb-2`}>
      <div className="flex items-start justify-between gap-1 mb-1">
        <p className="text-[12px] font-bold text-[#1A1D2E] leading-tight line-clamp-2 flex-1">
          {card.Product_Name ?? card.SKU_ID}
        </p>
        <div className={`${cfg.badge} text-white text-[9px] font-bold px-1.5 py-0.5 rounded-full whitespace-nowrap shrink-0`}>
          {(card.delist_score * 100).toFixed(0)}
        </div>
      </div>
      <p className="text-[10px] text-gray-500 mb-1.5 truncate">{card.Sub_Category} · {card.Brand}</p>
      <div className="flex flex-wrap gap-1">
        <span className={`text-[9.5px] font-semibold px-1.5 py-0.5 rounded-full ${(card.Calc_Growth_Pct ?? 0) >= 0 ? 'bg-emerald-100 text-emerald-700' : 'bg-red-100 text-red-600'}`}>
          {(card.Calc_Growth_Pct ?? 0) > 0 ? '+' : ''}{(card.Calc_Growth_Pct ?? 0).toFixed(0)}% growth
        </span>
        <span className="text-[9.5px] px-1.5 py-0.5 rounded-full bg-gray-100 text-gray-600">
          H:{card.Health_Score_100?.toFixed(0)}/100
        </span>
        {card.Basket_Role && card.Basket_Role !== 'Unknown' && (
          <span className="text-[9.5px] px-1.5 py-0.5 rounded-full bg-indigo-100 text-indigo-700">
            {card.Basket_Role}
          </span>
        )}
        <span className="text-[9.5px] px-1.5 py-0.5 rounded-full bg-gray-100 text-gray-600">
          {fmtRevenue(card.Revenue)}
        </span>
      </div>
    </div>
  )
}

export default function DelistHub({ data }: Props) {
  if (!data) return null

  const buckets: Array<keyof typeof BUCKET_CONFIG> = ['Keep', 'Grow', 'Watch', 'Delist']

  return (
    <div>
      {data.insight && (
        <div className="bg-amber-50 border border-amber-200 rounded-xl px-4 py-2.5 mb-4 text-[12px] text-amber-800 font-medium">
          💡 {data.insight}
        </div>
      )}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {buckets.map(b => {
          const cfg = BUCKET_CONFIG[b]
          const cards = data[b] ?? []
          return (
            <div key={b} className="flex flex-col">
              <div className={`flex items-center justify-between px-3 py-2 rounded-t-xl border-t border-x ${cfg.border} ${cfg.bg}`}>
                <span className="font-bold text-[12.5px] text-[#1A1D2E]">{cfg.icon} {b}</span>
                <span className={`${cfg.badge} text-white text-[10px] font-bold w-5 h-5 rounded-full flex items-center justify-center`}>
                  {cards.length}
                </span>
              </div>
              <div className={`flex-1 border border-t-0 ${cfg.border} rounded-b-xl p-2 min-h-[200px] max-h-[400px] overflow-y-auto`}>
                {cards.length === 0
                  ? <p className="text-center text-gray-400 text-xs pt-6">No SKUs</p>
                  : cards.map(c => <SkuPill key={c.SKU_ID} card={c} bucket={b} />)}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
