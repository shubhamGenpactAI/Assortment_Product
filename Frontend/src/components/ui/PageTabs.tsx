interface Tab {
  key:   string
  label: string
  icon?: string
  sub?:  string
}

interface Props {
  tabs:     Tab[]
  active:   string
  onChange: (key: string) => void
}

export default function PageTabs({ tabs, active, onChange }: Props) {
  return (
    <div className="flex flex-wrap gap-2 mb-4">
      {tabs.map(t => {
        const isActive = active === t.key
        return (
          <button
            key={t.key}
            type="button"
            onClick={() => onChange(t.key)}
            className={`flex items-center gap-1.5 px-4 py-2 rounded-full text-[12.5px] font-semibold border transition-all
              ${isActive
                ? 'bg-[#1A1D2E] text-white border-[#1A1D2E]'
                : 'bg-white text-gray-600 border-gray-200 hover:bg-gray-50'}`}
          >
            {t.icon && <span>{t.icon}</span>}
            {t.label}
            {t.sub && (
              <span className={`text-[10.5px] font-medium ${isActive ? 'text-white/60' : 'text-gray-400'}`}>
                &bull; {t.sub}
              </span>
            )}
          </button>
        )
      })}
    </div>
  )
}
