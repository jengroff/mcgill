import { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { ChevronRight, ArrowLeft, BookOpen } from 'lucide-react'
import { fetchDepartments, fetchFaculty } from '../api/client'
import { useAppStore } from '../store/appStore'

interface DeptItem {
  code: string
  name: string
  faculty_slug: string
  course_count: number
}

export default function FacultyPage() {
  const { slug } = useParams<{ slug: string }>()
  const addToast = useAppStore((s) => s.addToast)
  const [faculty, setFaculty] = useState<{ name: string; slug: string } | null>(null)
  const [departments, setDepartments] = useState<DeptItem[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!slug) return
    setLoading(true)
    Promise.all([fetchFaculty(slug), fetchDepartments(slug)])
      .then(([fac, deps]) => {
        setFaculty(fac)
        setDepartments(deps)
      })
      .catch(() => addToast('Failed to load faculty details', 'error', { label: 'Retry', fn: () => window.location.reload() }))
      .finally(() => setLoading(false))
  }, [slug])

  return (
    <div className="h-full overflow-y-auto p-6">
      <div className="max-w-3xl mx-auto">
        <Link to="/" className="flex items-center gap-1 text-xs mb-4 no-underline" style={{ color: 'var(--text-muted)' }}>
          <ArrowLeft size={14} />
          All Faculties
        </Link>

        {loading ? (
          <div className="text-center py-8" style={{ color: 'var(--text-muted)' }}>Loading...</div>
        ) : (
          <>
            <h1 className="text-xl font-bold mb-1" style={{ color: 'var(--text-primary)' }}>{faculty?.name}</h1>
            <p className="text-sm mb-6" style={{ color: 'var(--text-muted)' }}>{departments.length} departments</p>

            <div className="space-y-2">
              {departments.map((d) => (
                <div
                  key={d.code}
                  className="flex items-center justify-between rounded-lg p-4"
                  style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)' }}
                >
                  <Link
                    to={`/dept/${d.code}`}
                    className="flex items-center gap-3 flex-1 min-w-0 no-underline"
                  >
                    <span className="text-sm font-mono font-semibold" style={{ color: 'var(--accent)' }}>{d.code}</span>
                    <span className="text-sm truncate" style={{ color: 'var(--text-primary)' }}>{d.name}</span>
                  </Link>
                  <div className="flex items-center gap-3 ml-3 shrink-0">
                    <span className="flex items-center gap-1 text-xs" style={{ color: 'var(--text-muted)' }}>
                      <BookOpen size={12} />
                      {d.course_count}
                    </span>
                    <Link to={`/dept/${d.code}`} className="no-underline">
                      <ChevronRight size={16} style={{ color: 'var(--text-muted)' }} />
                    </Link>
                  </div>
                </div>
              ))}
            </div>
          </>
        )}
      </div>
    </div>
  )
}
