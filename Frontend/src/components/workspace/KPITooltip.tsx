import { useState, useRef, useCallback } from 'react'
import { createPortal } from 'react-dom'
import { Info } from 'lucide-react'

interface Props {
  label:    string
  tooltip:  string
  children?: React.ReactNode
}

export function KPITooltip({ label, tooltip, children }: Props) {
  const [show, setShow] = useState(false)
  const [pos,  setPos]  = useState({ top: 0, left: 0 })
  const btnRef = useRef<HTMLButtonElement>(null)

  const handleEnter = useCallback(() => {
    if (btnRef.current) {
      const r = btnRef.current.getBoundingClientRect()
      setPos({ top: r.top - 10, left: r.left + r.width / 2 })
    }
    setShow(true)
  }, [])

  return (
    <div className="inline-flex items-center gap-1">
      <span className="text-[10px] font-semibold text-gray-500 uppercase tracking-wider">{label}</span>
      {children}
      <button
        ref={btnRef}
        className="text-gray-300 hover:text-indigo-400 transition-colors flex-shrink-0"
        onMouseEnter={handleEnter}
        onMouseLeave={() => setShow(false)}
        onClick={(e) => e.stopPropagation()}
        aria-label={`Info: ${label}`}
      >
        <Info size={11} />
      </button>

      {show && createPortal(
        <div
          className="pointer-events-none animate-fade-in"
          style={{ position: 'fixed', top: pos.top, left: pos.left, transform: 'translate(-50%, -100%)', zIndex: 9999 }}
        >
          <div className="w-60 bg-[#1A1D2E] text-white text-[11px] leading-relaxed rounded-xl p-3 shadow-2xl">
            {tooltip}
            <div className="absolute top-full left-1/2 -translate-x-1/2 border-4 border-transparent border-t-[#1A1D2E]" />
          </div>
        </div>,
        document.body
      )}
    </div>
  )
}
