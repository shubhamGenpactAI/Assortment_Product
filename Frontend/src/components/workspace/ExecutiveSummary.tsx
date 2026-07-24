import { TrendingUp, TrendingDown, AlertTriangle, CheckCircle, Zap, DollarSign, Target } from 'lucide-react'
import type { WorkspaceSummary } from '../../types/assortment'

interface Props { summary: WorkspaceSummary }

function fmt(n: number | null | undefined, decimals = 0): string {
  if (n == null) return '—'
  return n.toLocaleString('en-US', { maximumFractionDigits: decimals })
}

function fmtPct(n: number | null | undefined): string {
  if (n == null) return '—'
  return `${n >= 0 ? '+' : ''}${n.toFixed(1)}%`
}

function fmtM(n: number | null | undefined): string {
  if (n == null) return '—'
  if (Math.abs(n) >= 1_000_000) return `$${(n / 1_000_000).toFixed(1)}M`
  if (Math.abs(n) >= 1_000)     return `$${(n / 1_000).toFixed(0)}K`
  return `$${n.toFixed(0)}`
}

interface KPIChipProps {
  icon:    React.ReactNode
  label:   string
  value:   string
  sub?:    string
  accent?: string
  trend?:  'up' | 'down' | 'flat'
}

function KPIChip({ icon, label, value, sub, accent = 'text-[#1A1D2E]', trend }: KPIChipProps) {
  return (
    <div className="flex items-center gap-3 bg-gray-50 border border-gray-100 rounded-2xl px-4 py-3 shadow-sm hover:shadow-md transition-shadow min-w-0">
      <div className="flex-shrink-0 w-9 h-9 rounded-xl bg-gradient-to-br from-[#1A1D2E]/10 to-[#4F46E5]/10 flex items-center justify-center">
        {icon}
      </div>
      <div className="min-w-0">
        <p className="text-[9px] font-bold uppercase tracking-widest text-gray-400 truncate">{label}</p>
        <div className="flex items-baseline gap-1">
          <p className={`text-xl font-black leading-none ${accent}`}>{value}</p>
          {trend && (
            <span className={trend === 'up' ? 'text-emerald-500' : trend === 'down' ? 'text-red-400' : 'text-gray-400'}>
              {trend === 'up' ? <TrendingUp size={12} /> : trend === 'down' ? <TrendingDown size={12} /> : null}
            </span>
          )}
        </div>
        {sub && <p className="text-[10px] text-gray-400 mt-0.5 truncate">{sub}</p>}
      </div>
    </div>
  )
}

export function ExecutiveSummary({ summary: s }: Props) {
  const delistCount = (s.decisions['DELIST'] || 0) + (s.decisions['PHASE_OUT'] || 0)
  const expandCount = (s.decisions['EXPAND'] || 0) + (s.decisions['FUTURE_STAR'] || 0)
  const watchCount  = s.decisions['KEEP_WATCH'] || 0
  const keepCount   = s.decisions['CONTINUE'] || 0
  const growth      = s.avgForecastGrowth

  return (
    <div className="bg-gradient-to-r from-[#0F1629] via-[#1A1D2E] to-[#1E2240] px-6 pt-4 pb-4">
      {/* KPI chips */}
      <div className="flex flex-wrap gap-2 mb-4">
        <KPIChip
          icon={<Zap size={16} className="text-indigo-400" />}
          label="Active SKUs"
          value={fmt(s.totalSKUs)}
          sub="Global assortment"
          accent="text-[#1A1D2E]"
        />
        <KPIChip
          icon={<CheckCircle size={16} className="text-emerald-400" />}
          label="Expand / Star"
          value={fmt(expandCount)}
          sub="Expand distribution to grow"
          accent="text-emerald-400"
          trend="up"
        />
        <KPIChip
          icon={<AlertTriangle size={16} className="text-red-400" />}
          label="Exit Candidates"
          value={fmt(delistCount)}
          sub="Delist + Phase-out"
          accent="text-red-400"
          trend={delistCount > 5 ? 'down' : 'flat'}
        />
        <KPIChip
          icon={<Target size={16} className="text-orange-400" />}
          label="Under Watch"
          value={fmt(watchCount)}
          sub="Needs monitoring"
          accent="text-orange-400"
        />
        <KPIChip
          icon={<CheckCircle size={16} className="text-indigo-400" />}
          label="Core Continue"
          value={fmt(keepCount)}
          sub="Stable assortment"
          accent="text-indigo-400"
        />
        <KPIChip
          icon={<TrendingUp size={16} className="text-sky-400" />}
          label="Forecast Trend"
          value={fmtPct(growth)}
          accent={growth != null && growth >= 0 ? 'text-emerald-400' : 'text-red-400'}
          trend={growth != null ? (growth >= 0 ? 'up' : 'down') : 'flat'}
        />
        <KPIChip
          icon={<DollarSign size={16} className="text-amber-400" />}
          label="Revenue"
          value={fmtM(s.totalRevenue)}
          sub="Category total"
          accent="text-amber-400"
        />
      </div>
    </div>
  )
}
