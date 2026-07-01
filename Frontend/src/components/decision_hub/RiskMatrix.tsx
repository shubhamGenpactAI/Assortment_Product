import { useState } from 'react'

interface MatrixRow {
  SKU_ID: string
  Product_Name?: string
  Store_ID: string
  Sub_Category?: string
  Brand?: string
  risk_bucket: string
  action: string
  financial_impact_usd: number
  WoC: number
  Lost_Revenue?: number
  Calc_Growth_Pct?: number
  Health_Score_100?: number
  delist_score?: number
}

interface Props { rows: MatrixRow[] }

const BUCKETS = [
  { key: 'Stock-out Risk',      icon: '🔴', color: 'bg-red-500',     tab: 'red-tab'    },
  { key: 'Excess Inventory',    icon: '🟡', color: 'bg-amber-400',   tab: 'amber-tab'  },
  { key: 'Growth Opportunity',  icon: '🟢', color: 'bg-emerald-500', tab: 'green-tab'  },
  { key: 'Delist Candidate',    icon: '🟣', color: 'bg-purple-500',  tab: 'purple-tab' },
  { key: 'Transfer Candidate',  icon: '🔵', color: 'bg-blue-500',    tab: 'blue-tab'   },
]

const ACTION_COLORS: Record<string, string> = {
  'Replenish Now':     'bg-red-100 text-red-700',
  'Reduce Orders':     'bg-amber-100 text-amber-700',
  'Expand Assortment': 'bg-emerald-100 text-emerald-700',
  'Review Delisting':  'bg-purple-100 text-purple-700',
  'Transfer Stock':    'bg-blue-100 text-blue-700',
}

const fmtMoney = (n: number) =>
  n >= 1_000_000 ? `$${(n / 1_000_000).toFixed(1)}M`
  : n >= 1_000   ? `$${(n / 1_000).toFixed(0)}K`
  : `$${Math.round(n)}`

export default function RiskMatrix({ rows }: Props) {
  const [active, setActive] = useState('Stock-out Risk')

  const countFor = (b: string) => rows.filter(r => r.risk_bucket === b).length
  const visible   = rows.filter(r => r.risk_bucket === active).slice(0, 50)

  return (
    <div>
      {/* Bucket tabs */}
      <div className="flex flex-wrap gap-2 mb-3">
        {BUCKETS.map(b => {
          const cnt = countFor(b.key)
          return (
            <button
              key={b.key}
              onClick={() => setActive(b.key)}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-full text-[11.5px] font-semibold border transition-all
                ${active === b.key
                  ? 'bg-[#1A1D2E] text-white border-[#1A1D2E]'
                  : 'bg-white text-gray-600 border-gray-200 hover:bg-gray-50'}`}
            >
              {b.icon} {b.key}
              <span className={`inline-block w-4.5 h-4.5 rounded-full text-[10px] text-white font-bold px-1 ${b.color}`}>
                {cnt}
              </span>
            </button>
          )
        })}
      </div>

      {visible.length === 0 ? (
        <div className="text-center py-8 text-gray-400 text-sm">No SKUs in this bucket</div>
      ) : (
        <div className="overflow-x-auto rounded-xl border border-gray-200">
          <table className="w-full text-[12px]">
            <thead>
              <tr className="bg-gray-50 border-b border-gray-200">
                {['SKU','Product','Store','Sub-Cat','Action','Impact','WoC','Growth %'].map(h => (
                  <th key={h} className="text-left px-3 py-2 font-semibold text-gray-500 text-[10.5px] uppercase tracking-wider">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {visible.map((r, i) => (
                <tr key={i} className={`border-b border-gray-100 hover:bg-blue-50/40 transition-colors ${i % 2 === 0 ? 'bg-white' : 'bg-gray-50/30'}`}>
                  <td className="px-3 py-2 font-mono text-[11px] text-gray-500">{r.SKU_ID}</td>
                  <td className="px-3 py-2 font-medium text-[#1A1D2E] max-w-[180px] truncate">{r.Product_Name ?? r.SKU_ID}</td>
                  <td className="px-3 py-2 text-gray-600">{r.Store_ID}</td>
                  <td className="px-3 py-2 text-gray-500">{r.Sub_Category ?? '—'}</td>
                  <td className="px-3 py-2">
                    <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${ACTION_COLORS[r.action] ?? 'bg-gray-100 text-gray-600'}`}>
                      {r.action}
                    </span>
                  </td>
                  <td className="px-3 py-2 font-semibold text-[#1A1D2E]">{fmtMoney(r.financial_impact_usd)}</td>
                  <td className="px-3 py-2">
                    <span className={`font-semibold ${r.WoC < 2 ? 'text-red-600' : r.WoC > 12 ? 'text-amber-600' : 'text-gray-700'}`}>
                      {r.WoC?.toFixed(1)} wk
                    </span>
                  </td>
                  <td className="px-3 py-2">
                    {r.Calc_Growth_Pct !== undefined && (
                      <span className={`font-semibold ${r.Calc_Growth_Pct >= 0 ? 'text-emerald-600' : 'text-red-500'}`}>
                        {r.Calc_Growth_Pct > 0 ? '+' : ''}{r.Calc_Growth_Pct?.toFixed(1)}%
                      </span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
