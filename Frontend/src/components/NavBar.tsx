import { useState } from 'react'
import { NavLink, useNavigate } from 'react-router-dom'

const NAV = [
  { to: '/workspace',    label: '🧠 Category Intelligence' },
  { to: '/decision-hub', label: '⚡ Decision Hub'          },
  { to: '/new-sku',      label: '✨ New SKU Intelligence'  },
  { to: '/agent-hub',    label: '🕵️ Agent Hub'            },
  { to: '/assortment-decisions', label: '📋 Assortment Decision' },
]

export default function NavBar() {
  const [menuOpen, setMenuOpen] = useState(false)
  const navigate = useNavigate()

  return (
    <header className="fixed top-0 left-0 right-0 z-50 bg-[#1A1D2E] border-b-4 border-[#F2A93B] shadow-lg">
      {/* Top row: logo + brand + meta */}
      <div className="flex items-center gap-3 px-5 h-[52px]">
        <img src="/Genpact.jpg" alt="Genpact" className="h-8 object-contain" />
        <div className="w-px h-7 bg-[#F2A93B]/40" />
        <span className="text-white font-extrabold text-lg tracking-tight">
          🛒 &nbsp;Retail Assortment Optimization
        </span>
        <div className="flex-1" />
        <span className="text-[#8E93A6] text-xs hidden md:block">
          Hair Care · Category Growth
        </span>
        <div className="flex-1 hidden md:block" />
        <div className="relative">
          <button
            type="button"
            onClick={() => setMenuOpen(o => !o)}
            className="flex items-center gap-1.5 text-[#F2A93B] text-sm font-bold hover:text-[#ffc35f] transition-colors"
          >
            👤 Category Manager
            <span className={`text-[10px] transition-transform duration-150 ${menuOpen ? 'rotate-180' : ''}`}>▾</span>
          </button>

          {menuOpen && (
            <>
              <div className="fixed inset-0 z-40" onClick={() => setMenuOpen(false)} />
              <div className="absolute right-0 top-8 z-50 w-52 bg-white rounded-xl shadow-xl border border-gray-100 overflow-hidden">
                <div className="px-4 py-3 border-b border-gray-100">
                  <p className="text-[13px] font-bold text-[#1A1D2E]">Category Manager</p>
                  <p className="text-[11px] text-gray-400">Hair Care · Category Growth</p>
                </div>
                <button
                  type="button"
                  onClick={() => { setMenuOpen(false); navigate('/login') }}
                  className="w-full text-left px-4 py-2.5 text-[12.5px] text-gray-600 hover:bg-gray-50 transition-colors"
                >
                  🚪 Sign out
                </button>
              </div>
            </>
          )}
        </div>
      </div>

      {/* Bottom row: nav pills */}
      <nav className="flex gap-1 px-5 pb-2 overflow-x-auto scrollbar-hide">
        {NAV.map(({ to, label }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            className={({ isActive }) =>
              `whitespace-nowrap text-[11.5px] font-semibold px-3.5 py-1.5 rounded-full
               transition-all duration-150 border
               ${isActive
                 ? 'bg-[#F2A93B] text-[#1A1D2E] border-[#F2A93B]'
                 : 'text-[#C9CCD6] border-transparent hover:bg-white/10 hover:text-white'
               }`
            }
          >
            {label}
          </NavLink>
        ))}
      </nav>
    </header>
  )
}
