import { useState, useEffect, useCallback, useMemo } from 'react'
import { Loader2 } from 'lucide-react'
import {
  fetchHubKpis, fetchRiskMatrix, fetchLostSales,
  fetchInventoryProductivity, fetchDelistRationalization,
  fetchExceptionAlerts, fetchCategoryHealth,
} from '../api/decisionHubApi'
import { fetchStores } from '../api/generalApi'
import KpiHeader        from '../components/decision_hub/KpiHeader'
import ExceptionAlerts  from '../components/decision_hub/ExceptionAlerts'
import RiskMatrix       from '../components/decision_hub/RiskMatrix'
import LostSalesChart   from '../components/decision_hub/LostSalesChart'
import InventoryScatter from '../components/decision_hub/InventoryScatter'
import DelistHub        from '../components/decision_hub/DelistHub'
import AICopilot        from '../components/decision_hub/AICopilot'
import WatchdogBanner   from '../components/agents/WatchdogBanner'
import { useFilters }   from '../context/FilterContext'

type Filters = { store_id?: string; sub_cat?: string; cluster?: string }

const CLUSTERS = ['Premium Urban', 'Emerging Growth', 'Affluent Suburban', 'Digital-First Urban', 'Rural Remote']
const SUB_CATS = [
  'Shampoo','Conditioner','Hair Color','Hair Oil','Hair Serum',
  'Hair Mask','Anti-Dandruff Treatment',
]

function SectionCard({ title, children, className = '' }: { title: string; children: React.ReactNode; className?: string }) {
  return (
    <div className={`bg-white rounded-2xl border border-gray-200 shadow-sm p-5 ${className}`}>
      <h2 className="text-[13px] font-bold text-[#1A1D2E] uppercase tracking-wider mb-4">{title}</h2>
      {children}
    </div>
  )
}

function Skeleton({ h = 48 }: { h?: number }) {
  return <div className={`bg-gray-100 animate-pulse rounded-xl`} style={{ height: h }} />
}

export default function DecisionHubPage() {
  const { filters: gf, setFilter, patchFilters } = useFilters()

  const [stores,     setStores]     = useState<string[]>([])
  const [kpis,       setKpis]       = useState<any>(null)
  const [matrix,     setMatrix]     = useState<any[]>([])
  const [lostSales,  setLostSales]  = useState<any[]>([])
  const [invProd,    setInvProd]    = useState<any[]>([])
  const [delist,     setDelist]     = useState<any>(null)
  const [alerts,     setAlerts]     = useState<any[]>([])
  const [health,     setHealth]     = useState<any[]>([])
  const [loading,    setLoading]    = useState(true)

  // Derive the API filter shape from shared context (only DH-relevant fields)
  const filters = useMemo<Filters>(() => ({
    store_id: gf.store_id || undefined,
    sub_cat:  gf.sub_cat  || undefined,
    cluster:  gf.cluster  || undefined,
  }), [gf.store_id, gf.sub_cat, gf.cluster])

  useEffect(() => {
    fetchStores().then(setStores).catch(() => {})
    fetchCategoryHealth().then(setHealth).catch(() => {})
  }, [])

  const reload = useCallback((f: Filters) => {
    setLoading(true)
    Promise.all([
      fetchHubKpis(f).then(setKpis),
      fetchRiskMatrix(f).then(setMatrix),
      fetchLostSales(f).then(setLostSales),
      fetchInventoryProductivity(f).then(setInvProd),
      fetchDelistRationalization(f).then(setDelist),
      fetchExceptionAlerts(f).then(setAlerts),
    ])
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => { reload(filters) }, [filters, reload])

  const set = (key: keyof Filters, val: string) =>
    setFilter(key as 'store_id' | 'sub_cat' | 'cluster', val)

  return (
    <div className="max-w-[1600px] mx-auto px-5 pb-10">
      {/* ── Watchdog Banner ────────────────────────────────────── */}
      <WatchdogBanner />

      {/* ── Filter Bar ─────────────────────────────────────────── */}
      <div className="flex flex-wrap items-center gap-3 py-4">
        <h1 className="text-[18px] font-extrabold text-[#1A1D2E] mr-2">⚡ Category Decision Hub</h1>

        <select
          value={gf.store_id}
          onChange={e => set('store_id', e.target.value)}
          className="border border-gray-200 rounded-lg px-3 py-1.5 text-[12px] bg-white focus:outline-none focus:border-[#4F46E5]"
        >
          <option value="">All Stores</option>
          {stores.map(s => <option key={s} value={s}>{s}</option>)}
        </select>

        <select
          value={gf.sub_cat}
          onChange={e => set('sub_cat', e.target.value)}
          className="border border-gray-200 rounded-lg px-3 py-1.5 text-[12px] bg-white focus:outline-none focus:border-[#4F46E5]"
        >
          <option value="">All Sub-Categories</option>
          {SUB_CATS.map(s => <option key={s} value={s}>{s}</option>)}
        </select>

        <select
          value={gf.cluster}
          onChange={e => set('cluster', e.target.value)}
          className="border border-gray-200 rounded-lg px-3 py-1.5 text-[12px] bg-white focus:outline-none focus:border-[#4F46E5]"
        >
          <option value="">All Clusters</option>
          {CLUSTERS.map(c => <option key={c} value={c}>{c}</option>)}
        </select>

        <button
          onClick={() => patchFilters({ store_id: '', sub_cat: '', cluster: '' })}
          className="text-[11px] text-gray-400 hover:text-gray-700 border border-gray-200 rounded-lg px-3 py-1.5 bg-white"
        >
          ✕ Clear
        </button>

        {loading && <Loader2 size={14} className="animate-spin text-[#4F46E5] ml-1" />}
      </div>

      {/* ── Category Health Strip ─────────────────────────────── */}
      {health.length > 0 && (
        <div className="flex flex-wrap gap-2 mb-4">
          {health.slice(0, 8).map(h => (
            <div key={h.Sub_Category} className="bg-white border border-gray-200 rounded-xl px-3 py-1.5 flex items-center gap-2 shadow-sm">
              <span className="text-[11px] font-semibold text-gray-600">{h.Sub_Category}</span>
              <div className="w-20 h-1.5 bg-gray-100 rounded-full overflow-hidden">
                <div
                  className={`h-full rounded-full ${h.composite >= 70 ? 'bg-emerald-500' : h.composite >= 45 ? 'bg-amber-400' : 'bg-red-400'}`}
                  style={{ width: `${Math.min(100, h.composite)}%` }}
                />
              </div>
              <span className={`text-[11px] font-bold ${h.composite >= 70 ? 'text-emerald-600' : h.composite >= 45 ? 'text-amber-600' : 'text-red-500'}`}>
                {h.composite?.toFixed(0)}
              </span>
            </div>
          ))}
        </div>
      )}

      {/* ── Row 1: KPI Header ─────────────────────────────────── */}
      <div className="mb-4">
        {loading ? <Skeleton h={80} /> : <KpiHeader data={kpis} />}
      </div>

      {/* ── Row 2: AI Copilot + Exception Alerts ─────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-4">
        <SectionCard title="🤖 AI Copilot Recommendations">
          <AICopilot filters={filters} />
        </SectionCard>
        <SectionCard title="🚨 Exception Alerts">
          {loading ? <Skeleton h={380} /> : <ExceptionAlerts alerts={alerts} />}
        </SectionCard>
      </div>

      {/* ── Row 3: Risk Matrix ────────────────────────────────── */}
      <SectionCard title="📊 Forecast Opportunity & Risk Matrix" className="mb-4">
        {loading ? <Skeleton h={220} /> : <RiskMatrix rows={matrix} />}
      </SectionCard>

      {/* ── Row 4: Lost Sales + Inventory Scatter ────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 mb-4">
        <SectionCard title="💸 Lost Sales & Revenue at Risk (Top 20 SKUs)">
          {loading ? <Skeleton h={280} /> : <LostSalesChart rows={lostSales} />}
        </SectionCard>
        <SectionCard title="🔬 Inventory Productivity (GMROI vs Weeks of Cover)">
          {loading ? <Skeleton h={280} /> : <InventoryScatter rows={invProd} />}
        </SectionCard>
      </div>

      {/* ── Row 5: Delist Hub ─────────────────────────────────── */}
      <SectionCard title="🧩 Delist & Rationalization Hub">
        {loading ? <Skeleton h={320} /> : <DelistHub data={delist} />}
      </SectionCard>
    </div>
  )
}
