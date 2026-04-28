import { useState, useRef, useEffect } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { sendChat } from '../services/api'

interface Message {
  role: 'user' | 'assistant'
  content: string
}

interface Props {
  sessionId: string
}

function AssistantMessage({ content }: { content: string }) {
  return (
    <ReactMarkdown
      remarkPlugins={[remarkGfm]}
      components={{
        p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
        strong: ({ children }) => <strong className="font-semibold text-white">{children}</strong>,
        ul: ({ children }) => <ul className="list-disc list-inside space-y-1 my-2">{children}</ul>,
        ol: ({ children }) => <ol className="list-decimal list-inside space-y-1 my-2">{children}</ol>,
        li: ({ children }) => <li className="text-slate-300">{children}</li>,
        code: ({ children }) => (
          <code className="bg-slate-700 text-red-300 px-1 py-0.5 rounded text-xs font-mono">{children}</code>
        ),
        table: ({ children }) => (
          <div className="overflow-x-auto my-3">
            <table className="w-full text-xs border-collapse">{children}</table>
          </div>
        ),
        thead: ({ children }) => <thead className="bg-slate-700">{children}</thead>,
        tbody: ({ children }) => <tbody>{children}</tbody>,
        tr: ({ children }) => <tr className="border-b border-slate-700">{children}</tr>,
        th: ({ children }) => (
          <th className="text-left px-2 py-1.5 text-slate-200 font-semibold whitespace-nowrap">{children}</th>
        ),
        td: ({ children }) => <td className="px-2 py-1.5 text-slate-300">{children}</td>,
      }}
    >
      {content}
    </ReactMarkdown>
  )
}

export default function ChatBox({ sessionId }: Props) {
  const [messages, setMessages] = useState<Message[]>([
    { role: 'assistant', content: "Hi! I'm your FairLens audit assistant. Ask me anything about the chains found in your dataset, compliance implications, or what to fix first." }
  ])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const send = async () => {
    const msg = input.trim()
    if (!msg || loading) return
    setInput('')
    setMessages(prev => [...prev, { role: 'user', content: msg }])
    setLoading(true)
    try {
      const res = await sendChat(sessionId, msg)
      setMessages(prev => [...prev, { role: 'assistant', content: res.data.reply }])
    } catch {
      setMessages(prev => [...prev, { role: 'assistant', content: 'AI assistant is temporarily unavailable. Please try again.' }])
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex flex-col h-full">
      <div className="flex-1 overflow-y-auto space-y-3 pr-1">
        {messages.map((m, i) => (
          <div key={i} className={`text-sm leading-relaxed ${m.role === 'user' ? 'text-right' : ''}`}>
            <div className={`inline-block px-3 py-2 rounded-xl max-w-[90%] text-left
              ${m.role === 'user'
                ? 'bg-red-600/30 text-red-100'
                : 'bg-slate-800 text-slate-300'}`}>
              {m.role === 'assistant'
                ? <AssistantMessage content={m.content} />
                : m.content}
            </div>
          </div>
        ))}
        {loading && (
          <div className="text-sm text-slate-400">
            <span className="inline-block bg-slate-800 px-3 py-2 rounded-xl">
              <span className="flex items-center gap-2">
                <span className="w-3 h-3 border border-slate-500 border-t-transparent rounded-full animate-spin" />
                Thinking…
              </span>
            </span>
          </div>
        )}
        <div ref={bottomRef} />
      </div>

      <div className="mt-3 flex gap-2">
        <input
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && send()}
          placeholder="Ask about chains, compliance, fixes…"
          className="flex-1 bg-slate-800 border border-slate-600 rounded-lg px-3 py-2
            text-sm text-white placeholder-slate-500 focus:outline-none focus:border-slate-400"
        />
        <button
          onClick={send}
          disabled={!input.trim() || loading}
          className="px-4 py-2 bg-red-600 hover:bg-red-700 disabled:bg-slate-700
            disabled:text-slate-500 text-white rounded-lg text-sm font-semibold transition-colors"
        >
          Send
        </button>
      </div>
    </div>
  )
}
