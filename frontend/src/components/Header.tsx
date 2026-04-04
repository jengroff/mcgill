import { Activity, GraduationCap, MessageCircle, LogOut } from 'lucide-react'
import { Link, useLocation } from 'react-router-dom'
import { useAppStore } from '../store/appStore'

export default function Header() {
  const connected = useAppStore((s) => s.connected)
  const user = useAppStore((s) => s.user)
  const logout = useAppStore((s) => s.logout)
  const location = useLocation()

  return (
    <header className="flex items-center justify-between px-6 py-3 border-b" style={{ borderColor: 'var(--border)', background: 'var(--bg-surface)' }}>
      <div className="flex items-center gap-3">
        <Link to="/" className="flex items-center gap-3 no-underline">
          <div className="w-8 h-8 rounded-lg flex items-center justify-center text-sm font-bold" style={{ background: 'var(--accent)', color: '#fff' }}>
            <GraduationCap size={18} />
          </div>
          <div>
            <h1 className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>McGill Explorer</h1>
            <p className="text-xs" style={{ color: 'var(--text-muted)' }}>Course Intelligence</p>
          </div>
        </Link>
      </div>

      <nav className="flex items-center gap-4 text-xs">
        <Link
          to="/"
          className="px-3 py-1.5 rounded-md no-underline transition-colors"
          style={{
            color: location.pathname === '/' ? 'var(--text-primary)' : 'var(--text-muted)',
            background: location.pathname === '/' ? 'var(--bg-elevated)' : 'transparent',
          }}
        >
          Browse
        </Link>
        <Link
          to="/chat"
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-md no-underline transition-colors"
          style={{
            color: location.pathname === '/chat' ? 'var(--text-primary)' : 'var(--text-muted)',
            background: location.pathname === '/chat' ? 'var(--bg-elevated)' : 'transparent',
          }}
        >
          <MessageCircle size={12} />
          Chat
        </Link>

        <div className="flex items-center gap-1.5 ml-2" style={{ color: connected ? '#10b981' : 'var(--text-muted)' }}>
          <Activity size={12} />
          {connected ? 'Live' : 'Offline'}
        </div>

        {user && (
          <div className="flex items-center gap-2 ml-2 pl-3" style={{ borderLeft: '1px solid var(--border)' }}>
            <span className="text-xs" style={{ color: 'var(--text-primary)' }}>{user.name.split(' ')[0]}</span>
            <button
              onClick={logout}
              className="flex items-center gap-1 px-2 py-1 rounded cursor-pointer"
              style={{ background: 'none', border: 'none', color: 'var(--text-muted)' }}
              title="Log out"
            >
              <LogOut size={12} />
            </button>
          </div>
        )}
      </nav>
    </header>
  )
}
