import { useState, useMemo } from 'react'
import { SlidersHorizontal, X, ChevronDown } from 'lucide-react'
import type { SKURecommendation, SKUMasterInfo, WorkspaceFilters } from '../../types/assortment'

interface Props {
  rows:          SKURecommendation[]
  skuMaster:     Record<string, SKUMasterInfo>
  storeClusters: Array<{ Store_ID: string; Cluster_ID: number; Cluster_Label: string }>
  filters:       WorkspaceFilters
  onChange:      (f: WorkspaceFilters) => void
}

function uniq(arr: (string | null | undefined)[]): string[] {
  return Array.from(new Set(arr.filter(Boolean) as string[])).sort()
}

interface DropdownProps {
  label:    string
  value:    string
  options:  string[]
  onChange: (v: string) => void
  className?: string
}

function FilterDropdown({ label, value, options, onChange, className = '' }: DropdownProps) {
  return (
    <div className={`flex flex-col gap-0.5 flex-none ${className}`}>
      <label className="text-[9px] font-bold uppercase tracking-widest text-gray-400 truncate px-1">{label}</label>
      <div className="relative">
        <select
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="w-full appearance-none bg-white border border-gray-200 rounded-lg pl-2.5 pr-6 py-1.5 text-[11px]
                     font-medium text-gray-700 focus:outline-none focus:ring-2 focus:ring-indigo-400
                     focus:border-indigo-400 cursor-pointer hover:border-gray-300 transition-colors"
        >
          <option value="">All</option>
          {options.map((o) => <option key={o} value={o}>{o.replace(/_/g, ' ')}</option>)}
        </select>
        <ChevronDown size={11} className="absolute right-1.5 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none" />
      </div>
    </div>
  )
}

export function SmartFilterBar({ rows, skuMaster, storeClusters, filters, onChange }: Props) {
  const [expanded, setExpanded] = useState(false)

  const opts = useMemo(() => {
    const brandSet    = new Set<string>()
    const categorySet = new Set<string>()
    Object.values(skuMaster).forEach((s) => {
      if (s.Brand)    brandSet.add(s.Brand)
      if (s.Category) categorySet.add(s.Category)
    })
    const clusterSet = new Set(storeClusters.map((c) => c.Cluster_Label))

    return {
      granularity_level: uniq(rows.map((r) => r.granularity_level)),
      Brand:             Array.from(brandSet).sort(),
      Category:          Array.from(categorySet).sort(),
      Sub_Category:      uniq(rows.map((r) => r.Sub_Category)),
      Decision:          uniq(rows.map((r) => r.Decision)),
      Health_Band:       uniq(rows.map((r) => r.Health_Band)),
      Delist_Band:       uniq(rows.map((r) => r.Delist_Band)),
      GMROI_Band:        uniq(rows.map((r) => r.GMROI_Band)),
      Basket_Role:       uniq(rows.map((r) => r.Basket_Role)),
      ABC_Class:         uniq(rows.map((r) => r.ABC_Class)),
      Store_Name:        uniq(rows.filter((r) => r.granularity_level === 'Store').map((r) => r.granularity_value)),
      Cluster_Name:      Array.from(clusterSet).sort(),
      Region_Name:       uniq(rows.filter((r) => r.granularity_level === 'Geography').map((r) => r.granularity_value)),
    }
  }, [rows, skuMaster, storeClusters])

  const set = (key: keyof WorkspaceFilters, val: string) =>
    onChange({ ...filters, [key]: val || undefined })

  // Count active filters (excluding granularity_level and searchTerm as they're always shown)
  const activeCount = Object.entries(filters).filter(
    ([k, v]) => k !== 'granularity_level' && k !== 'searchTerm' && v && v !== ''
  ).length

  const clearAll = () =>
    onChange({ granularity_level: filters.granularity_level, searchTerm: filters.searchTerm })

  return (
    <div className="bg-white border-b border-gray-100 px-4 py-2.5 shadow-sm">
      {/* Primary row */}
      <div className="flex items-end gap-2.5">
        {/* Search — 20% narrower than flex-1 */}
        <div className="flex flex-col gap-0.5 flex-none w-[200px]">
          <label className="text-[9px] font-bold uppercase tracking-widest text-gray-400 px-1">Search</label>
          <input
            type="text"
            placeholder="SKU ID or product name…"
            value={filters.searchTerm ?? ''}
            onChange={(e) => onChange({ ...filters, searchTerm: e.target.value })}
            className="w-full bg-gray-50 border border-gray-200 rounded-lg pl-3 pr-3 py-1.5 text-[11px]
                       text-gray-700 focus:outline-none focus:ring-2 focus:ring-indigo-400 focus:bg-white transition-all"
          />
        </div>

        <FilterDropdown
          label="View Level"
          value={filters.granularity_level ?? ''}
          options={opts.granularity_level}
          onChange={(v) => set('granularity_level', v)}
          className="w-[110px]"
        />
        <FilterDropdown
          label="Brand"
          value={filters.Brand ?? ''}
          options={opts.Brand}
          onChange={(v) => set('Brand', v)}
          className="w-[110px]"
        />
        <FilterDropdown
          label="Category"
          value={filters.Category ?? ''}
          options={opts.Category}
          onChange={(v) => set('Category', v)}
          className="w-[110px]"
        />
        <FilterDropdown
          label="Sub-Category"
          value={filters.Sub_Category ?? ''}
          options={opts.Sub_Category}
          onChange={(v) => set('Sub_Category', v)}
          className="w-[120px]"
        />
        <FilterDropdown
          label="Decision"
          value={filters.Decision ?? ''}
          options={opts.Decision}
          onChange={(v) => set('Decision', v)}
          className="w-[110px]"
        />

        {/* More filters toggle */}
        <div className="flex flex-col gap-0.5 flex-none">
          <label className="text-[9px] font-bold uppercase tracking-widest text-transparent px-1 select-none">·</label>
          <button
            onClick={() => setExpanded((p) => !p)}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-[11px] font-semibold transition-all whitespace-nowrap
              ${expanded
                ? 'bg-indigo-600 text-white border-indigo-600'
                : 'bg-white text-gray-600 border-gray-200 hover:border-indigo-300 hover:text-indigo-600'
              }`}
          >
            <SlidersHorizontal size={12} />
            Filters
            {activeCount > 0 && (
              <span className="bg-[#F2A93B] text-[#1A1D2E] text-[9px] font-black rounded-full w-4 h-4 flex items-center justify-center">
                {activeCount}
              </span>
            )}
          </button>
        </div>

        {activeCount > 0 && (
          <div className="flex flex-col gap-0.5 flex-none">
            <label className="text-[9px] font-bold uppercase tracking-widest text-transparent px-1 select-none">·</label>
            <button
              onClick={clearAll}
              className="flex items-center gap-1 text-[11px] text-gray-400 hover:text-red-500 transition-colors whitespace-nowrap py-1.5"
            >
              <X size={11} /> Clear
            </button>
          </div>
        )}
      </div>

      {/* Expanded secondary row — 8 filters on a single line */}
      {expanded && (
        <div className="grid grid-cols-8 gap-2 pt-2.5 mt-2 border-t border-gray-100 animate-fade-in">
          <FilterDropdown label="Health Band"  value={filters.Health_Band  ?? ''} options={opts.Health_Band}  onChange={(v) => set('Health_Band',  v)} />
          <FilterDropdown label="Delist Band"  value={filters.Delist_Band  ?? ''} options={opts.Delist_Band}  onChange={(v) => set('Delist_Band',  v)} />
          <FilterDropdown label="GMROI Band"   value={filters.GMROI_Band   ?? ''} options={opts.GMROI_Band}   onChange={(v) => set('GMROI_Band',   v)} />
          <FilterDropdown label="Basket Role"  value={filters.Basket_Role  ?? ''} options={opts.Basket_Role}  onChange={(v) => set('Basket_Role',  v)} />
          <FilterDropdown label="ABC Class"    value={filters.ABC_Class    ?? ''} options={opts.ABC_Class}    onChange={(v) => set('ABC_Class',    v)} />
          <FilterDropdown label="Store Name"   value={filters.Store_Name   ?? ''} options={opts.Store_Name}   onChange={(v) => set('Store_Name',   v)} />
          <FilterDropdown label="Cluster Name" value={filters.Cluster_Name ?? ''} options={opts.Cluster_Name} onChange={(v) => set('Cluster_Name', v)} />
          <FilterDropdown label="Region Name"  value={filters.Region_Name  ?? ''} options={opts.Region_Name}  onChange={(v) => set('Region_Name',  v)} />
        </div>
      )}
    </div>
  )
}
