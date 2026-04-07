import { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { ArrowLeft, BookOpen, Clock, AlertCircle, GitBranch } from 'lucide-react'
import { fetchCourse, fetchPrereqTree } from '../api/client'
import { useAppStore } from '../store/appStore'
import PrereqGraph from '../components/PrereqGraph'

interface CourseDetail {
  code: string
  title: string
  dept: string
  number: string
  credits: number | null
  faculty: string
  terms: string[]
  description: string
  prerequisites_raw: string
  restrictions_raw: string
  notes_raw: string
  url: string
  prerequisites: string[]
  corequisites: string[]
  restrictions: string[]
}

export default function CoursePage() {
  const { code } = useParams<{ code: string }>()
  const addToast = useAppStore((s) => s.addToast)
  const [course, setCourse] = useState<CourseDetail | null>(null)
  const [loading, setLoading] = useState(true)
  const [treeData, setTreeData] = useState<{ root: string; nodes: any[]; edges: any[] } | null>(null)

  useEffect(() => {
    if (!code) return
    setLoading(true)
    fetchCourse(code)
      .then(setCourse)
      .catch(() => addToast(`Failed to load course ${code}`, 'error', { label: 'Retry', fn: () => window.location.reload() }))
      .finally(() => setLoading(false))
    fetchPrereqTree(code).then(setTreeData).catch(() => {})
  }, [code])

  if (loading) {
    return <div className="h-full flex items-center justify-center" style={{ color: 'var(--text-muted)' }}>Loading...</div>
  }

  if (!course) {
    return <div className="h-full flex items-center justify-center" style={{ color: 'var(--text-muted)' }}>Course not found</div>
  }

  return (
    <div className="h-full overflow-y-auto p-6">
      <div className="max-w-3xl mx-auto">
        <Link to={`/dept/${course.dept}`} className="flex items-center gap-1 text-xs mb-4 no-underline" style={{ color: 'var(--text-muted)' }}>
          <ArrowLeft size={14} />
          {course.dept} courses
        </Link>

        <div className="rounded-lg p-6" style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)' }}>
          <div className="flex items-start justify-between mb-4">
            <div>
              <span className="text-sm font-mono font-bold" style={{ color: 'var(--accent)' }}>{course.code}</span>
              <h1 className="text-xl font-bold mt-1" style={{ color: 'var(--text-primary)' }}>{course.title}</h1>
              <p className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>{course.faculty}</p>
            </div>
            <div className="flex items-center gap-3 flex-shrink-0">
              {course.credits != null && (
                <span className="flex items-center gap-1 text-sm px-3 py-1 rounded-full" style={{ background: 'var(--bg-elevated)', color: 'var(--text-primary)' }}>
                  <BookOpen size={14} />
                  {course.credits} credits
                </span>
              )}
            </div>
          </div>

          {course.terms.length > 0 && (
            <div className="flex gap-2 mb-4">
              {course.terms.map((t) => (
                <span key={t} className="flex items-center gap-1 text-xs px-3 py-1 rounded-full" style={{ background: 'var(--bg-elevated)', color: 'var(--text-muted)' }}>
                  <Clock size={12} />
                  {t}
                </span>
              ))}
            </div>
          )}

          {course.description && (
            <div className="mb-4">
              <h2 className="text-xs font-medium uppercase tracking-wide mb-2" style={{ color: 'var(--text-muted)' }}>Description</h2>
              <p className="text-sm leading-relaxed" style={{ color: 'var(--text-primary)' }}>{course.description}</p>
            </div>
          )}

          {course.prerequisites_raw && (
            <div className="mb-4">
              <h2 className="text-xs font-medium uppercase tracking-wide mb-2" style={{ color: 'var(--text-muted)' }}>Prerequisites</h2>
              <p className="text-sm" style={{ color: 'var(--text-primary)' }}>{course.prerequisites_raw}</p>
              {course.prerequisites.length > 0 && (
                <div className="flex flex-wrap gap-2 mt-2">
                  {course.prerequisites.map((p) => (
                    <Link
                      key={p}
                      to={`/course/${encodeURIComponent(p)}`}
                      className="flex items-center gap-1 text-xs px-2 py-1 rounded no-underline"
                      style={{ background: 'var(--phase1)', color: '#fff', opacity: 0.9 }}
                    >
                      <GitBranch size={10} />
                      {p}
                    </Link>
                  ))}
                </div>
              )}
            </div>
          )}

          {course.restrictions_raw && (
            <div className="mb-4">
              <h2 className="text-xs font-medium uppercase tracking-wide mb-2" style={{ color: 'var(--text-muted)' }}>Restrictions</h2>
              <div className="flex items-start gap-2 text-sm" style={{ color: 'var(--text-primary)' }}>
                <AlertCircle size={14} className="flex-shrink-0 mt-0.5" style={{ color: 'var(--phase4)' }} />
                {course.restrictions_raw}
              </div>
            </div>
          )}

          {course.notes_raw && (
            <div className="mb-4">
              <h2 className="text-xs font-medium uppercase tracking-wide mb-2" style={{ color: 'var(--text-muted)' }}>Notes</h2>
              <p className="text-sm" style={{ color: 'var(--text-muted)' }}>{course.notes_raw}</p>
            </div>
          )}

          {course.url && (
            <a
              href={course.url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-xs underline"
              style={{ color: 'var(--accent)' }}
            >
              View on McGill Course Catalogue
            </a>
          )}
        </div>

        {treeData && treeData.nodes.length > 1 && (
          <div className="mt-4">
            <h2 className="text-xs font-medium uppercase tracking-wide mb-3"
                style={{ color: 'var(--text-muted)' }}>
              Prerequisite chain
            </h2>
            <div className="rounded-lg overflow-hidden relative"
                 style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)' }}>
              <PrereqGraph
                code={treeData.root}
                nodes={treeData.nodes}
                edges={treeData.edges}
              />
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
