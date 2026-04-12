import { useState } from 'react'
import { Activity, GraduationCap, MessageCircle, CalendarDays, BookOpen, LogOut, Menu, X } from 'lucide-react'
import { Link, useLocation } from 'react-router-dom'
import { useAppStore } from '../store/appStore'

export default function Header() {
  const connected = useAppStore((s) => s.connected)
  const user = useAppStore((s) => s.user)
  const logout = useAppStore((s) => s.logout)
  const location = useLocation()
  const [menuOpen, setMenuOpen] = useState(false)

  const navLinks = [
    { to: '/', label: 'Browse', icon: null, match: (p: string) => p === '/' },
    { to: '/chat', label: 'Chat', icon: <MessageCircle size={12} />, match: (p: string) => p === '/chat' },
    { to: '/planner', label: 'Planner', icon: <CalendarDays size={12} />, match: (p: string) => p.startsWith('/planner') },
    { to: '/guide', label: 'Guide', icon: <BookOpen size={12} />, match: (p: string) => p === '/guide' },
  ]

  return (
    <header className="border-b" style={{ borderColor: 'var(--border)', background: 'var(--bg-surface)' }}>
      <div className="flex items-center justify-between px-4 py-3 md:px-6">
        <Link to="/" className="flex items-center gap-3 no-underline">
          <div className="w-8 h-8 rounded-lg flex items-center justify-center text-sm font-bold" style={{ background: 'var(--accent)', color: '#fff' }}>
            <GraduationCap size={18} />
          </div>
          <div>
            <h1 className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>McGill Explorer</h1>
            <p className="text-xs hidden sm:block" style={{ color: 'var(--text-muted)' }}>Course Intelligence</p>
          </div>
        </Link>

        {/* Desktop nav */}
        <nav className="hidden md:flex items-center gap-4 text-xs">
          {navLinks.map((link) => (
            <Link
              key={link.to}
              to={link.to}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-md no-underline transition-colors"
              style={{
                color: link.match(location.pathname) ? 'var(--text-primary)' : 'var(--text-muted)',
                background: link.match(location.pathname) ? 'var(--bg-elevated)' : 'transparent',
              }}
            >
              {link.icon}
              {link.label}
            </Link>
          ))}

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

        {/* Mobile hamburger */}
        <button
          onClick={() => setMenuOpen(!menuOpen)}
          className="md:hidden flex items-center justify-center w-8 h-8 rounded cursor-pointer"
          style={{ background: 'none', border: 'none', color: 'var(--text-muted)' }}
        >
          {menuOpen ? <X size={20} /> : <Menu size={20} />}
        </button>
      </div>

      {/* Mobile menu dropdown */}
      {menuOpen && (
        <nav className="md:hidden flex flex-col gap-1 px-4 pb-3 text-xs">
          {navLinks.map((link) => (
            <Link
              key={link.to}
              to={link.to}
              onClick={() => setMenuOpen(false)}
              className="flex items-center gap-2 px-3 py-2.5 rounded-md no-underline transition-colors"
              style={{
                color: link.match(location.pathname) ? 'var(--text-primary)' : 'var(--text-muted)',
                background: link.match(location.pathname) ? 'var(--bg-elevated)' : 'transparent',
              }}
            >
              {link.icon}
              {link.label}
            </Link>
          ))}

          <div className="flex items-center justify-between px-3 py-2 mt-1" style={{ borderTop: '1px solid var(--border)' }}>
            <div className="flex items-center gap-1.5" style={{ color: connected ? '#10b981' : 'var(--text-muted)' }}>
              <Activity size={12} />
              {connected ? 'Live' : 'Offline'}
            </div>
            {user && (
              <button
                onClick={() => { logout(); setMenuOpen(false) }}
                className="flex items-center gap-1.5 px-2 py-1 rounded cursor-pointer text-xs"
                style={{ background: 'none', border: 'none', color: 'var(--text-muted)' }}
              >
                <LogOut size={12} />
                Log out
              </button>
            )}
          </div>
        </nav>
      )}
    </header>
  )
}
