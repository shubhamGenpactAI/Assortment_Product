import type { DecisionType } from '../../types/assortment'

const CONFIG: Record<DecisionType, { label: string; bg: string; text: string; dot: string }> = {
  EXPAND:      { label: 'Expand',      bg: 'bg-emerald-50',  text: 'text-emerald-700', dot: 'bg-emerald-500' },
  FUTURE_STAR: { label: 'Future Star', bg: 'bg-sky-50',      text: 'text-sky-700',     dot: 'bg-sky-500'     },
  KEEP:        { label: 'Keep',        bg: 'bg-indigo-50',   text: 'text-indigo-700',  dot: 'bg-indigo-500'  },
  CASH_COW:    { label: 'Cash Cow',    bg: 'bg-violet-50',   text: 'text-violet-700',  dot: 'bg-violet-500'  },
  INVESTIGATE: { label: 'Investigate', bg: 'bg-amber-50',    text: 'text-amber-700',   dot: 'bg-amber-500'   },
  KEEP_WATCH:  { label: 'Watch',       bg: 'bg-orange-50',   text: 'text-orange-700',  dot: 'bg-orange-500'  },
  PHASE_OUT:   { label: 'Phase Out',   bg: 'bg-rose-50',     text: 'text-rose-700',    dot: 'bg-rose-400'    },
  REPLACE:     { label: 'Replace',     bg: 'bg-pink-50',     text: 'text-pink-700',    dot: 'bg-pink-500'    },
  DELIST:      { label: 'Delist',      bg: 'bg-red-50',      text: 'text-red-700',     dot: 'bg-red-500'     },
}

interface Props {
  decision: DecisionType | null | undefined
  size?: 'sm' | 'md' | 'lg'
}

export function DecisionBadge({ decision, size = 'sm' }: Props) {
  if (!decision || !(decision in CONFIG)) {
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-semibold bg-gray-100 text-gray-500">
        —
      </span>
    )
  }
  const c = CONFIG[decision]
  const px = size === 'lg' ? 'px-3 py-1' : size === 'md' ? 'px-2.5 py-0.5' : 'px-2 py-0.5'
  const fs = size === 'lg' ? 'text-xs' : 'text-[10px]'
  const ds = size === 'lg' ? 'w-2 h-2' : 'w-1.5 h-1.5'
  return (
    <span className={`inline-flex items-center gap-1.5 ${px} rounded-full ${fs} font-semibold ${c.bg} ${c.text} whitespace-nowrap`}>
      <span className={`${ds} rounded-full ${c.dot} flex-shrink-0`} />
      {c.label}
    </span>
  )
}

export function decisionColor(decision: DecisionType | null | undefined): string {
  if (!decision || !(decision in CONFIG)) return '#6B7280'
  const map: Record<DecisionType, string> = {
    EXPAND: '#10B981', FUTURE_STAR: '#0EA5E9', KEEP: '#4F46E5', CASH_COW: '#7C3AED',
    INVESTIGATE: '#F59E0B', KEEP_WATCH: '#F97316', PHASE_OUT: '#F43F5E',
    REPLACE: '#EC4899', DELIST: '#EF4444',
  }
  return map[decision]
}
