import { BookOpen } from 'lucide-react'
import PhaseIndicator from './PhaseIndicator'
import { useAppStore } from '../store/appStore'
import { useEffect, useState } from 'react'
import { fetchHealth } from '../api/client'

export default function Sidebar() {
  const sources = useAppStore((s) => s.sources)
  const [health, setHealth] = useState({ postgres: 'unknown', neo4j: 'unknown' })

  useEffect(() => {
    fetchHealth().then(setHealth).catch(() => {})
    const iv = setInterval(() => {
      fetchHealth().then(setHealth).catch(() => {})
    }, 15000)
    return () => clearInterval(iv)
  }, [])

  return (
    <aside className="w-72 flex flex-col gap-4 p-4 border-r overflow-y-auto" style={{ borderColor: 'var(--border)', background: 'var(--bg-surface)' }}>
      <PhaseIndicator />

      {sources.length > 0 && (
        <div className="rounded-lg p-3" style={{ background: 'var(--bg-elevated)' }}>
          <p className="text-xs font-medium uppercase tracking-wide mb-2" style={{ color: 'var(--text-muted)' }}>Sources</p>
          <div className="space-y-1">
            {sources.map((s) => (
              <div key={s.code} className="flex items-center gap-2 text-xs">
                <BookOpen size={12} style={{ color: 'var(--accent)' }} />
                <span className="font-mono" style={{ color: 'var(--accent)' }}>{s.code}</span>
                <span style={{ color: 'var(--text-muted)' }}>{s.title}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="mt-auto rounded-lg p-3" style={{ background: 'var(--bg-elevated)' }}>
        <p className="text-xs font-medium uppercase tracking-wide mb-2" style={{ color: 'var(--text-muted)' }}>System</p>
        <div className="space-y-1 text-xs" style={{ color: 'var(--text-muted)' }}>
          <p>PostgreSQL: <span style={{ color: health.postgres === 'connected' ? '#10b981' : 'var(--text-muted)' }}>{health.postgres}</span></p>
          <p>Neo4j: <span style={{ color: health.neo4j === 'connected' ? '#10b981' : 'var(--text-muted)' }}>{health.neo4j}</span></p>
        </div>
      </div>
    </aside>
  )
}

export function Stat({ icon, label, value, color }: { icon: React.ReactNode; label: string; value: string; color: string }) {
  return (
    <div className="flex items-center gap-1.5">
      <span style={{ color }}>{icon}</span>
      <span style={{ color: 'var(--text-muted)' }}>{label}:</span>
      <span className="font-medium" style={{ color: 'var(--text-primary)' }}>{value}</span>
    </div>
  )
}
