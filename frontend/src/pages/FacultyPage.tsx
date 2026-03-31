import { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { ChevronRight, ArrowLeft, BookOpen, Play, Loader2 } from 'lucide-react'
import { fetchDepartments, fetchFaculty, triggerPipeline, pipelineStreamUrl } from '../api/client'

interface DeptItem {
  code: string
  name: string
  faculty_slug: string
  course_count: number
}

export default function FacultyPage() {
  const { slug } = useParams<{ slug: string }>()
  const [faculty, setFaculty] = useState<{ name: string; slug: string } | null>(null)
  const [departments, setDepartments] = useState<DeptItem[]>([])
  const [loading, setLoading] = useState(true)
  const [scrapingDept, setScrapingDept] = useState<string | null>(null)

  useEffect(() => {
    if (!slug) return
    Promise.all([fetchFaculty(slug), fetchDepartments(slug)])
      .then(([fac, deps]) => {
        setFaculty(fac)
        setDepartments(deps)
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [slug])

  async function scrapeDept(code: string) {
    if (scrapingDept) return
    setScrapingDept(code)
    try {
      const { run_id } = await triggerPipeline({ dept_filter: [code] })
      const es = new EventSource(pipelineStreamUrl(run_id))
      es.onmessage = (ev) => {
        try {
          const data = JSON.parse(ev.data)
          if (data.type === 'pipeline_done') {
            setScrapingDept(null)
            es.close()
          }
        } catch { /* ignore */ }
      }
      es.onerror = () => {
        setScrapingDept(null)
        es.close()
      }
    } catch {
      setScrapingDept(null)
    }
  }

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
                    <button
                      onClick={() => scrapeDept(d.code)}
                      disabled={scrapingDept !== null}
                      className="flex items-center gap-1 px-2.5 py-1 rounded-md text-xs cursor-pointer"
                      title={`Scrape ${d.code} courses`}
                      style={{
                        background: scrapingDept === d.code ? 'var(--bg-elevated)' : 'var(--accent)',
                        color: scrapingDept === d.code ? 'var(--text-muted)' : '#fff',
                        border: 'none',
                        opacity: scrapingDept !== null && scrapingDept !== d.code ? 0.4 : 1,
                      }}
                    >
                      {scrapingDept === d.code ? (
                        <Loader2 size={12} className="animate-spin" />
                      ) : (
                        <Play size={12} />
                      )}
                      {scrapingDept === d.code ? 'Scraping...' : 'Scrape'}
                    </button>
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
