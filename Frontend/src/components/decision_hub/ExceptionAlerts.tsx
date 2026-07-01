interface Alert {
  severity: 'red' | 'orange' | 'green'
  icon: string
  title: string
  detail: string
  financial: number
  sku_id: string
  store_id: string
}

interface Props { alerts: Alert[] }

const SEV_COLORS: Record<string, string> = {
  red:    'bg-red-50 border-red-200',
  orange: 'bg-amber-50 border-amber-200',
  green:  'bg-emerald-50 border-emerald-200',
}
const SEV_TEXT: Record<string, string> = {
  red:    'text-red-700',
  orange: 'text-amber-700',
  green:  'text-emerald-700',
}
const SEV_BADGE: Record<string, string> = {
  red:    'bg-red-100 text-red-700',
  orange: 'bg-amber-100 text-amber-700',
  green:  'bg-emerald-100 text-emerald-700',
}
const SEV_LABEL: Record<string, string> = { red: 'URGENT', orange: 'WATCH', green: 'OPPORTUNITY' }

const fmtMoney = (n: number) =>
  n >= 1_000_000 ? `$${(n / 1_000_000).toFixed(1)}M`
  : n >= 1_000   ? `$${(n / 1_000).toFixed(0)}K`
  : `$${n.toFixed(0)}`

export default function ExceptionAlerts({ alerts }: Props) {
  if (!alerts?.length) return (
    <div className="flex items-center justify-center h-32 text-gray-400 text-sm">
      No exceptions found for current filters
    </div>
  )

  const sections = [
    { key: 'red',    label: '🔴 Urgent' },
    { key: 'orange', label: '🟠 Watch'  },
    { key: 'green',  label: '🟢 Opportunities' },
  ]

  return (
    <div className="space-y-1 max-h-[420px] overflow-y-auto pr-1">
      {sections.map(({ key, label }) => {
        const group = alerts.filter(a => a.severity === key)
        if (!group.length) return null
        return (
          <div key={key}>
            <p className="text-[10px] font-bold uppercase tracking-wider text-gray-400 mt-2 mb-1">{label}</p>
            {group.map((a, i) => (
              <div key={i} className={`rounded-lg border px-3 py-2 mb-1.5 ${SEV_COLORS[a.severity]}`}>
                <div className="flex items-start justify-between gap-2">
                  <div className="flex-1 min-w-0">
                    <p className={`text-[12px] font-bold truncate ${SEV_TEXT[a.severity]}`}>{a.title}</p>
                    <p className="text-[11px] text-gray-500 mt-0.5 truncate">{a.detail}</p>
                  </div>
                  <div className="flex flex-col items-end gap-1 shrink-0">
                    <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded-full ${SEV_BADGE[a.severity]}`}>
                      {SEV_LABEL[a.severity]}
                    </span>
                    <span className="text-[10px] font-semibold text-gray-600">{fmtMoney(a.financial)}</span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )
      })}
    </div>
  )
}
