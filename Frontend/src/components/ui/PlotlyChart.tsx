import { useEffect, useRef } from 'react'
import Plotly from 'plotly.js-dist-min'

interface Props {
  traces:  Partial<Plotly.PlotData>[]
  layout?: Partial<Plotly.Layout>
  height?: number
}

const BASE_LAYOUT: Partial<Plotly.Layout> = {
  plot_bgcolor:  '#FFFFFF',
  paper_bgcolor: '#FFFFFF',
  margin: { l: 48, r: 12, t: 20, b: 44 },
  xaxis: { showgrid: true, gridcolor: '#F0F2F5', tickfont: { size: 11, color: '#6B7280' } },
  yaxis: { showgrid: true, gridcolor: '#F0F2F5', tickfont: { size: 11, color: '#6B7280' } },
  legend: { font: { size: 11, color: '#4B5563' } },
}

export default function PlotlyChart({ traces, layout = {}, height = 320 }: Props) {
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!ref.current) return
    const merged: Partial<Plotly.Layout> = {
      ...BASE_LAYOUT,
      ...layout,
      height,
      xaxis: { ...BASE_LAYOUT.xaxis, ...(layout.xaxis || {}) },
      yaxis: { ...BASE_LAYOUT.yaxis, ...(layout.yaxis || {}) },
      margin: { ...BASE_LAYOUT.margin, ...(layout.margin || {}) },
    }
    Plotly.react(ref.current, traces, merged, { displayModeBar: false, responsive: true })
    return () => { if (ref.current) Plotly.purge(ref.current) }
  }, [traces, layout, height])

  return <div ref={ref} className="w-full" />
}
