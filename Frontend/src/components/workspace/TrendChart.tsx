import { useEffect, useRef } from 'react'
import Plotly from 'plotly.js-dist-min'
import type { WeeklyDemandPoint, ForecastPoint } from '../../types/assortment'

interface Props {
  weekly:   WeeklyDemandPoint[]
  forecast: ForecastPoint[]
  height?:  number
}

const BRAND = '#4F46E5'
const AMBER = '#F2A93B'

export function TrendChart({ weekly, forecast, height = 240 }: Props) {
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!ref.current) return

    const actX = weekly.map((p) => p.w)
    const actY = weekly.map((p) => p.q ?? 0)
    const fcX  = forecast.map((p) => p.w)
    const fcY  = forecast.map((p) => p.fc ?? 0)
    const loY  = forecast.map((p) => p.lo ?? 0)
    const hiY  = forecast.map((p) => p.hi ?? 0)

    const traces: Partial<Plotly.PlotData>[] = [
      {
        x: actX, y: actY, type: 'scatter', mode: 'lines',
        name: 'Actual', line: { color: '#9CA3AF', width: 2 },
        hovertemplate: '<b>%{x}</b><br>Actual: %{y:,.0f}<extra></extra>',
      },
    ]

    if (fcX.length > 0) {
      traces.push(
        {
          x: fcX, y: hiY, type: 'scatter', mode: 'lines',
          name: '_hi', showlegend: false, line: { color: 'transparent' }, hoverinfo: 'skip',
        } as Partial<Plotly.PlotData>,
        {
          x: fcX, y: loY, type: 'scatter', mode: 'lines', fill: 'tonexty',
          fillcolor: 'rgba(99,102,241,0.10)', name: 'Confidence Band',
          line: { color: 'transparent' }, hoverinfo: 'skip',
        } as Partial<Plotly.PlotData>,
        {
          x: fcX, y: fcY, type: 'scatter', mode: 'lines+markers',
          name: 'Forecast', line: { color: BRAND, width: 2, dash: 'dash' },
          marker: { size: 6, symbol: 'diamond', color: BRAND },
          hovertemplate: '<b>%{x}</b><br>Forecast: %{y:,.0f}<extra></extra>',
        },
      )
    }

    const layout: Partial<Plotly.Layout> = {
      height,
      margin: { l: 44, r: 8, t: 10, b: 44 },
      plot_bgcolor: '#FFFFFF', paper_bgcolor: '#FFFFFF',
      legend: { orientation: 'h', y: -0.25, x: 0, font: { size: 10, color: '#6B7280' } },
      xaxis: {
        // Force categorical: the labels are period strings ("Jun'25", "W23'26"),
        // NOT dates. Without this, Plotly auto-parses "YYYY-WW"/"YYYY-MM"-looking
        // values as calendar dates and mislabels the axis.
        type: 'category',
        showgrid: true, gridcolor: '#F3F4F6', tickangle: -30,
        tickfont: { size: 10, color: '#9CA3AF' }, linecolor: '#E5E7EB',
        // Show every category label (≤12 points per tab) so the last bucket
        // — e.g. May'26 — is always labelled, not thinned away.
        tickmode: 'array', tickvals: (actX.length ? actX : fcX), automargin: true,
      },
      yaxis: {
        showgrid: true, gridcolor: '#F3F4F6',
        tickfont: { size: 10, color: '#9CA3AF' }, linecolor: '#E5E7EB',
        rangemode: 'tozero',
      },
    }

    if (actX.length > 0 && fcX.length > 0) {
      const sep = actX[actX.length - 1]
      layout.shapes = [{ type: 'line', xref: 'x', yref: 'paper', x0: sep, x1: sep, y0: 0, y1: 1, line: { color: AMBER, width: 1, dash: 'dot' } } as Plotly.Shape]
      layout.annotations = [{ x: sep, y: 1.0, xref: 'x', yref: 'paper', text: 'Forecast →', showarrow: false, font: { size: 9, color: AMBER }, xanchor: 'left' } as Plotly.Annotations]
    }

    Plotly.react(ref.current, traces, layout, { displayModeBar: false, responsive: true })
    return () => { if (ref.current) Plotly.purge(ref.current) }
  }, [weekly, forecast, height])

  const hasData = weekly.length > 0 || forecast.length > 0
  if (!hasData) {
    return (
      <div className="flex items-center justify-center h-32 bg-gray-50 rounded-xl">
        <p className="text-xs text-gray-400">No trend data available for this SKU</p>
      </div>
    )
  }

  return <div ref={ref} className="w-full" />
}
