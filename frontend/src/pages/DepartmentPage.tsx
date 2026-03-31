import { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { ArrowLeft, Play, Loader2 } from 'lucide-react'
import { fetchDepartmentCourses, triggerPipeline, pipelineStreamUrl } from '../api/client'
import CourseCard from '../components/CourseCard'

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
  const [courses, setCourses] = useState<CourseItem[]>([])
  const [loading, setLoading] = useState(true)
  const [scraping, setScraping] = useState(false)

  useEffect(() => {
    if (!code) return
    fetchDepartmentCourses(code)
      .then(setCourses)
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [code])

  async function scrapeDept() {
    if (scraping || !code) return
    setScraping(true)
    try {
      const { run_id } = await triggerPipeline({ dept_filter: [code] })
      const es = new EventSource(pipelineStreamUrl(run_id))
      es.onmessage = (ev) => {
        try {
          const data = JSON.parse(ev.data)
          if (data.type === 'pipeline_done') {
            setScraping(false)
            es.close()
            // Refresh course list after scrape completes
            fetchDepartmentCourses(code).then(setCourses).catch(() => {})
          }
        } catch { /* ignore */ }
      }
      es.onerror = () => {
        setScraping(false)
        es.close()
      }
    } catch {
      setScraping(false)
    }
  }

  return (
    <div className="h-full overflow-y-auto p-6">
      <div className="max-w-3xl mx-auto">
        <Link to="/" className="flex items-center gap-1 text-xs mb-4 no-underline" style={{ color: 'var(--text-muted)' }}>
          <ArrowLeft size={14} />
          Back
        </Link>

        <div className="flex items-center justify-between mb-1">
          <h1 className="text-xl font-bold" style={{ color: 'var(--text-primary)' }}>{code}</h1>
          <button
            onClick={scrapeDept}
            disabled={scraping}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs cursor-pointer"
            style={{
              background: scraping ? 'var(--bg-elevated)' : 'var(--accent)',
              color: scraping ? 'var(--text-muted)' : '#fff',
              border: 'none',
              opacity: scraping ? 0.7 : 1,
            }}
          >
            {scraping ? (
              <Loader2 size={12} className="animate-spin" />
            ) : (
              <Play size={12} />
            )}
            {scraping ? 'Scraping...' : `Scrape ${code}`}
          </button>
        </div>
        <p className="text-sm mb-6" style={{ color: 'var(--text-muted)' }}>{courses.length} courses</p>

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
