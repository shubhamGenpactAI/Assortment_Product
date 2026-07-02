import { useState, useRef, useEffect } from 'react'
import { Loader2, Send, RefreshCw, Sparkles } from 'lucide-react'
import { streamCopilot } from '../../api/decisionHubApi'

interface Filters { store_id?: string; sub_cat?: string; cluster?: string }
interface Props   { filters: Filters }

const PLACEHOLDER_LINES = [
  'Generating ranked recommendations from your live data…',
]

export default function AICopilot({ filters }: Props) {
  const [output,   setOutput]   = useState('')
  const [loading,  setLoading]  = useState(false)
  const [question, setQuestion] = useState('')
  const [error,    setError]    = useState('')
  const scrollRef  = useRef<HTMLDivElement>(null)
  const abortRef   = useRef(false)

  useEffect(() => {
    if (scrollRef.current) scrollRef.current.scrollTop = scrollRef.current.scrollHeight
  }, [output])

  const generate = async (q = '') => {
    abortRef.current = false
    setLoading(true)
    setOutput('')
    setError('')

    await streamCopilot(
      filters,
      q,
      tok => {
        if (!abortRef.current) setOutput(prev => prev + tok)
      },
      () => setLoading(false),
      err => { setError(err); setLoading(false) },
    )
  }

  const handleAsk = () => {
    if (!question.trim()) return
    generate(question)
    setQuestion('')
  }

  const renderMarkdown = (text: string) =>
    text
      .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
      .replace(/\n/g, '<br />')

  return (
    <div className="flex flex-col h-full min-h-[380px]">
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Sparkles size={15} className="text-[#F2A93B]" />
          <span className="text-[12px] font-bold text-[#1A1D2E] uppercase tracking-wider">AI Copilot</span>
          <span className="text-[9px] bg-[#F2A93B]/20 text-[#B8760A] px-1.5 py-0.5 rounded-full font-semibold">OpenAI o3-mini</span>
        </div>
        <button
          onClick={() => generate()}
          disabled={loading}
          className="flex items-center gap-1 text-[11px] font-semibold text-[#4F46E5] hover:text-[#4338CA] disabled:opacity-40"
        >
          <RefreshCw size={12} className={loading ? 'animate-spin' : ''} />
          {loading ? 'Generating…' : 'Regenerate'}
        </button>
      </div>

      {/* Output area */}
      <div
        ref={scrollRef}
        className="flex-1 overflow-y-auto rounded-xl bg-[#F8F9FB] border border-gray-200 px-4 py-3 text-[12.5px] text-[#1A1D2E] leading-relaxed min-h-[260px] max-h-[340px]"
      >
        {!output && !loading && !error && (
          <div className="flex flex-col items-center justify-center h-full gap-3 text-gray-400">
            <Sparkles size={24} className="text-[#F2A93B]" />
            <p className="text-sm text-center">
              Click <strong className="text-[#4F46E5]">Generate Insights</strong> to get AI-powered recommendations<br />
              based on your current forecast and inventory data.
            </p>
            <button
              onClick={() => generate()}
              className="mt-1 px-4 py-2 bg-[#4F46E5] text-white rounded-lg text-[12px] font-semibold hover:bg-[#4338CA] transition-colors"
            >
              ⚡ Generate Insights
            </button>
          </div>
        )}
        {loading && !output && (
          <div className="flex items-center gap-2 text-gray-400 mt-4">
            <Loader2 size={14} className="animate-spin" />
            <span className="text-sm">{PLACEHOLDER_LINES[0]}</span>
          </div>
        )}
        {error && (
          <div className="text-red-500 text-sm bg-red-50 border border-red-200 rounded-lg px-3 py-2">
            ⚠ {error}
          </div>
        )}
        {output && (
          <div
            className="prose-sm"
            dangerouslySetInnerHTML={{ __html: renderMarkdown(output) }}
          />
        )}
        {loading && output && (
          <span className="inline-block w-2 h-4 bg-[#4F46E5] animate-pulse ml-0.5 rounded-sm" />
        )}
      </div>

      {/* Question input */}
      <div className="flex gap-2 mt-3">
        <input
          type="text"
          value={question}
          onChange={e => setQuestion(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && handleAsk()}
          placeholder="Ask a question… e.g. Which SKUs should I replenish first?"
          className="flex-1 border border-gray-200 rounded-lg px-3 py-2 text-[12px] outline-none focus:border-[#4F46E5] focus:ring-1 focus:ring-[#4F46E5]/30 bg-white"
          disabled={loading}
        />
        <button
          onClick={handleAsk}
          disabled={loading || !question.trim()}
          className="px-3 py-2 bg-[#4F46E5] text-white rounded-lg hover:bg-[#4338CA] disabled:opacity-40 transition-colors"
        >
          <Send size={14} />
        </button>
      </div>
    </div>
  )
}
