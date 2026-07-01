interface Props {
  data:   number[]
  color?: string
  width?: number
  height?: number
}

export function Sparkline({ data, color = '#4F46E5', width = 72, height = 28 }: Props) {
  if (!data || data.length < 2) return <span className="text-gray-300 text-xs">—</span>
  const vals = data.filter((v) => v != null && !isNaN(v))
  if (vals.length < 2) return <span className="text-gray-300 text-xs">—</span>

  const max = Math.max(...vals)
  const min = Math.min(...vals)
  const range = max - min || 1
  const pad = 2

  const pts = vals.map((v, i) => ({
    x: pad + (i / (vals.length - 1)) * (width - pad * 2),
    y: pad + ((max - v) / range) * (height - pad * 2),
  }))

  const path = pts.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(' ')
  const last = pts[pts.length - 1]

  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} className="overflow-visible">
      <path d={path} fill="none" stroke={color} strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" />
      <circle cx={last.x} cy={last.y} r={2.5} fill={color} />
    </svg>
  )
}
