import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Eye, EyeOff } from 'lucide-react'

// Illustrative only — no backend auth, no email-domain restriction.
// Any input (or none) proceeds straight into the app.

const FEATURES = [
  'Category Intelligence — Health, Delist & GMROI scoring',
  'Decision Hub — AI Copilot with approval workflows',
  'New SKU Intelligence — Forecast & analog matching',
]

const BAR_ROWS = [
  { color: 'bg-[#F2A93B]', width: '100%' },
  { color: 'bg-amber-400', width: '78%' },
  { color: 'bg-red-400',   width: '52%' },
  { color: 'bg-emerald-400', width: '66%' },
  { color: 'bg-red-400',   width: '38%' },
  { color: 'bg-emerald-400', width: '58%' },
]

export default function LoginPage() {
  const navigate = useNavigate()
  const [showPassword, setShowPassword] = useState(false)
  const [remember, setRemember] = useState(false)

  const enterApp = (e: React.FormEvent) => {
    e.preventDefault()
    navigate('/workspace')
  }

  return (
    <div className="min-h-screen flex flex-col lg:flex-row bg-[#F4F6FA]">
      {/* Left marketing panel */}
      <div className="lg:w-1/2 bg-[#1A1D2E] text-white flex flex-col justify-between p-10 lg:p-16">
        <div>
          <div className="flex items-center gap-3 mb-1">
            <img src="/Genpact.jpg" alt="Genpact" className="h-8 object-contain" />
          </div>
          <p className="text-[#F2A93B] text-[11px] font-bold tracking-widest uppercase mt-4">
            Retail Assortment Optimization
          </p>

          <h1 className="text-3xl lg:text-4xl font-extrabold mt-8 leading-tight">
            Make smarter assortment decisions.
          </h1>
          <p className="text-[#C9CCD6] text-sm mt-3 max-w-md">
            AI-powered insights for category managers, reviewers and administrators.
          </p>

          <ul className="mt-6 space-y-2">
            {FEATURES.map(f => (
              <li key={f} className="flex items-start gap-2 text-[13px] text-[#E4E6EE]">
                <span className="mt-1.5 w-1.5 h-1.5 rounded-full bg-[#F2A93B] shrink-0" />
                {f}
              </li>
            ))}
          </ul>

          <div className="mt-10 bg-white/5 border border-white/10 rounded-xl p-4 space-y-2.5 max-w-sm">
            {BAR_ROWS.map((r, i) => (
              <div key={i} className="flex items-center gap-2">
                <div className={`w-2.5 h-2.5 rounded-full ${r.color}`} />
                <div className="flex-1 h-2 bg-white/10 rounded-full overflow-hidden">
                  <div className={`h-full rounded-full ${r.color}`} style={{ width: r.width }} />
                </div>
              </div>
            ))}
          </div>
        </div>

        <p className="text-[11px] text-[#8E93A6] mt-10">
          © Genpact · Retail Assortment Platform · For internal use only.
        </p>
      </div>

      {/* Right sign-in panel */}
      <div className="lg:w-1/2 flex items-center justify-center p-8 lg:p-16">
        <form onSubmit={enterApp} className="w-full max-w-md bg-white rounded-2xl shadow-sm border border-gray-100 p-8">
          <h2 className="text-2xl font-extrabold text-[#1A1D2E]">Welcome back</h2>
          <p className="text-[13px] text-gray-400 mt-1 mb-6">Sign in to your account to continue.</p>

          <button
            type="submit"
            className="w-full flex items-center justify-center gap-2 bg-[#1A1D2E] text-white font-bold text-[13px] rounded-xl py-3 hover:bg-[#242840] transition-colors"
          >
            <img src="/Genpact.jpg" alt="" className="h-4 object-contain" />
            Sign in with Genpact SSO
          </button>

          <div className="flex items-center gap-3 my-5">
            <div className="flex-1 h-px bg-gray-200" />
            <span className="text-[11px] text-gray-400">or continue with email</span>
            <div className="flex-1 h-px bg-gray-200" />
          </div>

          <label className="block text-[12px] font-semibold text-gray-600 mb-1">Email address</label>
          <input
            type="email"
            placeholder="you@genpact.com"
            className="w-full border border-gray-200 rounded-lg px-3 py-2.5 text-[13px] mb-4 focus:outline-none focus:border-[#4F46E5]"
          />

          <div className="flex items-center justify-between mb-1">
            <label className="text-[12px] font-semibold text-gray-600">Password</label>
            <button type="button" className="text-[11.5px] font-semibold text-[#F2A93B] hover:underline">
              Forgot password?
            </button>
          </div>
          <div className="relative mb-4">
            <input
              type={showPassword ? 'text' : 'password'}
              placeholder="••••••••"
              className="w-full border border-gray-200 rounded-lg px-3 py-2.5 pr-10 text-[13px] focus:outline-none focus:border-[#4F46E5]"
            />
            <button
              type="button"
              onClick={() => setShowPassword(v => !v)}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
            >
              {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
            </button>
          </div>

          <label className="flex items-center gap-2 mb-5 cursor-pointer">
            <input
              type="checkbox"
              checked={remember}
              onChange={e => setRemember(e.target.checked)}
              className="rounded border-gray-300"
            />
            <span className="text-[12.5px] text-gray-600">Remember this device for 30 days</span>
          </label>

          <button
            type="submit"
            className="w-full bg-[#F2A93B] text-[#1A1D2E] font-bold text-[14px] rounded-xl py-3 hover:bg-[#e09c2f] transition-colors"
          >
            Sign In
          </button>

          <p className="text-center text-[12.5px] text-gray-500 mt-4">
            Don't have an account?{' '}
            <button type="button" onClick={enterApp} className="text-[#F2A93B] font-semibold hover:underline">
              Request Access
            </button>
          </p>

          <p className="text-center text-[11px] text-gray-400 mt-6">
            Having trouble signing in? Contact your administrator.
          </p>
        </form>
      </div>
    </div>
  )
}
