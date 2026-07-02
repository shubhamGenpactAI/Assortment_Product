import { useState, useMemo } from 'react'
import { X, ChevronRight, TrendingUp, TrendingDown, Minus, Sparkles, ArrowRight, GitCompare } from 'lucide-react'
import type {
  SKURecommendation, AssortmentData, TransferCandidate, DecisionType, SKUMasterInfo
} from '../../types/assortment'
import { saveAssortmentDecision, type AssortmentDecisionPayload } from '../../api/assortmentData'
import { DecisionBadge } from './DecisionBadge'
import { KPITooltip } from './KPITooltip'
import { TrendChart } from './TrendChart'

// ── helpers ────────────────────────────────────────────────────────────────

function fmt(n: number | null | undefined, dec = 2): string {
  if (n == null) return '—'
  return n.toLocaleString('en-US', { maximumFractionDigits: dec, minimumFractionDigits: dec })
}

function fmtK(n: number | null | undefined): string {
  if (n == null) return '—'
  if (Math.abs(n) >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (Math.abs(n) >= 1_000) return `${(n / 1_000).toFixed(0)}K`
  return n.toFixed(0)
}

function fmtPct(n: number | null | undefined): string {
  if (n == null) return '—'
  return `${n >= 0 ? '+' : ''}${n.toFixed(1)}%`
}

// ── KPI card ──────────────────────────────────────────────────────────────

interface KPICardProps {
  label:   string
  value:   string
  tooltip: string
  trend?:  'up' | 'down' | 'flat'
  accent?: string
}

function KPICard({ label, value, tooltip, trend, accent = '#4F46E5' }: KPICardProps) {
  return (
    <div className="bg-gray-50 rounded-2xl p-3 hover:bg-white hover:shadow-sm transition-all border border-gray-100">
      <KPITooltip label={label} tooltip={tooltip} />
      <div className="flex items-baseline gap-1 mt-1.5">
        <span className="text-xl font-black" style={{ color: accent }}>{value}</span>
        {trend === 'up' && <TrendingUp size={13} className="text-emerald-500" />}
        {trend === 'down' && <TrendingDown size={13} className="text-red-400" />}
        {trend === 'flat' && <Minus size={13} className="text-gray-400" />}
      </div>
    </div>
  )
}

// ── Band pill ─────────────────────────────────────────────────────────────

function BandPill({ value }: { value: string | null | undefined }) {
  if (!value) return <span className="text-gray-400 text-xs">—</span>
  const isHigh = value.startsWith('HIGH') || value === 'STRONG_GROWTH' || value === 'GROWTH'
  const isLow  = value.startsWith('LOW')  || value === 'DECLINE' || value === 'SHARP_DECLINE'
  const bg     = isHigh ? 'bg-emerald-100 text-emerald-700' : isLow ? 'bg-red-100 text-red-700' : 'bg-amber-100 text-amber-700'
  const label  = value.replace(/_HEALTH|_DELIST|_GMROI/g, '').replace('STRONG_', '★ ')
  return <span className={`inline-flex px-2 py-0.5 rounded-lg text-[10px] font-bold ${bg}`}>{label}</span>
}

// ── Action center ──────────────────────────────────────────────────────────

const ACTION_LABELS: Partial<Record<DecisionType, { label: string; color: string; impact: string }>> = {
  EXPAND:      { label: 'Expand Distribution',  color: 'bg-emerald-500 hover:bg-emerald-600', impact: 'Expected +12–18% revenue uplift over 8 weeks.' },
  FUTURE_STAR: { label: 'Protect & Invest',      color: 'bg-sky-500 hover:bg-sky-600',        impact: 'Retain full distribution. Re-evaluate in 4 weeks.' },
  KEEP:        { label: 'Maintain Assortment',   color: 'bg-indigo-500 hover:bg-indigo-600',  impact: 'No immediate action needed. Monitor inventory levels.' },
  CASH_COW:    { label: 'Harvest Margin',        color: 'bg-violet-500 hover:bg-violet-600',  impact: 'Reduce promo spend. Optimise shelf price for margin.' },
  INVESTIGATE: { label: 'Escalate for Review',   color: 'bg-amber-500 hover:bg-amber-600',    impact: 'Conflicting signals — manual category review required.' },
  KEEP_WATCH:  { label: 'Set Performance Trigger', color: 'bg-orange-500 hover:bg-orange-600', impact: 'Flag for next review cycle. No incremental investment.' },
  PHASE_OUT:   { label: 'Initiate Phase-Out',    color: 'bg-rose-500 hover:bg-rose-600',      impact: '-50% facings at next reset. ETA: 4–6 weeks.' },
  REPLACE:     { label: 'Plan Replacement',      color: 'bg-pink-500 hover:bg-pink-600',      impact: 'Identify best substitute. Stage shelf transition.' },
  DELIST:      { label: 'Confirm Delist',        color: 'bg-red-600 hover:bg-red-700',        impact: 'Remove at next reset. Cancel open POs. Reallocate space.' },
}

interface ActionCenterProps {
  decision:    DecisionType | null | undefined
  sku:         SKURecommendation
  masterInfo:  SKUMasterInfo | undefined
  productName: string
}

function ActionCenter({ decision, sku, masterInfo, productName }: ActionCenterProps) {
  const [actionDone,    setActionDone]    = useState(false)
  const [saving,        setSaving]        = useState(false)
  const [saveError,     setSaveError]     = useState<string | null>(null)
  const [comment,       setComment]       = useState('')
  const [commentSaving, setCommentSaving] = useState(false)
  const [commentSaved,  setCommentSaved]  = useState(false)

  if (!decision || !(decision in ACTION_LABELS)) return null
  const cfg = ACTION_LABELS[decision]!

  function buildPayload(overrideComment = ''): AssortmentDecisionPayload {
    return {
      decision_label:       cfg.label,
      decision_type:        decision,
      comment:              overrideComment,
      sku_id:               sku.SKU_ID,
      product_name:         productName,
      brand:                masterInfo?.Brand ?? null,
      category:             masterInfo?.Category ?? null,
      sub_category:         sku.Sub_Category,
      view_label:           sku.granularity_level === 'Global'
                              ? 'Global'
                              : `${sku.granularity_level}: ${sku.granularity_value}`,
      scope:                sku.granularity_level,
      granularity_value:    sku.granularity_value,
      abc_class:            sku.ABC_Class,
      health_score:         sku.Health_Score,
      delist_score:         sku.delist_score,
      gmroi:                sku.GMROI,
      forecast_growth_pct:  sku.Forecast_Growth_Pct,
      health_band:          sku.Health_Band,
      delist_band:          sku.Delist_Band,
      basket_role:          sku.Basket_Role,
      total_revenue:        sku.total_revenue,
      total_margin:         sku.total_margin,
      price_band:           masterInfo?.Price_Band ?? null,
      list_price_usd:       masterInfo?.List_Price_USD ?? null,
      decision_reason:      sku.Decision_Reason,
      recommended_action:   sku.Recommended_Action,
    }
  }

  async function handleActionClick() {
    setSaving(true)
    setSaveError(null)
    try {
      await saveAssortmentDecision(buildPayload())
      setActionDone(true)
    } catch {
      setSaveError('Could not save — check server connection.')
    } finally {
      setSaving(false)
    }
  }

  async function handleCommentSubmit() {
    if (!comment.trim()) return
    setCommentSaving(true)
    try {
      await saveAssortmentDecision(buildPayload(comment.trim()))
      setCommentSaved(true)
      setComment('')
      setTimeout(() => setCommentSaved(false), 3000)
    } catch {
      // best-effort; button re-enables automatically
    } finally {
      setCommentSaving(false)
    }
  }

  return (
    <div className="px-5 pb-5 pt-3 border-t border-gray-100">
      <p className="text-[10px] font-bold uppercase tracking-widest text-gray-400 mb-3">Action Center</p>

      {/* Decision button */}
      {!actionDone ? (
        <button
          onClick={handleActionClick}
          disabled={saving}
          className={`w-full ${cfg.color} text-white font-bold text-sm rounded-2xl py-3 px-4 transition-colors flex items-center justify-center gap-2 disabled:opacity-60`}
        >
          <ArrowRight size={15} />
          {saving ? 'Saving…' : cfg.label}
        </button>
      ) : (
        <div className="bg-emerald-50 border border-emerald-200 rounded-2xl p-4 animate-fade-in">
          <p className="text-[11px] font-bold text-emerald-700 mb-1">Action Saved</p>
          <p className="text-[12px] text-emerald-600">{cfg.impact}</p>
          <button
            onClick={() => setActionDone(false)}
            className="mt-2 text-[10px] text-gray-400 hover:text-gray-600"
          >
            ← Undo
          </button>
        </div>
      )}

      {saveError && (
        <p className="text-[11px] text-red-500 mt-2">{saveError}</p>
      )}

      {/* Manager comment */}
      <div className="mt-4">
        <p className="text-[10px] font-bold uppercase tracking-widest text-gray-400 mb-2">
          Manager Comment
        </p>
        <textarea
          value={comment}
          onChange={(e) => setComment(e.target.value)}
          placeholder="Disagree with this recommendation? Add your reasoning…"
          rows={3}
          className="w-full text-[12px] text-gray-700 bg-gray-50 border border-gray-200 rounded-xl p-3 resize-none focus:outline-none focus:border-indigo-300 focus:bg-white transition-all placeholder:text-gray-400"
        />
        <button
          onClick={handleCommentSubmit}
          disabled={commentSaving || !comment.trim()}
          className="mt-2 w-full bg-gray-100 hover:bg-indigo-50 hover:text-indigo-700 text-gray-600 font-semibold text-[12px] rounded-xl py-2 px-4 transition-colors disabled:opacity-50"
        >
          {commentSaving ? 'Submitting…' : commentSaved ? '✓ Comment Saved' : 'Submit Comment'}
        </button>
      </div>
    </div>
  )
}

// ── Replacement candidate card ─────────────────────────────────────────────

interface ReplacementCardProps {
  candidate: TransferCandidate
  rank:      number
  globalRec: SKURecommendation | undefined
  skuNames:  Record<string, string>
}

function ReplacementCard({ candidate, rank, globalRec, skuNames }: ReplacementCardProps) {
  const [compare, setCompare] = useState(false)
  const name = skuNames[candidate.to_sku] || candidate.to_sku
  const conf = candidate.transfer_confidence ?? 0

  return (
    <div className="bg-gray-50 rounded-2xl p-4 border border-gray-100 hover:border-indigo-200 hover:bg-white transition-all">
      <div className="flex items-start justify-between mb-2">
        <div>
          <div className="flex items-center gap-2 mb-0.5">
            <span className="text-[9px] font-black text-gray-400 uppercase tracking-widest">#{rank} Replacement</span>
            <span className="text-[9px] font-bold bg-indigo-100 text-indigo-700 px-1.5 py-0.5 rounded-md">
              {(conf * 100).toFixed(0)}% match
            </span>
          </div>
          <p className="text-[13px] font-bold text-[#1A1D2E] leading-tight">{name}</p>
          <p className="text-[10px] text-gray-400 font-mono">{candidate.to_sku}</p>
        </div>
        {globalRec && <DecisionBadge decision={globalRec.Decision} size="sm" />}
      </div>

      <div className="grid grid-cols-3 gap-2 mb-3">
        {candidate.to_sku_total_revenue != null && (
          <div className="text-center">
            <p className="text-[9px] text-gray-400 uppercase tracking-wide">Revenue</p>
            <p className="text-[13px] font-bold text-gray-700">{fmtK(candidate.to_sku_total_revenue)}</p>
          </div>
        )}
        {candidate.transfer_lift != null && (
          <div className="text-center">
            <p className="text-[9px] text-gray-400 uppercase tracking-wide">Lift</p>
            <p className="text-[13px] font-bold text-gray-700">{candidate.transfer_lift.toFixed(2)}×</p>
          </div>
        )}
        {globalRec?.GMROI != null && (
          <div className="text-center">
            <p className="text-[9px] text-gray-400 uppercase tracking-wide">GMROI</p>
            <p className="text-[13px] font-bold text-gray-700">{fmtK(globalRec.GMROI)}</p>
          </div>
        )}
      </div>

      <p className="text-[11px] text-gray-500 italic leading-relaxed mb-3">
        "Recommended because it satisfies similar shopper missions
        {candidate.transfer_lift != null && candidate.transfer_lift > 1 ? ` with ${((candidate.transfer_lift - 1) * 100).toFixed(0)}% higher basket lift` : ''}
        {globalRec?.Health_Score != null ? ` and a stronger health score (${globalRec.Health_Score.toFixed(2)})` : ''}.
        Low cannibalization overlap detected."
      </p>

      <button
        onClick={() => setCompare((p) => !p)}
        className="flex items-center gap-1.5 text-[11px] font-semibold text-indigo-600 hover:text-indigo-800 transition-colors"
      >
        <GitCompare size={12} />
        {compare ? 'Hide comparison' : 'Compare vs current'}
      </button>

      {compare && globalRec && (
        <div className="mt-3 pt-3 border-t border-gray-100 animate-fade-in">
          <p className="text-[9px] font-bold uppercase tracking-widest text-gray-400 mb-2">Side-by-side</p>
          <div className="grid grid-cols-2 gap-1 text-[11px]">
            {[
              { label: 'Revenue',  cur: fmtK(globalRec.total_revenue), rep: fmtK(candidate.to_sku_total_revenue) },
              { label: 'GMROI',    cur: fmtK(globalRec.GMROI),         rep: globalRec ? fmtK(globalRec.GMROI) : '—' },
              { label: 'Health',   cur: fmt(globalRec.Health_Score),   rep: globalRec ? fmt(globalRec.Health_Score) : '—' },
              { label: 'Forecast', cur: fmtPct(globalRec.Forecast_Growth_Pct), rep: '—' },
            ].map(({ label, cur, rep }) => (
              <div key={label} className="bg-white rounded-lg p-2 border border-gray-100">
                <p className="text-[9px] text-gray-400 uppercase tracking-wide mb-1">{label}</p>
                <div className="flex items-center justify-between">
                  <div>
                    <p className="text-[9px] text-gray-400">Current</p>
                    <p className="font-bold text-red-500">{cur}</p>
                  </div>
                  <ChevronRight size={10} className="text-gray-300" />
                  <div>
                    <p className="text-[9px] text-gray-400">Replace</p>
                    <p className="font-bold text-emerald-600">{rep}</p>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

// ── Main drawer ────────────────────────────────────────────────────────────

interface Props {
  open:     boolean
  sku:      SKURecommendation | null
  data:     AssortmentData
  skuNames: Record<string, string>
  onClose:  () => void
}

const NEEDS_REPLACEMENT: DecisionType[] = ['DELIST', 'REPLACE', 'PHASE_OUT']

export function SKUDrawer({ open, sku, data, skuNames, onClose }: Props) {
  const [activeTab, setActiveTab] = useState<'trend' | 'forecast'>('trend')

  const skuId = sku?.SKU_ID ?? ''

  const weekly   = data.weeklyDemand[skuId]   ?? []
  const forecast = data.forecastData[skuId]   ?? []
  const basket   = data.basketInsights[skuId]
  const masterInfo = data.skuMaster[skuId]

  // Find global-level row for the same SKU (if current row is store-level)
  const globalRow = useMemo(() =>
    sku?.granularity_level !== 'Global'
      ? data.recommendations.find((r) => r.SKU_ID === skuId && r.granularity_level === 'Global')
      : sku,
    [sku, skuId, data.recommendations]
  )

  // Replacement candidates
  const candidates: TransferCandidate[] = useMemo(() => {
    if (!sku || !NEEDS_REPLACEMENT.includes(sku.Decision as DecisionType)) return []
    return (data.transferMatrix[skuId] ?? []).slice(0, 3)
  }, [sku, skuId, data.transferMatrix])

  const candidateGlobalRecs = useMemo(() =>
    Object.fromEntries(
      candidates.map((c) => [
        c.to_sku,
        data.recommendations.find((r) => r.SKU_ID === c.to_sku && r.granularity_level === 'Global'),
      ])
    ),
    [candidates, data.recommendations]
  )

  const productName = skuNames[skuId] || skuId

  const trendWeekly   = activeTab === 'trend' ? weekly : []
  const trendForecast = activeTab === 'forecast' ? forecast : []
  const trendData     = activeTab === 'trend' ? weekly : []

  if (!open || !sku) return null

  return (
    <>
      {/* Backdrop */}
      <div className="fixed inset-0 bg-black/20 z-30 backdrop-blur-[1px]" onClick={onClose} />

      {/* Drawer panel — positioned below the 96px fixed NavBar */}
      <aside className="fixed right-0 w-[500px] max-w-[95vw] bg-white shadow-2xl z-40 flex flex-col overflow-hidden"
             style={{ top: '96px', height: 'calc(100vh - 96px)' }}>
        {/* Header */}
        <div className="flex-shrink-0 px-5 pt-5 pb-4 border-b border-gray-100 bg-gradient-to-r from-[#0F1629] to-[#1A1D2E]">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0">
              <div className="flex items-center gap-2 mb-1.5 flex-wrap">
                <DecisionBadge decision={sku.Decision} size="md" />
                {sku.Health_Band && <BandPill value={sku.Health_Band} />}
                {sku.Basket_Role && (
                  <span className="text-[10px] font-semibold text-indigo-300 bg-white/10 px-2 py-0.5 rounded-lg">
                    {sku.Basket_Role}
                  </span>
                )}
              </div>
              <h2 className="text-[15px] font-black text-white leading-tight truncate">{productName}</h2>
              <p className="text-[10px] text-gray-400 font-mono mt-0.5">
                {sku.SKU_ID} · {sku.Sub_Category} · {sku.ABC_Class}-class ·{' '}
                {sku.granularity_level === 'Global' ? 'Global' : `${sku.granularity_level}: ${sku.granularity_value}`}
              </p>
            </div>
            <button onClick={onClose} className="flex-shrink-0 text-gray-400 hover:text-white transition-colors mt-0.5">
              <X size={18} />
            </button>
          </div>
        </div>

        {/* Scrollable body */}
        <div className="flex-1 overflow-y-auto">
          {/* AI narrative */}
          {sku.Recommendation_Narrative && (
            <div className="px-5 pt-4 pb-3">
              <div className="flex items-center gap-2 mb-2">
                <Sparkles size={13} className="text-[#F2A93B]" />
                <span className="text-[10px] font-bold uppercase tracking-widest text-gray-400">AI Recommendation</span>
              </div>
              <div className="bg-gradient-to-br from-[#0F1629]/5 to-indigo-50 rounded-2xl p-4 border border-indigo-100">
                <p className="text-[12px] text-gray-700 leading-relaxed">{sku.Recommendation_Narrative}</p>
                {sku.Decision_Reason && (
                  <p className="text-[11px] text-indigo-600 font-medium mt-2 pt-2 border-t border-indigo-100">
                    <strong>Key drivers:</strong> {sku.Decision_Reason}
                  </p>
                )}
              </div>
            </div>
          )}

          {/* KPI snapshot */}
          <div className="px-5 pb-3">
            <p className="text-[10px] font-bold uppercase tracking-widest text-gray-400 mb-3">KPI Snapshot</p>
            <div className="grid grid-cols-2 gap-2">
              <KPICard
                label="Health Score"
                value={fmt(sku.Health_Score)}
                tooltip="Composite measure of SKU commercial strength: sales, margin, sentiment, inventory, and market strength."
                accent={sku.Health_Score != null && sku.Health_Score > 0.3 ? '#10B981' : '#EF4444'}
                trend={sku.Health_Score != null && sku.Health_Score > 0.35 ? 'up' : 'down'}
              />
              <KPICard
                label="Delist Score"
                value={fmt(sku.delist_score)}
                tooltip="Higher score = stronger case for delisting. Composite of 7 weighted commercial signals."
                accent={sku.delist_score != null && sku.delist_score > 0.7 ? '#EF4444' : '#F59E0B'}
                trend={sku.delist_score != null && sku.delist_score > 0.7 ? 'down' : 'flat'}
              />
              <KPICard
                label="GMROI"
                value={fmtK(sku.GMROI)}
                tooltip="Gross Margin Return on Inventory Investment. Higher = better space productivity."
                accent="#4F46E5"
              />
              <KPICard
                label="Forecast Growth"
                value={fmtPct(sku.Forecast_Growth_Pct)}
                tooltip="Projected sales growth based on historical trends and AI forecasting models."
                accent={sku.Forecast_Growth_Pct != null && sku.Forecast_Growth_Pct >= 0 ? '#10B981' : '#EF4444'}
                trend={sku.Forecast_Growth_Pct != null ? (sku.Forecast_Growth_Pct >= 0 ? 'up' : 'down') : 'flat'}
              />
              <KPICard
                label="Sentiment"
                value={fmt(sku.SentimentIndex)}
                tooltip="Normalized consumer sentiment score from reviews and social data (0–1)."
                accent="#6366F1"
              />
              <KPICard
                label="Market Strength"
                value={fmt(sku.MarketStrengthIndex)}
                tooltip="Composite of market share, share growth, sub-category growth, and distribution trend."
                accent="#8B5CF6"
              />
              <KPICard
                label="Inventory Eff."
                value={fmt(sku.InventoryEfficiency)}
                tooltip="Gross margin generated per inventory unit (Days of Supply). Higher = more efficient."
                accent="#0EA5E9"
              />
              <KPICard
                label="Recapture"
                value={fmt(sku.Recapture_Potential)}
                tooltip="Probability that demand can be captured by substitute SKUs if this one is removed (0–1)."
                accent="#F97316"
              />
            </div>
          </div>

          {/* Band classification */}
          <div className="px-5 pb-3">
            <p className="text-[10px] font-bold uppercase tracking-widest text-gray-400 mb-2">Band Classification</p>
            <div className="flex flex-wrap gap-2">
              {[
                { label: 'Health', value: sku.Health_Band },
                { label: 'Delist', value: sku.Delist_Band },
                { label: 'GMROI', value: sku.GMROI_Band },
                { label: 'Forecast', value: sku.Forecast_Band },
              ].map(({ label, value }) => (
                <div key={label} className="flex items-center gap-1.5 bg-gray-50 rounded-xl px-3 py-1.5 border border-gray-100">
                  <span className="text-[9px] text-gray-400 font-semibold">{label}:</span>
                  <BandPill value={value} />
                </div>
              ))}
            </div>
          </div>

          {/* Trend chart */}
          <div className="px-5 pb-3">
            <div className="flex items-center justify-between mb-2">
              <p className="text-[10px] font-bold uppercase tracking-widest text-gray-400">Demand Trend</p>
              <div className="flex gap-1 bg-gray-100 rounded-lg p-0.5">
                {(['trend', 'forecast'] as const).map((tab) => (
                  <button
                    key={tab}
                    onClick={() => setActiveTab(tab)}
                    className={`px-2.5 py-1 rounded-md text-[10px] font-bold transition-all capitalize ${
                      activeTab === tab ? 'bg-white text-indigo-600 shadow-sm' : 'text-gray-400 hover:text-gray-600'
                    }`}
                  >
                    {tab === 'trend' ? 'Historical' : 'Forecast'}
                  </button>
                ))}
              </div>
            </div>
            <div className="bg-white rounded-2xl p-3 border border-gray-100">
              <TrendChart
                weekly={activeTab === 'trend' ? weekly : []}
                forecast={activeTab === 'forecast' ? forecast : []}
                height={200}
              />
            </div>
          </div>

          {/* Basket insights */}
          {basket && (
            <div className="px-5 pb-3">
              <p className="text-[10px] font-bold uppercase tracking-widest text-gray-400 mb-2">Basket Intelligence</p>
              <div className="grid grid-cols-3 gap-2">
                {[
                  { label: 'Baskets', value: basket.n_baskets_present?.toLocaleString() ?? '—' },
                  { label: 'Support', value: basket.support != null ? `${(basket.support * 100).toFixed(2)}%` : '—' },
                  { label: 'Dependency', value: basket.basket_dependency_score?.toFixed(1) ?? '—' },
                ].map(({ label, value }) => (
                  <div key={label} className="bg-gray-50 rounded-xl p-2.5 text-center border border-gray-100">
                    <p className="text-[9px] text-gray-400 uppercase tracking-wide">{label}</p>
                    <p className="text-[14px] font-black text-gray-700">{value}</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Replacement candidates */}
          {candidates.length > 0 && (
            <div className="px-5 pb-3">
              <div className="flex items-center gap-2 mb-3">
                <div className="w-1 h-4 bg-[#F2A93B] rounded-full" />
                <p className="text-[10px] font-bold uppercase tracking-widest text-gray-800">
                  Top Replacement Candidates
                </p>
              </div>
              <div className="flex flex-col gap-3">
                {candidates.map((c, i) => (
                  <ReplacementCard
                    key={c.to_sku}
                    candidate={c}
                    rank={i + 1}
                    globalRec={candidateGlobalRecs[c.to_sku]}
                    skuNames={skuNames}
                  />
                ))}
              </div>
            </div>
          )}

          {/* Recommended action text */}
          {sku.Recommended_Action && (
            <div className="px-5 pb-3">
              <p className="text-[10px] font-bold uppercase tracking-widest text-gray-400 mb-2">Recommended Action</p>
              <div className="bg-blue-50 border border-blue-100 rounded-2xl p-3">
                <p className="text-[12px] text-blue-800 leading-relaxed">{sku.Recommended_Action}</p>
              </div>
            </div>
          )}

          <div className="h-2" />
        </div>

        {/* Sticky action footer */}
        <ActionCenter
          decision={sku.Decision}
          sku={sku}
          masterInfo={masterInfo}
          productName={productName}
        />
      </aside>
    </>
  )
}
