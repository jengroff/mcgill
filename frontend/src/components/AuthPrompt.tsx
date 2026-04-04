import { useState } from 'react'
import { GraduationCap, MessageCircle, BookOpen, Search } from 'lucide-react'
import { login, register } from '../api/client'
import { useAppStore } from '../store/appStore'

const EXAMPLE_PROMPTS = [
  { icon: <Search size={14} />, text: 'What are the prerequisites for COMP 251?' },
  { icon: <BookOpen size={14} />, text: 'Show me all 3-credit MATH courses offered in Winter' },
  { icon: <MessageCircle size={14} />, text: 'Plan a 4-semester curriculum for computer science' },
]

export default function AuthPrompt() {
  const { loginUser } = useAppStore()
  const [mode, setMode] = useState<'login' | 'signup'>('signup')
  const [name, setName] = useState('')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const res = mode === 'signup'
        ? await register(name, email, password)
        : await login(email, password)
      loginUser(res.token, res.user)
    } catch (err: any) {
      setError(err.message || 'Something went wrong')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="h-full flex items-center justify-center p-6">
      <div className="w-full max-w-md">
        {/* Branding */}
        <div className="text-center mb-8">
          <div className="w-14 h-14 rounded-2xl flex items-center justify-center text-xl font-bold mx-auto mb-4" style={{ background: 'var(--accent)', color: '#fff' }}>
            <GraduationCap size={28} />
          </div>
          <h1 className="text-2xl font-bold mb-1" style={{ color: 'var(--text-primary)' }}>McGill Explorer</h1>
          <p className="text-sm" style={{ color: 'var(--text-muted)' }}>
            Search courses, explore prerequisites, and plan your curriculum
          </p>
        </div>

        {/* Auth form */}
        <form
          onSubmit={handleSubmit}
          className="rounded-xl p-6 mb-6"
          style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)' }}
        >
          <h2 className="text-sm font-semibold mb-4" style={{ color: 'var(--text-primary)' }}>
            {mode === 'signup' ? 'Create an account' : 'Welcome back'}
          </h2>

          <div className="space-y-3">
            {mode === 'signup' && (
              <input
                type="text"
                placeholder="Your name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                required
                className="w-full px-3 py-2 rounded-lg text-sm outline-none"
                style={{
                  background: 'var(--bg-primary)',
                  border: '1px solid var(--border)',
                  color: 'var(--text-primary)',
                }}
              />
            )}
            <input
              type="email"
              placeholder="Email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              required
              className="w-full px-3 py-2 rounded-lg text-sm outline-none"
              style={{
                background: 'var(--bg-primary)',
                border: '1px solid var(--border)',
                color: 'var(--text-primary)',
              }}
            />
            <input
              type="password"
              placeholder="Password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              minLength={8}
              className="w-full px-3 py-2 rounded-lg text-sm outline-none"
              style={{
                background: 'var(--bg-primary)',
                border: '1px solid var(--border)',
                color: 'var(--text-primary)',
              }}
            />
          </div>

          {error && (
            <p className="text-xs mt-2" style={{ color: '#ef4444' }}>{error}</p>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full mt-4 py-2 rounded-lg text-sm font-medium cursor-pointer"
            style={{
              background: 'var(--accent)',
              color: '#fff',
              border: 'none',
              opacity: loading ? 0.7 : 1,
            }}
          >
            {loading ? 'Please wait...' : mode === 'signup' ? 'Sign up' : 'Log in'}
          </button>

          <p className="text-xs text-center mt-3" style={{ color: 'var(--text-muted)' }}>
            {mode === 'signup' ? 'Already have an account?' : "Don't have an account?"}{' '}
            <button
              type="button"
              onClick={() => { setMode(mode === 'signup' ? 'login' : 'signup'); setError('') }}
              className="cursor-pointer"
              style={{ color: 'var(--accent)', background: 'none', border: 'none', textDecoration: 'underline', fontSize: '12px' }}
            >
              {mode === 'signup' ? 'Log in' : 'Sign up'}
            </button>
          </p>
        </form>

        {/* Example prompts */}
        <div>
          <p className="text-xs font-medium mb-3 text-center" style={{ color: 'var(--text-muted)' }}>
            Try asking things like
          </p>
          <div className="space-y-2">
            {EXAMPLE_PROMPTS.map((p, i) => (
              <div
                key={i}
                className="flex items-center gap-3 rounded-lg px-4 py-3 text-xs"
                style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)', color: 'var(--text-secondary)' }}
              >
                <span style={{ color: 'var(--accent)' }}>{p.icon}</span>
                {p.text}
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
