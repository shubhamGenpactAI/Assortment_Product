import PlotlyChart from '../ui/PlotlyChart'

interface ScatterRow {
  SKU_ID: string
  Product_Name?: string
  Sub_Category?: string
  WoC: number
  GMROI: number
  Revenue: number
  Health_Score_100: number
  bubble_size: number
  Sell_Through: number
  delist_score?: number
  Calc_Growth_Pct?: number
}

interface Props { rows: ScatterRow[] }

export default function InventoryScatter({ rows }: Props) {
  if (!rows?.length) return (
    <div className="flex items-center justify-center h-64 text-gray-400 text-sm">No productivity data</div>
  )

  const valid = rows.filter(r => r.WoC != null && r.GMROI != null && r.GMROI > 0)

  const traces: any[] = [{
    type: 'scatter',
    mode: 'markers',
    x: valid.map(r => r.WoC),
    y: valid.map(r => r.GMROI),
    marker: {
      size: valid.map(r => r.bubble_size),
      color: valid.map(r => r.Health_Score_100),
      colorscale: [
        [0, '#EF4444'], [0.4, '#F59E0B'], [0.65, '#84CC16'], [1, '#10B981'],
      ],
      colorbar: {
        title: { text: 'Health', font: { size: 10 } },
        thickness: 10, len: 0.7, tickfont: { size: 9 },
      },
      opacity: 0.8,
      line: { width: 0.5, color: '#9CA3AF' },
    },
    text: valid.map(r => r.Product_Name ?? r.SKU_ID),
    hovertemplate:
      '<b>%{text}</b><br>' +
      'WoC: %{x:.1f} wks<br>' +
      'GMROI: %{y:.0f}<br>' +
      '<extra></extra>',
  }]

  // Max GMROI for quadrant lines
  const maxGMROI  = Math.max(...valid.map(r => r.GMROI)) * 1.05
  const medWoC    = 6

  return (
    <div>
      <div className="flex flex-wrap gap-3 text-[10px] text-gray-500 mb-2">
        <span>⬤ <span className="text-red-500 font-semibold">Red</span> = low health</span>
        <span>⬤ <span className="text-emerald-500 font-semibold">Green</span> = high health</span>
        <span>● Bubble size = Revenue</span>
      </div>
      <PlotlyChart
        traces={traces}
        height={310}
        layout={{
          margin: { l: 52, r: 20, t: 20, b: 52 },
          xaxis: {
            title: { text: 'Weeks of Cover →', font: { size: 11 } },
            zeroline: false,
            range: [0, Math.min(30, Math.max(...valid.map(r => r.WoC)) * 1.1)],
          },
          yaxis: {
            title: { text: 'GMROI ↑', font: { size: 11 } },
            zeroline: false,
          },
          shapes: [
            {
              type: 'line', x0: medWoC, x1: medWoC,
              y0: 0, y1: maxGMROI, yref: 'y',
              line: { color: '#CBD5E1', width: 1, dash: 'dot' },
            },
          ],
          annotations: [
            { x: 2,      y: maxGMROI * 0.96, text: '🏆 Understocked Winners', showarrow: false, font: { size: 9, color: '#6B7280' } },
            { x: 20,     y: maxGMROI * 0.96, text: '📦 Overstocked Winners',  showarrow: false, font: { size: 9, color: '#6B7280' } },
            { x: 2,      y: maxGMROI * 0.08, text: '⚠ Stock-out Risk',        showarrow: false, font: { size: 9, color: '#6B7280' } },
            { x: 20,     y: maxGMROI * 0.08, text: '🗑 Overstocked Losers',   showarrow: false, font: { size: 9, color: '#6B7280' } },
          ],
        }}
      />
    </div>
  )
}
