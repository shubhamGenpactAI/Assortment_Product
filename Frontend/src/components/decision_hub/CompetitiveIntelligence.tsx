import { useMemo, useState } from 'react'
import { Loader2, X } from 'lucide-react'
import { fetchCompetitiveDrilldown } from '../../api/decisionHubApi'

interface CompRow {
  Product_Name:            string
  Our_Assortment:          'Yes' | 'No'
  DirectComp:              'Yes' | 'No'
  CompSpecificCatchment:   'Yes' | 'No'
  NewRetailToGrow:         'Yes' | 'No'
}

interface CompMetrics {
  overlap:              number
  our_exclusive:         number
  competitor_exclusive: number
}

export interface CompetitiveIntelligenceData {
  metrics: CompMetrics
  rows:    CompRow[]
}

interface DrilldownRetailer { Retailer: string; Sold: 'Yes' | 'No'; Combos: { Geography: string; Region: string }[] }
interface DrilldownData { product_name: string; category_key: string; retailers: DrilldownRetailer[] }

type CardKey = 'overlap' | 'our_exclusive' | 'competitor_exclusive'

const CATEGORY_COLS: { key: 'DirectComp' | 'CompSpecificCatchment' | 'NewRetailToGrow'; label: string }[] = [
  { key: 'DirectComp',            label: 'DirectComp' },
  { key: 'CompSpecificCatchment', label: 'Comp for Specific Catchment' },
  { key: 'NewRetailToGrow',       label: 'New Retail_To Grow' },
]

const CARDS: { key: CardKey; label: string; sub: string; color: string }[] = [
  { key: 'overlap',              label: 'Overlap',              sub: "Our SKUs also carried by ≥1 competitor",   color: 'border-l-indigo-500' },
  { key: 'our_exclusive',        label: 'Our Exclusive',        sub: 'Our SKUs no competitor carries',            color: 'border-l-emerald-500' },
  { key: 'competitor_exclusive', label: 'Competitor Exclusive', sub: "Competitor SKUs we don't carry",            color: 'border-l-red-500' },
]

function MetricCard({ label, sub, value, color, active, onClick }: {
  label: string; sub: string; value: number; color: string; active: boolean; onClick: () => void
}) {
  return (
    <button
      onClick={onClick}
      className={`text-left bg-white rounded-xl shadow-sm border border-gray-200 border-l-4 ${color} px-4 py-3.5 transition-all
        ${active ? 'ring-2 ring-[#4F46E5] ring-offset-1' : 'hover:shadow-md'}`}
    >
      <p className="text-[10px] font-bold uppercase tracking-wider text-gray-400 mb-1">{label}</p>
      <p className="text-xl font-extrabold text-[#1A1D2E]">{value}</p>
      <p className="text-[11px] text-gray-400 mt-0.5">{sub}</p>
    </button>
  )
}

function YesNoBadge({ value, onClick }: { value: 'Yes' | 'No'; onClick?: () => void }) {
  const isYes = value === 'Yes'
  const base  = isYes ? 'bg-emerald-50 text-emerald-700' : 'bg-gray-100 text-gray-400'
  if (!onClick) {
    return <span className={`inline-flex px-2 py-0.5 rounded-full text-[10px] font-bold ${base}`}>{value}</span>
  }
  return (
    <button
      onClick={onClick}
      className={`inline-flex px-2 py-0.5 rounded-full text-[10px] font-bold ${base} hover:ring-2 hover:ring-[#4F46E5]/40 cursor-pointer transition-all`}
      title="View competitor breakdown"
    >
      {value}
    </button>
  )
}

function DrilldownModal({ productName, categoryLabel, data, loading, onClose }: {
  productName: string; categoryLabel: string; data: DrilldownData | null; loading: boolean; onClose: () => void
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4" onClick={onClose}>
      <div
        className="bg-white rounded-2xl shadow-xl w-full max-w-lg max-h-[80vh] overflow-hidden flex flex-col"
        onClick={e => e.stopPropagation()}
      >
        <div className="flex items-start justify-between px-5 py-4 border-b border-gray-100">
          <div>
            <p className="text-[10px] font-bold uppercase tracking-wider text-gray-400 mb-0.5">{categoryLabel}</p>
            <p className="text-[13px] font-bold text-[#1A1D2E] leading-tight">{productName}</p>
          </div>
          <button onClick={onClose} className="text-gray-400 hover:text-gray-700">
            <X size={18} />
          </button>
        </div>
        <div className="overflow-y-auto p-5">
          {loading ? (
            <div className="flex items-center justify-center py-10 text-gray-400">
              <Loader2 size={20} className="animate-spin" />
            </div>
          ) : !data || data.retailers.length === 0 ? (
            <p className="text-center text-gray-400 text-sm py-6">No competitors found for this category.</p>
          ) : (
            <table className="w-full text-[12px]">
              <thead>
                <tr className="border-b border-gray-200">
                  <th className="text-left py-2 font-semibold text-gray-500 text-[10.5px] uppercase tracking-wider">Competitor</th>
                  <th className="text-left py-2 font-semibold text-gray-500 text-[10.5px] uppercase tracking-wider">Carries Product</th>
                  <th className="text-left py-2 font-semibold text-gray-500 text-[10.5px] uppercase tracking-wider">Geography / Region</th>
                </tr>
              </thead>
              <tbody>
                {data.retailers.map(r => (
                  <tr key={r.Retailer} className="border-b border-gray-100">
                    <td className="py-2 font-medium text-[#1A1D2E]">{r.Retailer}</td>
                    <td className="py-2"><YesNoBadge value={r.Sold} /></td>
                    <td className="py-2 text-gray-500 text-[11px]">
                      {r.Combos.length === 0 ? '—' : r.Combos.map(c => `${c.Geography} / ${c.Region}`).join(', ')}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>
    </div>
  )
}

interface Props { data: CompetitiveIntelligenceData | null }

export default function CompetitiveIntelligence({ data }: Props) {
  const [activeCard, setActiveCard] = useState<CardKey | null>(null)
  const [drill, setDrill] = useState<{ productName: string; categoryKey: string; categoryLabel: string } | null>(null)
  const [drillData, setDrillData] = useState<DrilldownData | null>(null)
  const [drillLoading, setDrillLoading] = useState(false)

  const rows    = data?.rows ?? []
  const metrics = data?.metrics ?? { overlap: 0, our_exclusive: 0, competitor_exclusive: 0 }

  const filteredRows = useMemo(() => {
    if (activeCard === 'overlap')
      return rows.filter(r => r.Our_Assortment === 'Yes' && CATEGORY_COLS.some(c => r[c.key] === 'Yes'))
    if (activeCard === 'our_exclusive')
      return rows.filter(r => r.Our_Assortment === 'Yes' && CATEGORY_COLS.every(c => r[c.key] === 'No'))
    if (activeCard === 'competitor_exclusive')
      return rows.filter(r => r.Our_Assortment === 'No' && CATEGORY_COLS.some(c => r[c.key] === 'Yes'))
    return rows
  }, [rows, activeCard])

  const toggleCard = (key: CardKey) => setActiveCard(prev => (prev === key ? null : key))

  const openDrilldown = async (productName: string, categoryKey: string, categoryLabel: string) => {
    setDrill({ productName, categoryKey, categoryLabel })
    setDrillData(null)
    setDrillLoading(true)
    try {
      const res = await fetchCompetitiveDrilldown(productName, categoryKey)
      setDrillData(res)
    } catch {
      setDrillData({ product_name: productName, category_key: categoryKey, retailers: [] })
    } finally {
      setDrillLoading(false)
    }
  }

  return (
    <div>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 mb-4">
        {CARDS.map(c => (
          <MetricCard
            key={c.key}
            label={c.label}
            sub={c.sub}
            value={metrics[c.key]}
            color={c.color}
            active={activeCard === c.key}
            onClick={() => toggleCard(c.key)}
          />
        ))}
      </div>

      {activeCard && (
        <div className="flex items-center gap-2 mb-2 text-[11px] text-gray-500">
          <span>Filtered by <b className="text-[#1A1D2E]">{CARDS.find(c => c.key === activeCard)?.label}</b> — {filteredRows.length} SKUs</span>
          <button onClick={() => setActiveCard(null)} className="text-[#4F46E5] font-semibold hover:underline">Clear filter</button>
        </div>
      )}

      <div className="overflow-x-auto rounded-xl border border-gray-200">
        <table className="w-full text-[12px]">
          <thead>
            <tr className="bg-gray-50 border-b border-gray-200">
              <th className="text-left px-3 py-2 font-semibold text-gray-500 text-[10.5px] uppercase tracking-wider">SKU / Product Name</th>
              <th className="text-left px-3 py-2 font-semibold text-gray-500 text-[10.5px] uppercase tracking-wider">Our Assortment</th>
              {CATEGORY_COLS.map(c => (
                <th key={c.key} className="text-left px-3 py-2 font-semibold text-gray-500 text-[10.5px] uppercase tracking-wider">{c.label}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {filteredRows.length === 0 ? (
              <tr><td colSpan={5} className="text-center py-8 text-gray-400 text-sm">No SKUs match this filter</td></tr>
            ) : filteredRows.map((r, i) => (
              <tr key={r.Product_Name} className={`border-b border-gray-100 hover:bg-blue-50/40 transition-colors ${i % 2 === 0 ? 'bg-white' : 'bg-gray-50/30'}`}>
                <td className="px-3 py-2 font-medium text-[#1A1D2E] max-w-[280px] truncate">{r.Product_Name}</td>
                <td className="px-3 py-2"><YesNoBadge value={r.Our_Assortment} /></td>
                {CATEGORY_COLS.map(c => (
                  <td key={c.key} className="px-3 py-2">
                    <YesNoBadge value={r[c.key]} onClick={() => openDrilldown(r.Product_Name, c.key, c.label)} />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {drill && (
        <DrilldownModal
          productName={drill.productName}
          categoryLabel={drill.categoryLabel}
          data={drillData}
          loading={drillLoading}
          onClose={() => { setDrill(null); setDrillData(null) }}
        />
      )}
    </div>
  )
}
