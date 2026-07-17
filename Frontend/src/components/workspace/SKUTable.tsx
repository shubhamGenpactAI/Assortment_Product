import { useMemo, useCallback, memo } from 'react'
import { AgGridReact } from 'ag-grid-react'
import type { ColDef, GridReadyEvent, RowClickedEvent, ICellRendererParams } from 'ag-grid-community'
import type { SKURecommendation, DecisionType } from '../../types/assortment'
import { DecisionBadge } from './DecisionBadge'
import { KPITooltip } from './KPITooltip'

interface Props {
  rows:        SKURecommendation[]
  skuNames:    Record<string, string>
  selectedId?: string
  onRowClick:  (row: SKURecommendation) => void
}

// ── Custom cell renderers ──────────────────────────────────────────────────

function DecisionCell({ value }: ICellRendererParams) {
  return (
    <div className="flex items-center h-full">
      <DecisionBadge decision={value as DecisionType} size="sm" />
    </div>
  )
}

function ScoreBar({ value, danger = false }: { value: number | null; danger?: boolean }) {
  if (value == null) return <span className="text-gray-300 text-xs">—</span>
  const pct = Math.min(Math.max(value * 100, 0), 100)
  const color = danger
    ? pct > 70 ? '#EF4444' : pct > 40 ? '#F97316' : '#10B981'
    : pct > 66 ? '#10B981' : pct > 33 ? '#F59E0B' : '#EF4444'
  return (
    <div className="flex items-center gap-2 w-full h-full">
      <div className="flex-1 h-1.5 bg-gray-100 rounded-full overflow-hidden">
        <div className="h-full rounded-full transition-all" style={{ width: `${pct}%`, backgroundColor: color }} />
      </div>
      <span className="text-[11px] font-semibold text-gray-600 w-8 text-right">{value.toFixed(2)}</span>
    </div>
  )
}

function HealthCell({ value }: ICellRendererParams) {
  return <ScoreBar value={value as number | null} />
}

function DelistCell({ value }: ICellRendererParams) {
  return <ScoreBar value={value as number | null} danger />
}

function GrowthCell({ value }: ICellRendererParams) {
  if (value == null) return <span className="text-gray-300 text-xs">—</span>
  const v = value as number
  const color = v >= 5 ? '#10B981' : v >= 0 ? '#6B7280' : v >= -5 ? '#F97316' : '#EF4444'
  return (
    <span className="text-[12px] font-bold" style={{ color }}>
      {v >= 0 ? '+' : ''}{v.toFixed(1)}%
    </span>
  )
}

function GMROICell({ value }: ICellRendererParams) {
  if (value == null) return <span className="text-gray-300 text-xs">—</span>
  return <span className="text-[12px] font-semibold text-gray-700">{(value as number).toLocaleString('en-US', { maximumFractionDigits: 0 })}</span>
}

function BandCell({ value }: ICellRendererParams) {
  if (!value) return <span className="text-gray-300 text-xs">—</span>
  const v = String(value)
  const isHigh = v.startsWith('HIGH')
  const isMid  = v.startsWith('MID')
  const color  = isHigh ? 'bg-emerald-50 text-emerald-700' : isMid ? 'bg-amber-50 text-amber-700' : 'bg-red-50 text-red-700'
  const label  = v.replace('_HEALTH', '').replace('_DELIST', '').replace('_GMROI', '').replace('STRONG_', '')
  return (
    <span className={`inline-flex items-center px-2 py-0.5 rounded-md text-[10px] font-semibold ${color}`}>
      {label}
    </span>
  )
}

// ── Tooltip definitions for column headers ────────────────────────────────

const KPI_TOOLTIPS: Record<string, string> = {
  'Health Score': 'Composite measure of SKU commercial strength: sales performance, profitability, sentiment, inventory efficiency, and market position.',
  'Delist Score': 'Higher score = stronger probability that this SKU can be removed with minimal category disruption. Composite of 7 weighted signals.',
  'GMROI':        'Gross Margin Return on Inventory Investment. Measures gross margin generated per dollar of inventory held. Higher = better space productivity.',
  'Forecast %':   'Projected sales growth based on historical trends and time-series forecasting models (LightGBM + AutoETS).',
  'Health Band':  'Percentile-based tier: HIGH = top third, MID = middle third, LOW = bottom third of health scores across all SKUs.',
}

function TooltipHeader({ label }: { label: string }) {
  const tip = KPI_TOOLTIPS[label]
  return (
    <div className="flex items-center gap-1 h-full">
      {tip
        ? <KPITooltip label={label} tooltip={tip} />
        : <span className="text-[10px] font-bold text-gray-500 uppercase tracking-wider">{label}</span>
      }
    </div>
  )
}

// ── Main component ─────────────────────────────────────────────────────────

export const SKUTable = memo(function SKUTable({ rows, skuNames, selectedId, onRowClick }: Props) {
  const colDefs = useMemo<ColDef[]>(() => [
    {
      field:      'SKU_ID',
      headerName: 'SKU / Product',
      pinned:     'left',
      width:      220,
      cellRenderer: (p: ICellRendererParams) => {
        const name = skuNames[p.value as string] || p.value
        return (
          <div className="flex flex-col justify-center h-full py-1">
            <span className="text-[11px] font-bold text-[#1A1D2E] truncate leading-tight">{name}</span>
            <span className="text-[9px] text-gray-400 font-mono">{p.value}</span>
          </div>
        )
      },
    },
    {
      field:      'Sub_Category',
      headerName: 'Sub-Category',
      width:      150,
      cellStyle:  { fontSize: '11px', color: '#6B7280' } as Record<string, string>,
    },
    {
      field:      'ABC_Class',
      headerName: 'ABC',
      width:      70,
      cellStyle:  (p) => ({
        fontSize: '11px', fontWeight: 700,
        color: p.value === 'A' ? '#10B981' : p.value === 'B' ? '#F59E0B' : '#9CA3AF',
      }),
    },
    {
      field:            'Health_Score',
      headerName:       'Health Score',
      headerComponent:  () => <TooltipHeader label="Health Score" />,
      width:            150,
      cellRenderer:     HealthCell,
      sort:             'desc',
    },
    {
      field:           'delist_score',
      headerName:      'Delist Score',
      headerComponent: () => <TooltipHeader label="Delist Score" />,
      width:           150,
      cellRenderer:    DelistCell,
    },
    {
      field:           'GMROI',
      headerName:      'GMROI',
      headerComponent: () => <TooltipHeader label="GMROI" />,
      width:           110,
      cellRenderer:    GMROICell,
      type:            'numericColumn',
    },
    {
      field:           'Forecast_Growth_Pct',
      headerName:      'Forecast %',
      headerComponent: () => <TooltipHeader label="Forecast %" />,
      width:           110,
      cellRenderer:    GrowthCell,
      type:            'numericColumn',
    },
    {
      field:        'Decision',
      headerName:   'Decision',
      width:        130,
      cellRenderer: DecisionCell,
    },
    {
      field:        'Health_Band',
      headerName:   'Health Band',
      headerComponent: () => <TooltipHeader label="Health Band" />,
      width:        120,
      cellRenderer: BandCell,
    },
    {
      field:      'Basket_Role',
      headerName: 'Basket Role',
      width:      110,
      cellStyle:  { fontSize: '11px', color: '#6B7280' } as Record<string, string>,
    },
    {
      field:      'granularity_level',
      headerName: 'Level',
      width:      100,
      cellStyle:  { fontSize: '10px', color: '#374151' } as Record<string, string>,
    },
    {
      field:      'granularity_value',
      headerName: 'Scope',
      width:      110,
      cellStyle:  { fontSize: '10px', color: '#374151' } as Record<string, string>,
    },
  ], [skuNames])

  const defaultColDef = useMemo<ColDef>(() => ({
    resizable: true, sortable: true, suppressMovable: false,
    cellStyle: { display: 'flex', alignItems: 'center' },
  }), [])

  const onGridReady = useCallback((e: GridReadyEvent) => {
    (window as unknown as Record<string, unknown>)._skuGridApi = e.api
  }, [])

  const getRowStyle = useCallback((params: { data?: SKURecommendation }) => {
    if (params.data?.SKU_ID === selectedId) {
      return { backgroundColor: '#EEF2FF', borderLeft: '3px solid #4F46E5' }
    }
    return undefined
  }, [selectedId])

  const handleRowClicked = useCallback((e: RowClickedEvent<SKURecommendation>) => {
    if (e.data) onRowClick(e.data)
  }, [onRowClick])

  return (
    <div className="ag-theme-alpine w-full h-full" style={{ minHeight: 300 }}>
      <AgGridReact
        rowData={rows}
        columnDefs={colDefs}
        defaultColDef={defaultColDef}
        onGridReady={onGridReady}
        onRowClicked={handleRowClicked}
        getRowStyle={getRowStyle}
        rowHeight={52}
        headerHeight={44}
        pagination
        paginationPageSize={25}
        suppressCellFocus
        enableCellTextSelection
        animateRows
      />
    </div>
  )
})
