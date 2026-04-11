import { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { ArrowLeft } from 'lucide-react'
import { fetchDepartmentCourses } from '../api/client'
import { useAppStore } from '../store/appStore'
import CourseCard from '../components/CourseCard'
import PipelineRunner from '../components/PipelineRunner'

interface CourseItem {
  code: string
  slug: string
  title: string
  credits: number | null
  terms: string[]
  description: string
}

export default function DepartmentPage() {
  const { code } = useParams<{ code: string }>()
  const addToast = useAppStore((s) => s.addToast)
  const [courses, setCourses] = useState<CourseItem[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!code) return
    setLoading(true)
    fetchDepartmentCourses(code)
      .then(setCourses)
      .catch(() => addToast('Failed to load courses', 'error', { label: 'Retry', fn: () => window.location.reload() }))
      .finally(() => setLoading(false))
  }, [code])

  return (
    <div className="h-full overflow-y-auto p-6">
      <div className="max-w-3xl mx-auto">
        <Link to="/" className="flex items-center gap-1 text-xs mb-4 no-underline" style={{ color: 'var(--text-muted)' }}>
          <ArrowLeft size={14} />
          Back
        </Link>

        <div className="flex items-center justify-between mb-1">
          <h1 className="text-xl font-bold" style={{ color: 'var(--text-primary)' }}>{code}</h1>
        </div>
        <p className="text-sm mb-4" style={{ color: 'var(--text-muted)' }}>{courses.length} courses</p>

        <div className="mb-6">
          <PipelineRunner deptFilter={code ? [code] : undefined} />
        </div>

        {loading ? (
          <div className="text-center py-8" style={{ color: 'var(--text-muted)' }}>Loading courses...</div>
        ) : (
          <div className="space-y-3">
            {courses.map((c) => (
              <CourseCard
                key={c.code}
                code={c.code}
                title={c.title}
                credits={c.credits}
                terms={c.terms}
                description={c.description}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
