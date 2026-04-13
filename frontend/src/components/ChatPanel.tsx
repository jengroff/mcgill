import { useState, useRef, useEffect } from 'react'
import { Send } from 'lucide-react'
import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { useAppStore } from '../store/appStore'
import { sendMessage, createSession, sseUrl } from '../api/client'

export default function ChatPanel() {
  const { sessionId, setSessionId, messages, addMessage, sending, setSending, streamToken, finalizeStream } = useAppStore()
  const [input, setInput] = useState('')
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  async function handleSend() {
    const text = input.trim()
    if (!text || sending) return
    setInput('')
    setSending(true)
    addMessage('user', text)
    try {
      // Create session lazily if SSE connection hasn't established yet
      let sid = sessionId
      if (!sid) {
        sid = await createSession()
        setSessionId(sid)
        const es = new EventSource(sseUrl(sid))
        es.onmessage = (ev) => {
          try {
            const data = JSON.parse(ev.data)
            if (data.type === 'token') streamToken(data.content)
            else if (data.type === 'assistant_done') finalizeStream()
            else if (data.type === 'assistant') addMessage('assistant', data.content)
            else if (data.type === 'error') addMessage('system', data.content)
          } catch { /* ignore */ }
        }
      }
      await sendMessage(sid, text)
    } catch {
      addMessage('system', 'Failed to send message')
      setSending(false)
    }
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  return (
    <div className="flex flex-col h-full">
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {messages.length === 0 && (
          <div className="text-center py-12">
            <p className="text-lg font-medium mb-1" style={{ color: 'var(--text-primary)' }}>Ask about McGill courses</p>
            <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
              Find courses, check prerequisites, or explore programs
            </p>
          </div>
        )}

        {messages.map((msg) => (
          <div key={msg.id} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            <div
              className="max-w-[80%] rounded-lg px-3 py-2 text-sm leading-relaxed"
              style={{
                background: msg.role === 'user'
                  ? 'var(--accent)'
                  : msg.role === 'system'
                    ? 'rgba(245,158,11,0.1)'
                    : 'var(--bg-elevated)',
                color: msg.role === 'user' ? '#fff' : 'var(--text-primary)',
                border: msg.role === 'assistant' ? '1px solid var(--border)' : 'none',
              }}
            >
              <Markdown
                remarkPlugins={[remarkGfm]}
                components={{
                  p: ({ children }) => <p className="mb-1 last:mb-0">{children}</p>,
                  strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
                  code: ({ children }) => (
                    <code className="px-1 py-0.5 rounded text-xs" style={{ background: 'rgba(255,255,255,0.08)' }}>
                      {children}
                    </code>
                  ),
                  ul: ({ children }) => <ul className="list-disc pl-4 mb-1">{children}</ul>,
                  ol: ({ children }) => <ol className="list-decimal pl-4 mb-1">{children}</ol>,
                  li: ({ children }) => <li className="mb-0.5">{children}</li>,
                  table: ({ children }) => (
                    <div className="overflow-x-auto my-2">
                      <table className="w-full text-xs border-collapse" style={{ border: '1px solid var(--border)' }}>
                        {children}
                      </table>
                    </div>
                  ),
                  thead: ({ children }) => (
                    <thead style={{ background: 'rgba(255,255,255,0.05)' }}>{children}</thead>
                  ),
                  th: ({ children }) => (
                    <th className="px-2 py-1 text-left font-semibold" style={{ borderBottom: '1px solid var(--border)' }}>
                      {children}
                    </th>
                  ),
                  td: ({ children }) => (
                    <td className="px-2 py-1" style={{ borderBottom: '1px solid var(--border)' }}>
                      {children}
                    </td>
                  ),
                }}
              >
                {msg.content}
              </Markdown>
            </div>
          </div>
        ))}

        {sending && (
          <div className="flex justify-start">
            <div className="rounded-lg px-3 py-2 text-sm" style={{ background: 'var(--bg-elevated)', border: '1px solid var(--border)' }}>
              <span className="inline-flex gap-1">
                <span className="w-1.5 h-1.5 rounded-full animate-bounce" style={{ background: 'var(--text-muted)', animationDelay: '0ms' }} />
                <span className="w-1.5 h-1.5 rounded-full animate-bounce" style={{ background: 'var(--text-muted)', animationDelay: '150ms' }} />
                <span className="w-1.5 h-1.5 rounded-full animate-bounce" style={{ background: 'var(--text-muted)', animationDelay: '300ms' }} />
              </span>
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      <div className="p-3 border-t" style={{ borderColor: 'var(--border)' }}>
        <div className="flex gap-2 items-end">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder=""
            rows={1}
            className="flex-1 resize-none rounded-lg px-3 py-2 text-sm outline-none"
            style={{
              background: 'var(--bg-elevated)',
              color: 'var(--text-primary)',
              border: '1px solid var(--border)',
            }}
          />
          <button
            onClick={handleSend}
            disabled={!input.trim() || sending}
            className="rounded-lg p-2 transition-opacity cursor-pointer"
            style={{
              background: 'var(--accent)',
              color: '#fff',
              opacity: !input.trim() || sending ? 0.4 : 1,
              border: 'none',
            }}
          >
            <Send size={16} />
          </button>
        </div>
      </div>
    </div>
  )
}
