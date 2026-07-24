import { useState } from 'react'
import { useFilters } from '../../context/FilterContext'
import { Loader2, Copy, Download, Sparkles, History, ChevronDown, ChevronUp } from 'lucide-react'
import {
  generateBrief, fetchBriefs, streamBriefPolish,
  Brief, BriefSection, VendorNegotiationRow,
} from '../../api/agentsApi'

const BRIEF_TYPES = [
  { value: 'vendor_negotiation', label: '🤝 Vendor Negotiation' },
  { value: 'cross_sell',         label: '🛒 Cross-Sell Opportunity' },
  { value: 'delist_rationale',   label: '🗑️ Delist Rationale' },
]
const SUB_CATS = [
  '', 'Shampoo', 'Conditioner', 'Hair Color', 'Hair Oil',
  'Hair Serum', 'Hair Mask', 'Treatment',
]
const BRANDS = [
  '', 'EarthTress', 'AquaSilk', 'NimbusPure', 'VelvetRoot',
  'GlossRoot', 'LustraBotanix', 'HydraCore',
]

function SectionCard({ section, open, toggle }: {
  section: BriefSection; open: boolean; toggle: () => void
}) {
  return (
    <div className="border border-gray-200 rounded-xl overflow-hidden">
      <button
        className="w-full flex items-center justify-between px-4 py-3 bg-gray-50 hover:bg-gray-100 text-left"
        onClick={toggle}
      >
        <span className="font-semibold text-[13px] text-[#1A1D2E]">{section.heading}</span>
        {open ? <ChevronUp size={16} className="text-gray-400" /> : <ChevronDown size={16} className="text-gray-400" />}
      </button>
      {open && (
        <div className="px-4 py-3 bg-white text-[12px] text-gray-700 leading-relaxed whitespace-pre-wrap">
          {section.body}
        </div>
      )}
    </div>
  )
}

const RATING_BADGE: Record<string, string> = {
  A: 'bg-green-100 text-green-700',
  B: 'bg-amber-100 text-amber-700',
  C: 'bg-red-100 text-red-700',
}

function VendorNegotiationTable({ rows }: { rows: VendorNegotiationRow[] }) {
  return (
    <div className="bg-white border border-gray-200 rounded-xl overflow-hidden">
      <div className="px-4 py-3 bg-gray-50 border-b border-gray-200">
        <h4 className="text-[13px] font-bold text-[#1A1D2E]">Vendor Negotiation — SKU Detail</h4>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-[11px] whitespace-nowrap">
          <thead>
            <tr className="bg-[#1A1D2E] text-white">
              {[
                'Supplier', 'SKU ID', 'EAN ID', 'SKU Name', 'Lead Time Target (Days)',
                'Fill Rate (%)', 'Supplier Rating', 'Sell Through', 'Margin %',
                'Sales ($)', 'Confidence Score',
              ].map(h => (
                <th key={h} className="px-3 py-2 text-left font-semibold">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={r.sku_id} className={i % 2 ? 'bg-gray-50' : 'bg-white'}>
                <td className="px-3 py-2">{r.supplier}</td>
                <td className="px-3 py-2 font-medium text-[#1A1D2E]">{r.sku_id}</td>
                <td className="px-3 py-2 text-gray-500">{r.ean_id}</td>
                <td className="px-3 py-2 whitespace-normal min-w-[180px]">{r.sku_name}</td>
                <td className="px-3 py-2 text-center">{r.lead_time_target_days ?? '—'}</td>
                <td className="px-3 py-2 text-center">{r.fill_rate_pct != null ? `${r.fill_rate_pct}%` : '—'}</td>
                <td className="px-3 py-2 text-center">
                  <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${RATING_BADGE[r.supplier_rating] ?? 'bg-gray-100 text-gray-600'}`}>
                    {r.supplier_rating || '—'}
                  </span>
                </td>
                <td className="px-3 py-2 text-center">{r.sell_through_pct != null ? `${r.sell_through_pct}%` : '—'}</td>
                <td className="px-3 py-2 text-center">{r.margin_pct != null ? `${r.margin_pct}%` : '—'}</td>
                <td className="px-3 py-2 text-right">
                  {r.sales_usd.toLocaleString(undefined, { maximumFractionDigits: 0 })}
                </td>
                <td className="px-3 py-2 text-center">{r.confidence_score ?? '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function BriefViewer({ brief, onPolished }: { brief: Brief; onPolished?: (b: Brief) => void }) {
  const [openSections, setOpenSections] = useState<Record<number, boolean>>({ 0: true })
  const [polishing,    setPolishing]    = useState(false)
  const [polishText,   setPolishText]   = useState('')
  const [copied,       setCopied]       = useState(false)

  const toggle = (i: number) => setOpenSections(prev => ({ ...prev, [i]: !prev[i] }))

  const copyMarkdown = () => {
    navigator.clipboard.writeText(brief.export.markdown)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  const downloadMarkdown = () => {
    const blob = new Blob([brief.export.markdown], { type: 'text/markdown' })
    const url  = URL.createObjectURL(blob)
    const a    = document.createElement('a')
    a.href     = url
    a.download = `brief_${brief.brief_id}.md`
    a.click()
    URL.revokeObjectURL(url)
  }

  const polish = () => {
    setPolishText('')
    setPolishing(true)
    streamBriefPolish(
      brief.brief_id,
      tok => setPolishText(p => p + tok),
      ()  => setPolishing(false),
      err => { setPolishText(err); setPolishing(false) },
    )
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <div className="text-[11px] text-gray-500">
            {BRIEF_TYPES.find(t => t.value === brief.brief_type)?.label ?? brief.brief_type}
            {' '}·{' '}
            {brief.scope.brand || brief.scope.sub_cat || 'All scope'}
          </div>
          <div className="text-[11px] text-gray-400">
            Generated {brief.generated_at?.slice(0, 16).replace('T', ' ')} by {brief.generated_by}
          </div>
        </div>
        <div className="flex gap-2">
          <button
            onClick={polish}
            disabled={polishing}
            className="flex items-center gap-1.5 px-3 py-2 text-[12px] bg-[#4F46E5] text-white rounded-lg hover:opacity-90 disabled:opacity-60 font-medium"
          >
            {polishing ? <Loader2 size={12} className="animate-spin" /> : <Sparkles size={12} />}
            {polishing ? 'Polishing…' : 'Polish Tone (AI)'}
          </button>
          <button
            onClick={copyMarkdown}
            className="flex items-center gap-1.5 px-3 py-2 text-[12px] border border-gray-300 rounded-lg hover:bg-gray-50"
          >
            <Copy size={12} /> {copied ? 'Copied!' : 'Copy'}
          </button>
          <button
            onClick={downloadMarkdown}
            className="flex items-center gap-1.5 px-3 py-2 text-[12px] border border-gray-300 rounded-lg hover:bg-gray-50"
          >
            <Download size={12} /> Export .md
          </button>
        </div>
      </div>

      {/* Vendor Negotiation SKU table — only for vendor_negotiation briefs with a non-empty result */}
      {brief.brief_type === 'vendor_negotiation' && brief.vendor_table && brief.vendor_table.length > 0 && (
        <VendorNegotiationTable rows={brief.vendor_table} />
      )}

      {/* Polished output */}
      {(polishText || polishing) && (
        <div className="bg-gradient-to-br from-[#1A1D2E] to-[#2D3250] rounded-xl p-4 text-white">
          <div className="text-[11px] text-[#F2A93B] font-bold mb-2">✨ AI-Polished Version</div>
          <p className="text-[12px] leading-relaxed whitespace-pre-wrap text-gray-200">
            {polishText}
            {polishing && <span className="animate-pulse">▌</span>}
          </p>
        </div>
      )}

      {/* Sections */}
      {brief.sections.map((s, i) => (
        <SectionCard
          key={i}
          section={s}
          open={!!openSections[i]}
          toggle={() => toggle(i)}
        />
      ))}
    </div>
  )
}

export default function BriefGenerator() {
  const { filters: gf, setFilter } = useFilters()
  const briefType = gf.brief_type
  const brand     = gf.brand
  const subCat    = gf.sub_cat

  const [generating,  setGenerating]  = useState(false)
  const [brief,       setBrief]       = useState<Brief | null>(null)
  const [history,     setHistory]     = useState<any[]>([])
  const [showHistory, setShowHistory] = useState(false)

  const generate = async () => {
    setGenerating(true)
    setBrief(null)
    try {
      const result = await generateBrief({
        brief_type: briefType,
        brand:      brand  || undefined,
        sub_cat:    subCat || undefined,
      })
      setBrief(result)
    } catch (e) {
      console.error(e)
    } finally {
      setGenerating(false)
    }
  }

  const loadHistory = () => {
    fetchBriefs(brand || undefined, subCat || undefined)
      .then(setHistory)
      .catch(console.error)
    setShowHistory(true)
  }

  return (
    <div className="space-y-4">
      {/* Generation form */}
      <div className="bg-white border border-gray-200 rounded-xl p-5">
        <h3 className="text-[13px] font-bold text-[#1A1D2E] mb-4">Generate Brief</h3>
        <div className="flex flex-wrap gap-4 mb-4">
          <div>
            <label className="text-[11px] text-gray-500 block mb-1">Brief Type</label>
            <select
              value={briefType}
              onChange={e => setFilter('brief_type', e.target.value)}
              className="text-[12px] border border-gray-300 rounded-lg px-3 py-2 bg-white min-w-[220px]"
            >
              {BRIEF_TYPES.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
            </select>
          </div>
          <div>
            <label className="text-[11px] text-gray-500 block mb-1">Brand (optional)</label>
            <select
              value={brand}
              onChange={e => setFilter('brand', e.target.value)}
              className="text-[12px] border border-gray-300 rounded-lg px-3 py-2 bg-white min-w-[160px]"
            >
              {BRANDS.map(b => <option key={b} value={b}>{b || 'Any brand'}</option>)}
            </select>
          </div>
          <div>
            <label className="text-[11px] text-gray-500 block mb-1">Sub-Category (optional)</label>
            <select
              value={subCat}
              onChange={e => setFilter('sub_cat', e.target.value)}
              className="text-[12px] border border-gray-300 rounded-lg px-3 py-2 bg-white min-w-[200px]"
            >
              {SUB_CATS.map(s => <option key={s} value={s}>{s || 'All sub-categories'}</option>)}
            </select>
          </div>
        </div>
        <div className="flex gap-3">
          <button
            onClick={generate}
            disabled={generating}
            className="flex items-center gap-2 px-5 py-2.5 bg-[#F2A93B] text-[#1A1D2E] text-[13px] font-bold rounded-xl hover:opacity-90 disabled:opacity-60"
          >
            {generating ? <Loader2 size={14} className="animate-spin" /> : '📄'}
            {generating ? 'Generating…' : 'Generate Brief'}
          </button>
          <button
            onClick={loadHistory}
            className="flex items-center gap-2 px-4 py-2.5 border border-gray-300 text-[12px] rounded-xl hover:bg-gray-50 text-gray-600"
          >
            <History size={14} /> Recent Briefs
          </button>
        </div>
      </div>

      {/* History */}
      {showHistory && (
        <div className="bg-white border border-gray-200 rounded-xl p-4">
          <div className="flex items-center justify-between mb-3">
            <h4 className="text-[13px] font-bold text-[#1A1D2E]">Recent Briefs</h4>
            <button onClick={() => setShowHistory(false)} className="text-[11px] text-gray-400 hover:text-gray-600">Close</button>
          </div>
          {history.length === 0 ? (
            <p className="text-[12px] text-gray-400 italic">No briefs generated yet.</p>
          ) : (
            <div className="space-y-2">
              {history.map(b => (
                <div key={b.brief_id} className="flex items-center justify-between border border-gray-100 rounded-lg px-3 py-2 hover:bg-gray-50">
                  <div>
                    <span className="text-[12px] font-medium text-[#1A1D2E]">
                      {BRIEF_TYPES.find(t => t.value === b.brief_type)?.label ?? b.brief_type}
                    </span>
                    <span className="text-[11px] text-gray-500 ml-2">
                      {b.scope?.brand || b.scope?.sub_cat || 'All scope'}
                    </span>
                  </div>
                  <span className="text-[11px] text-gray-400">{b.generated_at?.slice(0, 16).replace('T', ' ')}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Generated brief */}
      {brief && (
        <div className="bg-white border border-gray-200 rounded-xl p-5">
          <BriefViewer brief={brief} />
        </div>
      )}
    </div>
  )
}
