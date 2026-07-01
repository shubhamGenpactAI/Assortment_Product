import { NavLink } from 'react-router-dom'

const NAV = [
  { to: '/workspace',    label: '🧠 Category Intelligence'     },
  { to: '/',             label: '📊 Dashboard'                },
  { to: '/decision-hub', label: '⚡ Decision Hub'              },
  { to: '/sku',          label: '📋 SKU Performance'           },
  { to: '/new-sku',      label: '🧠 New SKU Intelligence'       },
  { to: '/data-quality', label: '🩺 Data Quality'              },
]

export default function NavBar() {
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
        <span className="text-[#F2A93B] text-sm font-bold">👤 Category Manager</span>
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
