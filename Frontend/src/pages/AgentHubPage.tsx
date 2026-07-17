import { useState } from 'react'
import { Shield, MapPin, FileText } from 'lucide-react'
import WatchdogPanel    from '../components/agents/WatchdogPanel'
import LocalizationTable from '../components/agents/LocalizationTable'
import BriefGenerator   from '../components/agents/BriefGenerator'
import { useFilters }   from '../context/FilterContext'

type Tab = 'watchdog' | 'localization' | 'brief'

const TABS: { id: Tab; label: string; icon: React.ReactNode; desc: string }[] = [
  {
    id:    'watchdog',
    label: '🕵️ Watchdog',
    icon:  <Shield size={16} />,
    desc:  'Ranked exception digest — what needs attention today',
  },
  {
    id:    'localization',
    label: '🗺️ Localization',
    icon:  <MapPin size={16} />,
    desc:  'Cluster-aware divergence from global Continue/Delist decisions',
  },
  {
    id:    'brief',
    label: '📄 Stakeholder Brief',
    icon:  <FileText size={16} />,
    desc:  'Generate ready-to-share vendor & merchandising briefs',
  },
]

const SUB_CATS = [
  '', 'Shampoo', 'Conditioner', 'Hair Color', 'Hair Oil',
  'Hair Serum', 'Hair Mask', 'Treatment',
]
const CLUSTERS = ['', 'Premium Urban', 'Emerging Growth', 'Affluent Suburban', 'Digital-First Urban', 'Rural Remote']

export default function AgentHubPage() {
  const [activeTab, setActiveTab] = useState<Tab>('watchdog')

  const { filters: gf, setFilter, patchFilters } = useFilters()

  const watchdogFilters = {
    store_id: gf.store_id || undefined,
    sub_cat:  gf.sub_cat  || undefined,
    cluster:  gf.cluster  || undefined,
  }

  return (
    <div className="max-w-[1400px] mx-auto px-5 pb-10">
      {/* Page header */}
      <div className="py-5">
        <h1 className="text-[20px] font-extrabold text-[#1A1D2E]">🕵️ Agent Hub</h1>
        <p className="text-[13px] text-gray-500 mt-1">
          Three AI agents that surface what matters, detect cluster conflicts, and draft stakeholder briefs.
        </p>
      </div>

      {/* Global filter bar (for Watchdog tab) */}
      {activeTab === 'watchdog' && (
        <div className="flex flex-wrap gap-3 items-end mb-5 p-4 bg-white border border-gray-200 rounded-xl">
          <div>
            <label className="text-[11px] text-gray-500 block mb-1">Store ID</label>
            <input
              value={gf.store_id}
              onChange={e => setFilter('store_id', e.target.value)}
              placeholder="e.g. ST01"
              className="text-[12px] border border-gray-300 rounded-lg px-3 py-2 w-28"
            />
          </div>
          <div>
            <label className="text-[11px] text-gray-500 block mb-1">Sub-Category</label>
            <select
              value={gf.sub_cat}
              onChange={e => setFilter('sub_cat', e.target.value)}
              className="text-[12px] border border-gray-300 rounded-lg px-3 py-2 bg-white"
            >
              {SUB_CATS.map(s => <option key={s} value={s}>{s || 'All'}</option>)}
            </select>
          </div>
          <div>
            <label className="text-[11px] text-gray-500 block mb-1">Cluster</label>
            <select
              value={gf.cluster}
              onChange={e => setFilter('cluster', e.target.value)}
              className="text-[12px] border border-gray-300 rounded-lg px-3 py-2 bg-white"
            >
              {CLUSTERS.map(c => <option key={c} value={c}>{c || 'All clusters'}</option>)}
            </select>
          </div>
          <div>
            <label className="text-[11px] text-gray-500 block mb-1">Top N</label>
            <select
              value={gf.top_n}
              onChange={e => setFilter('top_n', Number(e.target.value))}
              className="text-[12px] border border-gray-300 rounded-lg px-3 py-2 bg-white"
            >
              {[5, 10, 20, 30, 50].map(n => <option key={n} value={n}>{n} items</option>)}
            </select>
          </div>
          <div className="flex flex-col justify-end">
            <button
              onClick={() => patchFilters({ store_id: '', sub_cat: '', cluster: '', top_n: 10 })}
              className="text-[11px] text-gray-400 hover:text-gray-700 border border-gray-200 rounded-lg px-3 py-2 bg-white"
            >
              ✕ Clear
            </button>
          </div>
        </div>
      )}

      {/* Tab bar */}
      <div className="flex gap-2 mb-5 flex-wrap">
        {TABS.map(tab => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={`flex items-center gap-2 px-4 py-2 rounded-full text-[12px] font-semibold border transition-all duration-150
              ${activeTab === tab.id
                ? 'bg-[#1A1D2E] text-white border-[#1A1D2E]'
                : 'bg-white text-gray-600 border-gray-200 hover:border-[#4F46E5] hover:text-[#4F46E5]'
              }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab description */}
      <div className="mb-5 text-[12px] text-gray-500 italic">
        {TABS.find(t => t.id === activeTab)?.desc}
      </div>

      {/* Tab content */}
      {activeTab === 'watchdog'     && <WatchdogPanel    filters={watchdogFilters} topN={gf.top_n} />}
      {activeTab === 'localization' && <LocalizationTable />}
      {activeTab === 'brief'        && <BriefGenerator   />}
    </div>
  )
}
