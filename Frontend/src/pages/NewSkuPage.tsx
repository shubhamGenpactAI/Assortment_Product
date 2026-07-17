import { useState, useEffect, useCallback, useRef } from 'react'
import { AgGridReact } from 'ag-grid-react'
import type { ColDef } from 'ag-grid-community'
import PlotlyChart from '../components/ui/PlotlyChart'
import PageTabs from '../components/ui/PageTabs'
import { fetchIntelligence, uploadNewSkuCsv, clearUploadCache, downloadCsvTemplate } from '../api/newSkuApi'
import { fetchSimilarity } from '../api/generalApi'

// ─────────────────────────────────────────────────────────────────────────────
// Colour palette
// ─────────────────────────────────────────────────────────────────────────────
const C = {
  indigo:   '#4F46E5',
  amber:    '#F2A93B',
  green:    '#22C55E',
  red:      '#EF4444',
  slate:    '#1A1D2E',
  muted:    '#8E93A6',
  bg:       '#F4F6FA',
  card:     '#FFFFFF',
}

// ─────────────────────────────────────────────────────────────────────────────
// Small UI helpers
// ─────────────────────────────────────────────────────────────────────────────
function Spinner() {
  return (
    <div className="flex items-center justify-center h-48">
      <div className="w-8 h-8 border-4 border-indigo-200 border-t-indigo-600 rounded-full animate-spin" />
    </div>
  )
}

function SectionHeader({ icon, title, sub }: { icon: string; title: string; sub?: string }) {
  return (
    <div className="flex items-center gap-2 mb-3">
      <span className="text-xl">{icon}</span>
      <div>
        <p className="font-bold text-[#1A1D2E] text-sm tracking-wide uppercase">{title}</p>
        {sub && <p className="text-[11px] text-gray-400">{sub}</p>}
      </div>
    </div>
  )
}

function Badge({ label, color }: { label: string; color: string }) {
  const styles: Record<string, string> = {
    green:  'bg-green-100 text-green-800 border-green-200',
    amber:  'bg-amber-100 text-amber-800 border-amber-200',
    red:    'bg-red-100   text-red-800   border-red-200',
    indigo: 'bg-indigo-100 text-indigo-800 border-indigo-200',
    gray:   'bg-gray-100  text-gray-600  border-gray-200',
  }
  return (
    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold border ${styles[color] ?? styles.gray}`}>
      {label}
    </span>
  )
}

function KpiCard({ label, value, sub, color = 'indigo' }: { label: string; value: string; sub?: string; color?: string }) {
  const accent: Record<string, string> = {
    indigo: 'border-l-indigo-500',
    amber:  'border-l-amber-400',
    green:  'border-l-green-500',
    red:    'border-l-red-400',
  }
  return (
    <div className={`bg-white rounded-xl p-4 shadow-sm border border-gray-100 border-l-4 ${accent[color] ?? accent.indigo}`}>
      <p className="text-[11px] font-semibold text-gray-400 uppercase tracking-wide">{label}</p>
      <p className="text-2xl font-extrabold text-[#1A1D2E] mt-1">{value}</p>
      {sub && <p className="text-[11px] text-gray-400 mt-0.5">{sub}</p>}
    </div>
  )
}

function CopilotCard({ icon, title, body, accent }: { icon: string; title: string; body: string; accent: string }) {
  const borders: Record<string, string> = {
    indigo: 'border-indigo-200 bg-indigo-50',
    amber:  'border-amber-200  bg-amber-50',
    red:    'border-red-200    bg-red-50',
    green:  'border-green-200  bg-green-50',
  }
  return (
    <div className={`rounded-xl border p-4 ${borders[accent] ?? borders.indigo}`}>
      <div className="flex items-center gap-2 mb-2">
        <span className="text-lg">{icon}</span>
        <p className="font-bold text-[13px] text-[#1A1D2E]">{title}</p>
      </div>
      <p className="text-[12px] text-gray-700 leading-relaxed">{body}</p>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// Decision signal chip
// ─────────────────────────────────────────────────────────────────────────────
function DecisionChip({ signal, confidence }: { signal: string; confidence: string }) {
  const map: Record<string, { color: string; icon: string }> = {
    'Go':              { color: 'green',  icon: '✅' },
    'Conditional Go':  { color: 'amber',  icon: '⚡' },
    'Test':            { color: 'indigo', icon: '🔬' },
    'No-Go':           { color: 'red',    icon: '🚫' },
  }
  const cfg = map[signal] ?? { color: 'gray', icon: '❓' }
  return (
    <div className="flex items-center gap-2">
      <Badge label={`${cfg.icon} ${signal}`} color={cfg.color} />
      <Badge label={`${confidence} Confidence`} color={confidence === 'High' ? 'green' : confidence === 'Medium' ? 'amber' : 'red'} />
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// Scenario simulation panel
// ─────────────────────────────────────────────────────────────────────────────
function ScenarioPanel({ scenarios }: { scenarios: any }) {
  if (!scenarios?.comparison) return null

  const labels = scenarios.comparison.map((s: any) => s.label)
  const revenues = scenarios.comparison.map((s: any) => s.new_revenue)
  const margins  = scenarios.comparison.map((s: any) => s.new_margin)
  const recommended = scenarios.recommended_scenario

  const barColors = labels.map((l: string) =>
    l === recommended ? C.green : l === 'Base Case' ? C.indigo : C.amber
  )

  const traces = [
    { x: labels, y: revenues, type: 'bar' as const, name: 'Revenue ($)',
      marker: { color: barColors }, offsetgroup: 1 },
    { x: labels, y: margins,  type: 'bar' as const, name: 'Margin ($)',
      marker: { color: barColors.map(() => '#818CF8') }, offsetgroup: 2 },
  ]

  return (
    <div className="card">
      <SectionHeader icon="🎮" title="Scenario Simulation" sub="6 pre-built scenarios — price, promo, pack-size" />
      {scenarios.recommended_scenario && (
        <div className="mb-3 p-2.5 rounded-lg bg-green-50 border border-green-200 text-[12px] text-green-800">
          <span className="font-bold">Optimal Scenario: {scenarios.recommended_scenario}</span>
          {' — '}{scenarios.recommendation_reason}
        </div>
      )}
      <PlotlyChart
        traces={traces}
        height={280}
        layout={{
          barmode:  'group',
          margin:   { l: 60, r: 20, t: 10, b: 80 },
          xaxis:    { tickangle: -25, tickfont: { size: 10 } },
          yaxis:    { title: { text: '$' } },
          legend:   { orientation: 'h', y: -0.3 },
        }}
      />
      <div className="mt-3 overflow-x-auto">
        <table className="w-full text-[11px]">
          <thead>
            <tr className="border-b border-gray-100">
              {['Scenario', 'Units', 'Revenue', 'Margin', 'Rev Δ%', 'Margin Δ%', 'Demand Δ%'].map(h => (
                <th key={h} className="text-left py-1.5 px-2 font-semibold text-gray-500 uppercase tracking-wide">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {scenarios.comparison.map((s: any) => (
              <tr key={s.label} className={`border-b border-gray-50 ${s.label === recommended ? 'bg-green-50 font-bold' : ''}`}>
                <td className="py-1.5 px-2">{s.label === recommended ? '⭐ ' : ''}{s.label}</td>
                <td className="py-1.5 px-2 text-right">{s.new_units?.toLocaleString()}</td>
                <td className="py-1.5 px-2 text-right">${s.new_revenue?.toLocaleString()}</td>
                <td className="py-1.5 px-2 text-right">${s.new_margin?.toLocaleString()}</td>
                <td className={`py-1.5 px-2 text-right ${s.revenue_delta_pct > 0 ? 'text-green-600' : s.revenue_delta_pct < 0 ? 'text-red-500' : ''}`}>
                  {s.revenue_delta_pct > 0 ? '+' : ''}{s.revenue_delta_pct?.toFixed(1)}%
                </td>
                <td className={`py-1.5 px-2 text-right ${s.margin_delta_pct > 0 ? 'text-green-600' : s.margin_delta_pct < 0 ? 'text-red-500' : ''}`}>
                  {s.margin_delta_pct > 0 ? '+' : ''}{s.margin_delta_pct?.toFixed(1)}%
                </td>
                <td className={`py-1.5 px-2 text-right ${s.demand_delta_pct > 0 ? 'text-green-600' : s.demand_delta_pct < 0 ? 'text-red-500' : ''}`}>
                  {s.demand_delta_pct > 0 ? '+' : ''}{s.demand_delta_pct?.toFixed(1)}%
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// Cannibalization panel
// ─────────────────────────────────────────────────────────────────────────────
function CannibalizationPanel({ data }: { data: any }) {
  if (!data || data.error) return null

  const pieData = [{
    values: [data.cannibalized_units, data.incremental_units],
    labels: ['Cannibalized', 'Incremental'],
    type:   'pie' as const,
    hole:   0.55,
    marker: { colors: [C.red, C.green] },
    textinfo: 'label+percent' as const,
  }]

  const impactCols: ColDef[] = [
    { field: 'product_name',     flex: 1,   headerName: 'Impacted Product' },
    { field: 'similarity_score', width: 90, headerName: 'Similarity', type: 'numericColumn',
      valueFormatter: p => p.value?.toFixed(3), cellStyle: { color: C.indigo, fontWeight: 700 } },
    { field: 'cannibalization_coef', width: 95, headerName: 'Cannib. Coef',
      type: 'numericColumn', valueFormatter: p => p.value?.toFixed(3) },
    { field: 'estimated_transfer_units', width: 110, headerName: 'Transfer Units',
      type: 'numericColumn', valueFormatter: p => p.value?.toFixed(0),
      cellStyle: { color: C.red } },
  ]

  const riskColor = { High: 'red', Medium: 'amber', Low: 'green' }[data.risk_level as string] ?? 'gray'

  return (
    <div className="card">
      <SectionHeader icon="⚠️" title="Cannibalization Analysis" sub="Demand transfer from existing SKUs" />
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
        <KpiCard label="Cannibalization Rate" value={`${(data.cannibalization_rate * 100).toFixed(0)}%`}
          sub={`${data.cannibalized_units?.toLocaleString()} units`} color="red" />
        <KpiCard label="Incrementality Rate"  value={`${(data.incrementality_rate * 100).toFixed(0)}%`}
          sub={`${data.incremental_units?.toLocaleString()} units`} color="green" />
        <KpiCard label="Risk Level" value={data.risk_level}
          sub={`Score: ${(data.cannibalization_score * 100).toFixed(0)}/100`}
          color={riskColor as any} />
        <KpiCard label="Category Net Effect" value={data.category_net_effect}
          sub={`${data.n_competing_skus} competing SKUs`} color="indigo" />
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div>
          <p className="text-[11px] font-semibold text-gray-400 uppercase mb-2">Demand split</p>
          <PlotlyChart traces={pieData} height={220}
            layout={{ margin: { l: 10, r: 10, t: 10, b: 10 }, showlegend: true }} />
        </div>
        <div>
          <p className="text-[11px] font-semibold text-gray-400 uppercase mb-2">Top impacted SKUs</p>
          <div className="ag-theme-alpine" style={{ height: 220 }}>
            <AgGridReact rowData={data.impacted_skus?.slice(0, 6) ?? []}
              columnDefs={impactCols}
              defaultColDef={{ resizable: true, sortable: true }}
              rowHeight={32} headerHeight={36} />
          </div>
        </div>
      </div>
      {data.summary_nl && (
        <p className="mt-3 text-[11.5px] text-gray-600 bg-gray-50 rounded-lg p-3 border border-gray-100">
          {data.summary_nl}
        </p>
      )}
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// Store recommendation panel
// ─────────────────────────────────────────────────────────────────────────────
function StoreRecommendationPanel({ data }: { data: any }) {
  if (!data || data.error) return null

  const storeCols: ColDef[] = [
    { field: 'store_id',          width: 80,  headerName: 'Store' },
    { field: 'cluster_label',     flex: 1,    headerName: 'Cluster' },
    { field: 'composite_score',   width: 90,  headerName: 'Score',
      type: 'numericColumn', valueFormatter: p => p.value?.toFixed(3),
      cellStyle: (p: any) => ({ color: p.value >= 0.7 ? C.green : p.value >= 0.45 ? C.amber : C.red, fontWeight: 700 }) },
    { field: 'velocity_tier',     width: 85,  headerName: 'Velocity',
      cellStyle: (p: any) => ({ color: p.value === 'High' ? C.green : p.value === 'Medium' ? C.amber : C.red }) },
    { field: 'rollout_phase',     flex: 1,    headerName: 'Launch Phase' },
  ]

  // Cluster bar chart
  const clusterData = data.cluster_summary ?? []
  const clusterTraces = [{
    x: clusterData.map((c: any) => c.avg_score),
    y: clusterData.map((c: any) => c.cluster_label),
    type: 'bar' as const, orientation: 'h' as const,
    marker: { color: clusterData.map((c: any) => c.recommendation === 'Launch' ? C.green : C.muted) },
    text: clusterData.map((c: any) => `${(c.avg_score * 100).toFixed(0)}/100`),
    textposition: 'outside' as const,
  }]

  return (
    <div className="card">
      <SectionHeader icon="🏪" title="Store Launch Recommendation" sub="Scored by analog velocity, demographic fit, cluster affinity" />
      <div className="grid grid-cols-2 md:grid-cols-3 gap-3 mb-4">
        <KpiCard label="Recommended Stores" value={String(data.n_recommended)}
          sub={`of ${data.n_total} total`} color="green" />
        <KpiCard label="Skip Stores" value={String(data.skip_stores?.length ?? 0)}
          sub="Below threshold" color="red" />
        <KpiCard label="Top Cluster" value={data.cluster_summary?.[0]?.cluster_label ?? '—'}
          sub={`Score: ${((data.cluster_summary?.[0]?.avg_score ?? 0) * 100).toFixed(0)}/100`} color="indigo" />
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div>
          <p className="text-[11px] font-semibold text-gray-400 uppercase mb-2">Cluster fit scores</p>
          <PlotlyChart traces={clusterTraces} height={200}
            layout={{ margin: { l: 160, r: 60, t: 10, b: 30 }, xaxis: { range: [0, 1.1] } }} />
        </div>
        <div>
          <p className="text-[11px] font-semibold text-gray-400 uppercase mb-2">All stores ranked</p>
          <div className="ag-theme-alpine" style={{ height: 200 }}>
            <AgGridReact rowData={data.stores ?? []}
              columnDefs={storeCols}
              defaultColDef={{ resizable: true, sortable: true }}
              rowHeight={32} headerHeight={36} />
          </div>
        </div>
      </div>
      {data.launch_summary && (
        <p className="mt-3 text-[11.5px] text-gray-600 bg-gray-50 rounded-lg p-3 border border-gray-100">
          {data.launch_summary}
        </p>
      )}
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// Hierarchical forecast panel
// ─────────────────────────────────────────────────────────────────────────────
function ForecastPanel({ data }: { data: any }) {
  const [tab, setTab] = useState<'enterprise' | 'cluster' | 'store'>('enterprise')
  if (!data || data.error) return null

  const ent   = data.enterprise ?? []
  const store = data.store      ?? []

  // Enterprise weekly chart
  const entTraces = [
    { x: ent.map((r: any) => r.Year_WK), y: ent.map((r: any) => r.Units),
      type: 'scatter' as const, mode: 'lines+markers' as const, name: 'Units',
      line: { color: C.indigo, width: 2.5 }, fill: 'tozeroy' as const, fillcolor: 'rgba(79,70,229,0.07)' },
    { x: ent.map((r: any) => r.Year_WK), y: ent.map((r: any) => r.Units_Upper),
      type: 'scatter' as const, mode: 'lines' as const, name: 'Upper', line: { color: C.indigo, width: 1, dash: 'dot' as const }, showlegend: false },
    { x: ent.map((r: any) => r.Year_WK), y: ent.map((r: any) => r.Units_Lower),
      type: 'scatter' as const, mode: 'lines' as const, name: 'Lower', fill: 'tonexty' as const,
      fillcolor: 'rgba(79,70,229,0.06)', line: { color: C.indigo, width: 1, dash: 'dot' as const }, showlegend: false },
  ]

  // Revenue weekly chart
  const revTraces = [
    { x: ent.map((r: any) => r.Year_WK), y: ent.map((r: any) => r.Revenue),
      type: 'bar' as const, name: 'Revenue', marker: { color: C.amber } },
  ]

  const summary = data.summary ?? {}
  const ent_total = summary.enterprise_total ?? {}
  const avgConf   = data.avg_confidence ?? 0.5

  const storeColDefs: ColDef[] = [
    { field: 'Store_ID',      width: 80,  headerName: 'Store' },
    { field: 'Cluster_Label', flex: 1,    headerName: 'Cluster' },
    { field: 'Units',         width: 90,  headerName: 'Units', type: 'numericColumn',
      valueFormatter: p => p.value?.toFixed(0) },
    { field: 'Revenue',       width: 100, headerName: 'Revenue ($)', type: 'numericColumn',
      valueFormatter: p => `$${p.value?.toFixed(0)}` },
    { field: 'Margin',        width: 95,  headerName: 'Margin ($)',  type: 'numericColumn',
      valueFormatter: p => `$${p.value?.toFixed(0)}`,
      cellStyle: { color: C.green } },
    { field: 'confidence',    width: 90,  headerName: 'Confidence', type: 'numericColumn',
      valueFormatter: p => `${(p.value * 100)?.toFixed(0)}%` },
  ]

  return (
    <div className="card">
      <SectionHeader icon="📈" title="Hierarchical Demand Forecast" sub="Enterprise → Cluster → Store" />
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
        <KpiCard label="Total Units"   value={(ent_total.Units ?? 0).toLocaleString(undefined, { maximumFractionDigits: 0 })}
          sub={`${summary.week_count ?? 6}-week forecast`} color="indigo" />
        <KpiCard label="Revenue"       value={`$${(ent_total.Revenue ?? 0).toLocaleString(undefined, { maximumFractionDigits: 0 })}`}
          sub="Total forecast revenue" color="amber" />
        <KpiCard label="Margin"        value={`$${(ent_total.Margin ?? 0).toLocaleString(undefined, { maximumFractionDigits: 0 })}`}
          sub="Total forecast margin" color="green" />
        <KpiCard label="Avg Confidence" value={`${(avgConf * 100).toFixed(0)}%`}
          sub={data.sparse_stores?.length ? `${data.sparse_stores.length} sparse stores` : 'Good analog coverage'}
          color={avgConf >= 0.65 ? 'green' : avgConf >= 0.45 ? 'amber' : 'red'} />
      </div>

      {/* Tab switcher */}
      <div className="flex gap-2 mb-3 border-b border-gray-100 pb-2">
        {(['enterprise', 'cluster', 'store'] as const).map(t => (
          <button key={t} onClick={() => setTab(t)}
            className={`px-3 py-1.5 rounded-full text-[11px] font-semibold transition-all
              ${tab === t ? 'bg-indigo-600 text-white' : 'text-gray-500 hover:bg-gray-100'}`}>
            {t.charAt(0).toUpperCase() + t.slice(1)}
          </button>
        ))}
      </div>

      {tab === 'enterprise' && (
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
          <div>
            <p className="text-[11px] font-semibold text-gray-400 uppercase mb-1">Units forecast (with confidence band)</p>
            <PlotlyChart traces={entTraces} height={220}
              layout={{ margin: { l: 50, r: 20, t: 10, b: 40 }, yaxis: { title: { text: 'Units' } } }} />
          </div>
          <div>
            <p className="text-[11px] font-semibold text-gray-400 uppercase mb-1">Weekly revenue</p>
            <PlotlyChart traces={revTraces} height={220}
              layout={{ margin: { l: 60, r: 20, t: 10, b: 40 }, yaxis: { title: { text: '$' } } }} />
          </div>
        </div>
      )}

      {tab === 'cluster' && (
        <div>
          {Object.entries(summary.by_cluster ?? {}).length ? (
            <PlotlyChart
              traces={[{
                x: Object.keys(summary.by_cluster ?? {}),
                y: Object.values(summary.by_cluster ?? {}).map((v: any) => v.Units),
                type: 'bar' as const,
                marker: { color: C.indigo },
                text: Object.values(summary.by_cluster ?? {}).map((v: any) => `$${v.Revenue?.toFixed(0)}`),
                textposition: 'outside' as const,
              }]}
              height={260}
              layout={{ margin: { l: 50, r: 20, t: 20, b: 80 }, yaxis: { title: { text: 'Units' } } }}
            />
          ) : <p className="text-sm text-gray-400 p-4">No cluster data available.</p>}
        </div>
      )}

      {tab === 'store' && (
        <div className="ag-theme-alpine" style={{ height: 260 }}>
          <AgGridReact
            rowData={store.slice(0, 50)}
            columnDefs={storeColDefs}
            defaultColDef={{ resizable: true, sortable: true }}
            rowHeight={32} headerHeight={36}
          />
        </div>
      )}
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// Whitespace panel
// ─────────────────────────────────────────────────────────────────────────────
function WhitespacePanel({ data }: { data: any }) {
  if (!data || data.error || !data.whitespace_gaps?.length) return null
  const top = data.whitespace_gaps.slice(0, 8)

  const traces = [{
    x: top.map((g: any) => g.opportunity_score * 100),
    y: top.map((g: any) => g.gap_label?.length > 40 ? g.gap_label.slice(0, 40) + '…' : g.gap_label),
    type: 'bar' as const, orientation: 'h' as const,
    marker: { color: top.map((g: any) => {
      const s = g.opportunity_score
      return s >= 0.65 ? C.green : s >= 0.40 ? C.amber : C.muted
    })},
    text: top.map((g: any) => `${(g.opportunity_score * 100).toFixed(0)}`),
    textposition: 'outside' as const,
  }]

  return (
    <div className="card">
      <SectionHeader icon="🔍" title="Assortment White Space" sub="Uncovered attribute combinations ranked by opportunity" />
      {data.top_opportunity_nl && (
        <div className="mb-3 p-2.5 rounded-lg bg-green-50 border border-green-200 text-[12px] text-green-800">
          {data.top_opportunity_nl}
        </div>
      )}
      <PlotlyChart traces={traces} height={260}
        layout={{
          margin: { l: 260, r: 60, t: 10, b: 40 },
          xaxis:  { title: { text: 'Opportunity Score (0–100)' }, range: [0, 115] },
        }} />
      <p className="text-[11px] text-gray-400 mt-2">{data.summary}</p>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// Attribute contribution donut
// ─────────────────────────────────────────────────────────────────────────────
function AttributeContribPanel({ data }: { data: any }) {
  if (!data?.ranked_detail?.length) return null
  const det = data.ranked_detail
  const traces = [{
    values: det.map((d: any) => d.contribution_pct),
    labels: det.map((d: any) => d.group),
    type: 'pie' as const, hole: 0.5,
    marker: { colors: [C.indigo, '#818CF8', C.amber, '#FCD34D'] },
    textinfo: 'label+percent' as const,
  }]
  return (
    <div className="card">
      <SectionHeader icon="🧩" title="Similarity Drivers" sub="Which attribute groups drive the match" />
      <PlotlyChart traces={traces} height={200}
        layout={{ margin: { l: 10, r: 10, t: 10, b: 10 }, showlegend: true }} />
      {data.summary && (
        <p className="text-[11.5px] text-gray-600 mt-2">{data.summary}</p>
      )}
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// Analog table + similarity chart
// ─────────────────────────────────────────────────────────────────────────────
function AnalogPanel({ similarity, explainability }: { similarity: any; explainability: any }) {
  const analogs = similarity?.top_analogs ?? []

  const barTraces = [{
    x: analogs.map((r: any) => r.similarity_score),
    y: analogs.map((r: any) => (r.product_name || r.sku_id)?.slice(0, 30)),
    type: 'bar' as const, orientation: 'h' as const, name: 'Similarity',
    marker: { color: analogs.map((_: any, i: number) => i === 0 ? C.indigo : '#818CF8') },
    text: analogs.map((r: any) => r.similarity_score?.toFixed(3)),
    textposition: 'outside' as const,
  }]

  const simExpls = explainability?.similarity_explanations ?? []
  const diffs    = explainability?.difference_explanations  ?? []
  const contrib  = explainability?.attribute_contributions   ?? {}

  const simCols: ColDef[] = [
    { field: 'rank',             width: 55,  headerName: '#' },
    { field: 'product_name',     flex: 1,    headerName: 'Product' },
    { field: 'brand',            width: 100, headerName: 'Brand' },
    { field: 'sub_category',     width: 110, headerName: 'Sub-Cat' },
    { field: 'similarity_score', width: 100, headerName: 'Overall',
      type: 'numericColumn', cellStyle: { color: C.indigo, fontWeight: 700 },
      valueFormatter: p => p.value?.toFixed(3) },
    { field: 'hierarchy',   width: 90, headerName: 'Hierarchy',  type: 'numericColumn', valueFormatter: p => p.value?.toFixed(3) },
    { field: 'functional',  width: 90, headerName: 'Functional', type: 'numericColumn', valueFormatter: p => p.value?.toFixed(3) },
    { field: 'ingredient',  width: 90, headerName: 'Ingredient', type: 'numericColumn', valueFormatter: p => p.value?.toFixed(3) },
    { field: 'commercial',  width: 90, headerName: 'Commercial', type: 'numericColumn', valueFormatter: p => p.value?.toFixed(3) },
  ]

  return (
    <div className="card">
      <SectionHeader icon="🔗" title="Analog SKU Matching" sub="Top similar existing SKUs driving the demand forecast" />
      <div className="ag-theme-alpine mb-4" style={{ height: 220 }}>
        <AgGridReact rowData={analogs} columnDefs={simCols}
          defaultColDef={{ resizable: true, sortable: true }}
          rowHeight={34} headerHeight={38} />
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div>
          <p className="text-[11px] font-semibold text-gray-400 uppercase mb-2">Similarity scores</p>
          <PlotlyChart traces={barTraces} height={200}
            layout={{ margin: { l: 190, r: 60, t: 10, b: 30 }, xaxis: { range: [0, 1.15] } }} />
        </div>
        <AttributeContribPanel data={contrib} />
      </div>

      {/* Explainability bullets */}
      {simExpls.length > 0 && (
        <div className="mt-4 grid grid-cols-1 lg:grid-cols-2 gap-4">
          <div>
            <p className="text-[11px] font-semibold text-gray-400 uppercase mb-2">Why it matches (top analog)</p>
            <ul className="text-[12px] space-y-1">
              {(simExpls[0]?.reasons ?? []).map((r: string, i: number) => (
                <li key={i} className="flex items-start gap-1.5">
                  <span className="text-green-500 mt-0.5">✓</span> {r}
                </li>
              ))}
            </ul>
          </div>
          {diffs.length > 0 && (
            <div>
              <p className="text-[11px] font-semibold text-gray-400 uppercase mb-2">How it differs</p>
              <ul className="text-[12px] space-y-1">
                {(diffs[0]?.differences ?? []).map((d: string, i: number) => (
                  <li key={i} className="flex items-start gap-1.5">
                    <span className="text-amber-500 mt-0.5">△</span> {d}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// Risk panel
// ─────────────────────────────────────────────────────────────────────────────
function RiskPanel({ data }: { data: any }) {
  if (!data?.risks?.length) return null
  const sevColor: Record<string, string> = { High: 'red', Medium: 'amber', Low: 'green' }
  return (
    <div className="card">
      <SectionHeader icon="🚨" title="Risk Assessment" sub="Ranked by severity" />
      <div className="space-y-2">
        {data.risks.map((r: any, i: number) => (
          <div key={i} className="flex items-start gap-3 p-2.5 rounded-lg bg-gray-50 border border-gray-100">
            <Badge label={r.severity} color={sevColor[r.severity] ?? 'gray'} />
            <div>
              <p className="text-[12px] font-semibold text-[#1A1D2E]">{r.factor}</p>
              {r.detail && <p className="text-[11px] text-gray-500 mt-0.5">{r.detail}</p>}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// CSV Upload Panel
// ─────────────────────────────────────────────────────────────────────────────
const EXPECTED_COLS = [
  'SKU_ID', 'Product_Name', 'Brand', 'Sub_Category', 'Segment',
  'Attribute_Claim', 'Price_Band', 'List_Price_USD', 'Unit_Cost_USD',
  'Pack_Size_ml', 'Organic_Flag', 'Sulphate_Free_Flag', 'Paraben_Free_Flag',
  'Hair_Fall_Flag', 'Dandruff_Flag', 'Color_Protection_Flag',
  'Ingredient_1', 'Ingredient_2', 'Ingredient_3', 'Ingredient_4',
]
const REQUIRED_COLS_LABEL = ['SKU_ID (or Product_Name)', 'Sub_Category', 'List_Price_USD']

function UploadPanel({
  onUploaded,
  uploadedCount,
  onClearCache,
}: {
  onUploaded: (skuIds: string[]) => void
  uploadedCount: number
  onClearCache: () => void
}) {
  const [dragging,   setDragging]   = useState(false)
  const [uploading,  setUploading]  = useState(false)
  const [result,     setResult]     = useState<any>(null)
  const [uploadErr,  setUploadErr]  = useState('')
  const fileRef = useRef<HTMLInputElement>(null)

  const handleFile = useCallback((file: File) => {
    if (!file) return
    setUploading(true)
    setUploadErr('')
    setResult(null)
    uploadNewSkuCsv(file)
      .then((res: any) => {
        setResult(res)
        if (res.uploaded_sku_ids?.length) {
          onUploaded(res.uploaded_sku_ids)
        }
        if (res.status === 'error') {
          setUploadErr(res.errors?.join('; ') ?? 'Upload failed.')
        }
      })
      .catch((e: any) => setUploadErr(e?.response?.data?.detail ?? e?.message ?? 'Upload error.'))
      .finally(() => setUploading(false))
  }, [onUploaded])

  const onDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault(); setDragging(false)
    const f = e.dataTransfer.files?.[0]
    if (f) handleFile(f)
  }, [handleFile])

  const onInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const f = e.target.files?.[0]
    if (f) handleFile(f)
    e.target.value = ''
  }

  return (
    <div className="bg-white border border-gray-200 rounded-xl shadow-sm p-4">
      {/* Header — always visible, no collapse (tab itself gates visibility) */}
      <div className="flex items-center gap-3 mb-4">
        <span className="text-lg">📁</span>
        <div className="flex-1">
          <span className="font-semibold text-[13px] text-[#1A1D2E]">Upload New SKUs via CSV</span>
          <span className="text-[11px] text-gray-400 ml-2">
            Upload a list of new SKUs to analyse — similarity is computed on-the-fly
          </span>
        </div>
        {uploadedCount > 0 && (
          <span className="bg-green-100 text-green-700 text-[11px] font-bold px-2.5 py-0.5 rounded-full border border-green-200">
            {uploadedCount} SKU{uploadedCount > 1 ? 's' : ''} loaded
          </span>
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-[360px_1fr] gap-4">
        {/* Left column: instructions + drop zone */}
        <div>
          <div className="mb-3 p-3 bg-indigo-50 border border-indigo-100 rounded-lg text-[11.5px] text-indigo-700">
            <div>
              <span className="font-bold">Required columns:</span> {REQUIRED_COLS_LABEL.join(', ')}.{' '}
              <span className="font-bold">Recommended:</span>{' '}
              Sub_Category, Brand, Price_Band, Ingredient_1–4, functional flags (Organic_Flag etc.).
              CSV or XLSX accepted. First row = headers.
            </div>
            <details className="mt-2">
              <summary className="text-[11px] text-indigo-500 cursor-pointer hover:text-indigo-700 select-none">
                View all expected column names ▾
              </summary>
              <div className="mt-2 flex flex-wrap gap-1.5">
                {EXPECTED_COLS.map(c => (
                  <code key={c} className="text-[10px] bg-white text-gray-600 px-1.5 py-0.5 rounded border border-indigo-100">{c}</code>
                ))}
              </div>
            </details>
            <button
              onClick={downloadCsvTemplate}
              className="mt-3 text-[11px] font-semibold text-indigo-600 bg-white border border-indigo-200 px-3 py-1.5 rounded-lg hover:bg-indigo-50 transition-colors"
            >
              ⬇ Download Template CSV
            </button>
          </div>

          {/* Drop zone */}
          <div
            onDragOver={e => { e.preventDefault(); setDragging(true) }}
            onDragLeave={() => setDragging(false)}
            onDrop={onDrop}
            onClick={() => fileRef.current?.click()}
            className={`border-2 border-dashed rounded-xl p-6 text-center cursor-pointer transition-all duration-150
              ${dragging ? 'border-indigo-400 bg-indigo-50' : 'border-gray-200 hover:border-indigo-300 hover:bg-gray-50'}`}
          >
            <input ref={fileRef} type="file" accept=".csv,.xlsx,.xls" className="hidden" onChange={onInputChange} />
            {uploading ? (
              <div className="flex flex-col items-center gap-2">
                <div className="w-8 h-8 border-4 border-indigo-200 border-t-indigo-600 rounded-full animate-spin" />
                <p className="text-[12px] text-indigo-600 font-medium">Computing similarity scores…</p>
              </div>
            ) : (
              <div className="flex flex-col items-center gap-1.5">
                <span className="text-3xl">📤</span>
                <p className="text-[13px] font-semibold text-[#1A1D2E]">Drop CSV / XLSX here or click to browse</p>
                <p className="text-[11px] text-gray-400">Similarity scores computed instantly for each row</p>
              </div>
            )}
          </div>

          {uploadErr && (
            <div className="mt-2 p-2.5 bg-red-50 border border-red-200 rounded-lg text-[12px] text-red-700">
              {uploadErr}
            </div>
          )}
        </div>

        {/* Right column: processed results */}
        <div>
          {result && !uploadErr ? (
            <div className="space-y-2">
              {/* Summary bar */}
              <div className={`flex items-center gap-3 p-3 rounded-lg border text-[12px] font-medium
                ${result.status === 'ok'      ? 'bg-green-50 border-green-200 text-green-800' :
                  result.status === 'partial' ? 'bg-amber-50 border-amber-200 text-amber-800' :
                                                'bg-red-50 border-red-200 text-red-700'}`}>
                <span>{result.status === 'ok' ? '✅' : result.status === 'partial' ? '⚡' : '❌'}</span>
                <span>
                  <b>{result.uploaded_sku_ids?.length ?? 0}</b> of <b>{result.total_rows}</b> SKUs
                  processed from <b>{result.filename}</b>
                  {result.status === 'partial' && ` — ${result.errors?.length} error(s)`}
                </span>
              </div>

              {/* Column warnings */}
              {result.column_report?.missing_important?.length > 0 && (
                <div className="p-2.5 bg-amber-50 border border-amber-100 rounded-lg text-[11.5px] text-amber-700">
                  <span className="font-bold">Missing recommended columns:</span>{' '}
                  {result.column_report.missing_important.join(', ')}.
                  {' '}Similarity scoring will use defaults for these fields.
                </div>
              )}

              {/* Per-SKU results table */}
              <div className="overflow-x-auto rounded-lg border border-gray-100">
                <table className="w-full text-[11px]">
                  <thead>
                    <tr className="bg-gray-50 border-b border-gray-100">
                      <th className="text-left py-2 px-3 font-semibold text-gray-500">SKU ID</th>
                      <th className="text-left py-2 px-3 font-semibold text-gray-500">Product Name</th>
                      <th className="text-left py-2 px-3 font-semibold text-gray-500">Status</th>
                      <th className="text-left py-2 px-3 font-semibold text-gray-500">Best Analog Match</th>
                      <th className="text-right py-2 px-3 font-semibold text-gray-500">Top Score</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(result.processed_skus ?? []).map((s: any) => (
                      <tr key={s.sku_id} className="border-b border-gray-50 hover:bg-gray-50">
                        <td className="py-2 px-3 font-mono text-indigo-700">{s.sku_id}</td>
                        <td className="py-2 px-3 text-gray-700">{s.product_name}</td>
                        <td className="py-2 px-3">
                          {s.status === 'ok'
                            ? <span className="text-green-600 font-semibold">✓ Ready</span>
                            : <span className="text-red-500 font-semibold">✗ Error</span>}
                          {s.warnings?.length > 0 && (
                            <span className="text-amber-500 ml-1">⚠</span>
                          )}
                        </td>
                        <td className="py-2 px-3 text-gray-600">{s.best_analog || '—'}</td>
                        <td className="py-2 px-3 text-right font-bold text-indigo-600">
                          {s.best_score ? (s.best_score * 100).toFixed(1) + '%' : '—'}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* CTA */}
              {result.uploaded_sku_ids?.length > 0 && (
                <p className="text-[11.5px] text-green-700 bg-green-50 px-3 py-2 rounded-lg border border-green-100">
                  ✅ Select any uploaded SKU from the dropdown above to run the full intelligence analysis.
                </p>
              )}
            </div>
          ) : (
            <div className="h-full flex items-center justify-center text-center text-[12px] text-gray-400 border border-dashed border-gray-200 rounded-xl py-12">
              Upload a CSV/XLSX to see processed SKU results here.
            </div>
          )}
        </div>
      </div>

      {/* Clear cache */}
      {uploadedCount > 0 && (
        <div className="mt-3 flex justify-end">
          <button
            onClick={onClearCache}
            className="text-[11px] text-red-400 hover:text-red-600 underline"
          >
            Clear upload cache ({uploadedCount} SKU{uploadedCount > 1 ? 's' : ''})
          </button>
        </div>
      )}
    </div>
  )
}

// ─────────────────────────────────────────────────────────────────────────────
// Main page
// ─────────────────────────────────────────────────────────────────────────────
export default function NewSkuPage() {
  const [skuList,      setSkuList]      = useState<string[]>([])
  const [uploadedSkus, setUploadedSkus] = useState<string[]>([])
  const [selSku,       setSelSku]       = useState('')
  const [intel,        setIntel]        = useState<any>(null)
  const [loadingList,  setLoadingList]  = useState(true)
  const [loading,      setLoading]      = useState(false)
  const [error,        setError]        = useState('')
  const [tab,          setTab]          = useState<'upload' | 'summary'>('upload')

  // Merged SKU list: uploaded SKUs first, then CSV SKUs
  const allSkus = [...uploadedSkus, ...skuList.filter(s => !uploadedSkus.includes(s))]

  // Load base SKU list on mount
  useEffect(() => {
    fetchSimilarity()
      .then(d => {
        const skus: string[] = d.new_skus ?? []
        setSkuList(skus)
        if (skus.length && !selSku) setSelSku(skus[0])
      })
      .catch(() => {
        // No existing similarity output yet — that's fine if user will upload
      })
      .finally(() => setLoadingList(false))
  }, []) // eslint-disable-line

  // When new SKUs are uploaded, add them to the list and select the first
  const handleUploaded = useCallback((newIds: string[]) => {
    setUploadedSkus(prev => {
      const merged = [...newIds, ...prev.filter(id => !newIds.includes(id))]
      return merged
    })
    if (newIds.length) setSelSku(newIds[0])
  }, [])

  const handleClearCache = useCallback(() => {
    clearUploadCache().then(() => {
      setUploadedSkus([])
      setIntel(null)
      if (skuList.length) setSelSku(skuList[0])
    }).catch(console.error)
  }, [skuList])

  // Run intelligence when SKU selected
  const runIntelligence = useCallback((skuId: string) => {
    if (!skuId) return
    setLoading(true)
    setError('')
    fetchIntelligence(skuId)
      .then(setIntel)
      .catch(e => setError(`Intelligence API error: ${e?.message ?? e}`))
      .finally(() => setLoading(false))
  }, [])

  useEffect(() => {
    if (selSku) runIntelligence(selSku)
  }, [selSku, runIntelligence])

  // Derived sub-objects
  const copilot      = intel?.copilot               ?? null
  const similarity   = intel?.similarity             ?? null
  const forecast     = intel?.hierarchical_forecast  ?? null
  const cannib       = intel?.cannibalization        ?? null
  const storeRec     = intel?.store_recommendation   ?? null
  const scenarios    = intel?.scenarios              ?? null
  const explainability = intel?.explainability       ?? null
  const whitespace   = intel?.whitespace             ?? null
  const risks        = explainability?.risk_explanation ?? null
  const forecastExpl = explainability?.forecast_explanation ?? null

  return (
    <div className="px-5 py-5 max-w-[1600px] mx-auto">
      {/* ── Header ── */}
      <div className="flex items-center justify-between mb-4 flex-wrap gap-3">
        <div>
          <h2 className="text-2xl font-extrabold text-[#1A1D2E]">🧠 New SKU Intelligence Hub</h2>
          <p className="text-[12px] text-gray-400 mt-0.5">
            AI-powered launch decision support — similarity, forecast, cannibalization, store recommendation
          </p>
        </div>
        {copilot && (
          <DecisionChip signal={copilot.decision_signal} confidence={copilot.confidence_band} />
        )}
      </div>

      {/* ── SKU Selector ── */}
      <div className="bg-white border border-gray-200 rounded-xl p-4 mb-4 shadow-sm flex items-center gap-3 flex-wrap">
        <label className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Analyse SKU</label>
        {loadingList && allSkus.length === 0 ? (
          <div className="w-5 h-5 border-2 border-indigo-200 border-t-indigo-600 rounded-full animate-spin" />
        ) : allSkus.length === 0 ? (
          <span className="text-[12px] text-gray-400 italic">Upload a CSV or run similarity.py first</span>
        ) : (
          <select
            className="filter-select w-60"
            value={selSku}
            onChange={e => setSelSku(e.target.value)}
          >
            {uploadedSkus.length > 0 && (
              <optgroup label="📤 Uploaded SKUs">
                {uploadedSkus.map(s => <option key={s} value={s}>{s}</option>)}
              </optgroup>
            )}
            {skuList.filter(s => !uploadedSkus.includes(s)).length > 0 && (
              <optgroup label="📂 From similarity.py">
                {skuList.filter(s => !uploadedSkus.includes(s)).map(s => <option key={s} value={s}>{s}</option>)}
              </optgroup>
            )}
          </select>
        )}
        {loading && (
          <div className="flex items-center gap-2 text-[12px] text-indigo-600">
            <div className="w-4 h-4 border-2 border-indigo-200 border-t-indigo-600 rounded-full animate-spin" />
            Running intelligence pipeline…
          </div>
        )}
        {intel?.errors?.length > 0 && (
          <span className="text-[11px] text-amber-600 bg-amber-50 px-2 py-1 rounded">
            ⚠ {intel.errors.length} module warning(s) — partial results shown
          </span>
        )}
        {uploadedSkus.includes(selSku) && (
          <span className="text-[11px] bg-green-100 text-green-700 px-2 py-0.5 rounded-full border border-green-200 font-medium">
            📤 Uploaded SKU
          </span>
        )}
      </div>

      {error && (
        <div className="mb-4 p-3 rounded-xl bg-red-50 border border-red-200 text-[12px] text-red-700">
          {error}
        </div>
      )}

      {/* ── Page tabs ── */}
      <PageTabs
        active={tab}
        onChange={k => setTab(k as 'upload' | 'summary')}
        tabs={[
          { key: 'upload',  label: 'Upload & Process', icon: '📁', sub: uploadedSkus.length ? `${uploadedSkus.length} SKUs` : undefined },
          { key: 'summary', label: 'AI Summary',       icon: '🤖', sub: copilot?.decision_signal },
        ]}
      />

      {tab === 'upload' && (
        <UploadPanel
          onUploaded={handleUploaded}
          uploadedCount={uploadedSkus.length}
          onClearCache={handleClearCache}
        />
      )}

      {tab === 'summary' && (
        <>
          {loading && !intel && <Spinner />}

          {intel && !loading && (
            <div className="flex flex-col xl:flex-row gap-4">
              {/* ── Main intelligence panels ── */}
              <div className="flex-1 space-y-4 min-w-0">
                {/* Forecast explanation */}
                {forecastExpl && (
                  <div className="bg-indigo-50 border border-indigo-100 rounded-xl p-4">
                    <p className="font-bold text-[12px] text-indigo-700 mb-1">📊 {forecastExpl.headline}</p>
                    <ul className="grid grid-cols-1 md:grid-cols-2 gap-x-6 gap-y-1">
                      {(forecastExpl.drivers ?? []).map((d: string, i: number) => (
                        <li key={i} className="text-[11.5px] text-indigo-600 flex items-start gap-1.5">
                          <span className="mt-0.5">→</span> {d}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* Analogs + forecast */}
                <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
                  <AnalogPanel similarity={similarity} explainability={explainability} />
                  <ForecastPanel data={forecast} />
                </div>

                {/* Cannibalization + Stores */}
                <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
                  <CannibalizationPanel data={cannib} />
                  <StoreRecommendationPanel data={storeRec} />
                </div>

                {/* Scenarios + Risks */}
                <div className="grid grid-cols-1 xl:grid-cols-2 gap-4">
                  <ScenarioPanel scenarios={scenarios} />
                  <RiskPanel data={risks} />
                </div>

                {/* Whitespace */}
                <WhitespacePanel data={whitespace} />
              </div>

              {/* ── AI Merchant Copilot right rail ── */}
              {copilot && (
                <div className="w-full xl:w-[340px] shrink-0">
                  <div className="xl:sticky xl:top-[110px] bg-white border border-gray-200 rounded-xl shadow-sm p-4">
                    <SectionHeader icon="🤖" title="AI Merchant Copilot" sub="Executive decision summary" />
                    <span className="inline-block text-[11px] bg-gray-100 rounded-full px-3 py-1 text-gray-500 font-medium mb-3">
                      {copilot.one_liner}
                    </span>
                    <div className="flex flex-col gap-3">
                      <CopilotCard icon="🚀" title="Launch Overview"    body={copilot.launch_overview}    accent="indigo" />
                      <CopilotCard icon="💡" title="Market Opportunity" body={copilot.market_opportunity} accent="green" />
                      <CopilotCard icon="⚠️" title="Risk Assessment"    body={copilot.risk_assessment}    accent="red"   />
                      <CopilotCard icon="📋" title="Recommendation"     body={copilot.recommendation}     accent="amber" />
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}
        </>
      )}
    </div>
  )
}
