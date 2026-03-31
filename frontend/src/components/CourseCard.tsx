import { Link } from 'react-router-dom'
import { BookOpen, Clock } from 'lucide-react'

interface Props {
  code: string
  title: string
  credits?: number | null
  terms?: string[]
  description?: string
}

export default function CourseCard({ code, title, credits, terms, description }: Props) {
  return (
    <Link
      to={`/course/${encodeURIComponent(code)}`}
      className="block rounded-lg p-4 transition-colors no-underline"
      style={{ background: 'var(--bg-elevated)', border: '1px solid var(--border)' }}
    >
      <div className="flex items-start justify-between gap-2 mb-1">
        <div>
          <span className="text-xs font-mono font-semibold" style={{ color: 'var(--accent)' }}>{code}</span>
          <h3 className="text-sm font-medium mt-0.5" style={{ color: 'var(--text-primary)' }}>{title}</h3>
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          {credits != null && (
            <span className="flex items-center gap-1 text-xs" style={{ color: 'var(--text-muted)' }}>
              <BookOpen size={12} />
              {credits} cr
            </span>
          )}
        </div>
      </div>
      {description && (
        <p className="text-xs mt-1 line-clamp-2" style={{ color: 'var(--text-muted)' }}>
          {description}
        </p>
      )}
      {terms && terms.length > 0 && (
        <div className="flex gap-1 mt-2">
          {terms.map((t) => (
            <span key={t} className="flex items-center gap-1 text-xs px-2 py-0.5 rounded-full" style={{ background: 'var(--bg-surface)', color: 'var(--text-muted)' }}>
              <Clock size={10} />
              {t}
            </span>
          ))}
        </div>
      )}
    </Link>
  )
}
