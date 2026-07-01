interface Kpi { label: string; value: string; sub?: string; color: string }

function KpiCard({ label, value, sub, color }: Kpi) {
  const border: Record<string, string> = {
    green:  'border-l-emerald-500',
    red:    'border-l-red-500',
    amber:  'border-l-amber-500',
    blue:   'border-l-blue-500',
    indigo: 'border-l-indigo-500',
    purple: 'border-l-purple-500',
  }
  return (
    <div className={`bg-white rounded-xl shadow-sm border border-gray-200 border-l-4 ${border[color] ?? border.blue} px-4 py-3.5`}>
      <p className="text-[10px] font-bold uppercase tracking-wider text-gray-400 mb-1">{label}</p>
      <p className="text-xl font-extrabold text-[#1A1D2E]">{value}</p>
      {sub && <p className="text-[11px] text-gray-400 mt-0.5">{sub}</p>}
    </div>
  )
}

const fmt = (n: number) =>
  n >= 1_000_000 ? `$${(n / 1_000_000).toFixed(1)}M`
  : n >= 1_000   ? `$${(n / 1_000).toFixed(0)}K`
  : `$${n.toFixed(0)}`

interface Props { data: Record<string, number> | null }

export default function KpiHeader({ data }: Props) {
  if (!data) return null

  const cards: Kpi[] = [
    { label: 'Forecast Revenue (6 wk)',    value: fmt(data.forecast_revenue ?? 0),       sub: 'Across all stores & SKUs',    color: 'blue'   },
    { label: 'Forecast Margin (6 wk)',     value: fmt(data.forecast_margin ?? 0),        sub: 'Net after cost',              color: 'green'  },
    { label: 'Revenue at Risk',            value: fmt(data.revenue_at_risk ?? 0),        sub: 'Stock-out exposure',          color: 'red'    },
    { label: 'Excess Inventory Value',     value: fmt(data.excess_inventory_value ?? 0), sub: '>12 wks cover',               color: 'amber'  },
    { label: 'Delist Candidates',          value: String(data.delist_count ?? 0),        sub: 'SKUs scoring > 0.65',         color: 'purple' },
    { label: 'Growth Opportunities',       value: String(data.growth_opportunities ?? 0),sub: '>15% forecast growth',        color: 'indigo' },
  ]

  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
      {cards.map(c => <KpiCard key={c.label} {...c} />)}
    </div>
  )
}
