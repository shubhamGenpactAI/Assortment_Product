import { useState, useEffect } from 'react'
import PlotlyChart from '../components/ui/PlotlyChart'
import {
  fetchDashboardKpis, fetchDashboardRecs, fetchAbc,
  fetchBasketPairs, fetchSalesTrend, fetchStoreRanking,
} from '../api/generalApi'

const COLORS = { green: '#27AE60', orange: '#F2A93B', red: '#E84040', blue: '#2C7BB6', indigo: '#4F46E5' }

function KpiCard({ label, value, sub }: { label: string; value: string | number; sub?: string }) {
  return (
    <div className="bg-white border border-gray-200 rounded-xl px-5 py-4 shadow-sm">
      <p className="text-[10px] font-bold text-gray-400 uppercase tracking-wider mb-1">{label}</p>
      <p className="text-2xl font-extrabold text-[#1A1D2E]">{typeof value === 'number' ? value.toLocaleString() : value}</p>
      {sub && <p className="text-xs text-gray-400 mt-0.5">{sub}</p>}
    </div>
  )
}

function RecCard({ card }: { card: any }) {
  const badgeColors: Record<string, string> = { green: 'bg-emerald-100 text-emerald-800', red: 'bg-red-100 text-red-700', blue: 'bg-blue-100 text-blue-700', gray: 'bg-gray-100 text-gray-600' }
  return (
    <div className="bg-white border border-gray-200 rounded-xl p-3.5 mb-2.5 shadow-sm">
      <p className="text-[12px] font-bold text-[#1A1D2E] mb-1">{card.icon} {card.title}</p>
      <p className="text-[11.5px] text-gray-600 leading-snug">{card.body}</p>
      {card.badge && (
        <span className={`inline-block mt-1.5 text-[10px] font-semibold px-2 py-0.5 rounded-full ${badgeColors[card.badge_type] || badgeColors.gray}`}>
          {card.badge}
        </span>
      )}
      {card.action && <p className="text-[10px] text-[#2C7BB6] font-semibold mt-1.5 cursor-pointer hover:underline">{card.action}</p>}
    </div>
  )
}

export default function DashboardPage() {
  const [kpis, setKpis]       = useState<any>(null)
  const [recs, setRecs]       = useState<any[]>([])
  const [abc, setAbc]         = useState<any>({ bars: [] })
  const [basket, setBasket]   = useState<any[]>([])
  const [trend, setTrend]     = useState<any>({ actuals: [], forecast: [] })
  const [ranking, setRanking] = useState<any[]>([])

  useEffect(() => {
    fetchDashboardKpis().then(setKpis).catch(console.error)
    fetchDashboardRecs().then(setRecs).catch(console.error)
    fetchAbc().then(setAbc).catch(console.error)
    fetchBasketPairs().then(setBasket).catch(console.error)
    fetchSalesTrend().then(setTrend).catch(console.error)
    fetchStoreRanking().then(setRanking).catch(console.error)
  }, [])

  // ABC chart
  const clrMap: Record<string, string> = { A: COLORS.green, B: COLORS.orange, C: COLORS.red }
  const abcTraces = [
    {
      x: abc.bars.map((b: any) => b.ABC_Class), y: abc.bars.map((b: any) => b.Rev_Pct),
      type: 'bar' as const, name: 'Revenue %',
      marker: { color: abc.bars.map((b: any) => clrMap[b.ABC_Class] || COLORS.blue) },
      text: abc.bars.map((b: any) => `${b.Rev_Pct}%`), textposition: 'outside' as const,
    },
    {
      x: abc.bars.map((b: any) => b.ABC_Class), y: abc.bars.map((b: any) => b.Cum_Rev),
      type: 'scatter' as const, mode: 'lines+markers+text' as const, name: 'Cumulative %', yaxis: 'y2',
      line: { color: COLORS.blue, width: 2.5, dash: 'dot' as const },
      text: abc.bars.map((b: any) => `${b.Cum_Rev}%`), textposition: 'top center' as const,
    },
  ]

  // Sales trend traces
  const trendTraces = [
    { x: trend.actuals.map((p: any) => p.week), y: trend.actuals.map((p: any) => p.value),
      type: 'scatter' as const, mode: 'lines+markers' as const, name: 'Actual Sales',
      line: { color: COLORS.orange, width: 2.5 }, marker: { size: 4 } },
    { x: trend.forecast.map((p: any) => p.week), y: trend.forecast.map((p: any) => p.value),
      type: 'scatter' as const, mode: 'lines+markers' as const, name: 'Forecast',
      line: { color: COLORS.blue, width: 2.5, dash: 'dash' as const }, marker: { size: 5, symbol: 'diamond' } },
  ]

  // Store ranking
  const rankTraces = [{
    x: ranking.slice(-7).map((r: any) => r.FC_Total), y: ranking.slice(-7).map((r: any) => r.label),
    type: 'bar' as const, orientation: 'h' as const, name: 'Forecast',
    marker: { color: COLORS.indigo }, text: ranking.slice(-7).map((r: any) => r.FC_Total.toLocaleString()),
    textposition: 'outside' as const,
  }]

  return (
    <div className="px-5 py-5 max-w-[1600px] mx-auto">
      <h2 className="text-2xl font-extrabold text-[#1A1D2E] mb-4">📊 Dashboard</h2>

      {/* KPI strip */}
      <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 mb-5">
        <KpiCard label="Stores"           value={kpis?.stores ?? '—'} />
        <KpiCard label="Active SKUs"      value={kpis?.active_skus ?? '—'} />
        <KpiCard label="6-Week Forecast"  value={kpis ? kpis.forecast_6wk.toLocaleString() : '—'} sub="units" />
        <KpiCard label="Delist Candidates"value={kpis?.delist_candidates ?? '—'} />
        <KpiCard label="Top Basket Lift"  value={kpis ? `${kpis.top_basket_lift}x` : '—'} />
      </div>

      {/* 3-column layout */}
      <div className="grid grid-cols-1 lg:grid-cols-[240px_1fr_280px] gap-4">
        {/* Left: Recommendations */}
        <div>
          <p className="sec-hdr">Manager Recommendations</p>
          {recs.map((c, i) => <RecCard key={i} card={c} />)}
        </div>

        {/* Center: Charts */}
        <div className="flex flex-col gap-4">
          <div className="card">
            <p className="sec-hdr">ABC Analysis (Hair Care)</p>
            <PlotlyChart traces={abcTraces} height={220}
              layout={{ yaxis: { title: { text: 'Revenue %' }, range: [0, 115] },
                        yaxis2: { overlaying: 'y', side: 'right', range: [0, 115], showgrid: false } as any }} />
          </div>
          <div className="card">
            <p className="sec-hdr">Market Basket — Top Pairs</p>
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead><tr className="border-b border-gray-100">
                  <th className="text-left py-2 text-gray-500">Pair</th>
                  <th className="text-right py-2 text-gray-500">Lift</th>
                  <th className="text-right py-2 text-gray-500">Conf</th>
                </tr></thead>
                <tbody>
                  {basket.slice(0, 6).map((b, i) => (
                    <tr key={i} className="border-b border-gray-50 hover:bg-gray-50">
                      <td className="py-1.5 pr-2 text-gray-700">{b.pair}</td>
                      <td className="py-1.5 text-right font-semibold text-[#4F46E5]">{b.lift}</td>
                      <td className="py-1.5 text-right text-gray-500">{(b.confidence * 100).toFixed(0)}%</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
          <div className="card">
            <p className="sec-hdr">Sales Trend &amp; Forecast</p>
            <PlotlyChart traces={trendTraces} height={220}
              layout={{ yaxis: { title: { text: 'Qty Sold' } },
                legend: { orientation: 'h', y: 1.12 } }} />
          </div>
        </div>

        {/* Right: AI Assistant + Store ranking */}
        <div className="flex flex-col gap-4">
          <div className="rounded-2xl p-4 text-white flex flex-col gap-3"
               style={{ background: 'linear-gradient(160deg,#3730A3,#4F46E5)' }}>
            <p className="font-extrabold text-[14px]">AI Category Assistant <span className="text-[9px] bg-white/20 px-1.5 py-0.5 rounded-full ml-1">BETA</span></p>
            <p className="text-[10px] opacity-60">Insights derived from live project data</p>
            <div className="bg-white/10 rounded-lg p-2.5 text-[11px] italic leading-relaxed">
              &ldquo;Navigate to each page using the tabs above to explore SKU performance, assortment recommendations, and delisting risk analysis.&rdquo;
            </div>
          </div>
          <div className="card">
            <p className="sec-hdr">Store Ranking (Forecast)</p>
            <PlotlyChart traces={rankTraces} height={220}
              layout={{ margin: { l: 120, r: 40, t: 10, b: 40 },
                        xaxis: { title: { text: '6-Wk Forecast' } } }} />
          </div>
        </div>
      </div>
    </div>
  )
}
