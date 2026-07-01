import PlotlyChart from '../ui/PlotlyChart'

interface LostRow {
  SKU_ID: string
  Product_Name?: string
  Sub_Category?: string
  Brand?: string
  Lost_Units: number
  Lost_Revenue: number
  Lost_Margin: number
  Affected_Stores: number
}

interface Props { rows: LostRow[] }

const fmtMoney = (n: number) =>
  n >= 1_000_000 ? `$${(n / 1_000_000).toFixed(1)}M`
  : n >= 1_000   ? `$${(n / 1_000).toFixed(0)}K`
  : `$${Math.round(n)}`

export default function LostSalesChart({ rows }: Props) {
  if (!rows?.length) return (
    <div className="flex items-center justify-center h-48 text-gray-400 text-sm">No lost sales data</div>
  )

  const top = [...rows].sort((a, b) => b.Lost_Revenue - a.Lost_Revenue).slice(0, 20)
  const labels = top.map(r => (r.Product_Name ?? r.SKU_ID).slice(0, 28))
  const values = top.map(r => r.Lost_Revenue)
  const colors = top.map(r => r.Lost_Revenue > 100_000 ? '#EF4444' : r.Lost_Revenue > 30_000 ? '#F59E0B' : '#6B7280')

  const traces: any[] = [{
    type: 'bar',
    orientation: 'h',
    x: values,
    y: labels,
    marker: { color: colors },
    text: values.map(fmtMoney),
    textposition: 'outside',
    hovertemplate: '<b>%{y}</b><br>Lost Revenue: $%{x:,.0f}<extra></extra>',
  }]

  const totalLost = rows.reduce((s, r) => s + r.Lost_Revenue, 0)
  const totalUnits = rows.reduce((s, r) => s + r.Lost_Units, 0)

  return (
    <div>
      <div className="flex gap-4 mb-3">
        <div className="text-center">
          <p className="text-[10px] text-gray-400 uppercase tracking-wider">Total Revenue at Risk</p>
          <p className="text-lg font-extrabold text-red-600">{fmtMoney(totalLost)}</p>
        </div>
        <div className="text-center">
          <p className="text-[10px] text-gray-400 uppercase tracking-wider">Lost Units (6 wk)</p>
          <p className="text-lg font-extrabold text-gray-700">{Math.round(totalUnits).toLocaleString()}</p>
        </div>
      </div>
      <PlotlyChart
        traces={traces}
        height={Math.max(240, top.length * 22 + 40)}
        layout={{
          margin: { l: 220, r: 80, t: 8, b: 24 },
          xaxis: { title: { text: 'Lost Revenue ($)', font: { size: 11 } }, tickprefix: '$', tickformat: ',.0f' },
          yaxis: { autorange: 'reversed', tickfont: { size: 11 } },
        }}
      />
    </div>
  )
}
