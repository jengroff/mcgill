import { Activity, GraduationCap, MessageCircle, Play, ChevronDown, X } from 'lucide-react'
import { Link, useLocation } from 'react-router-dom'
import { useAppStore } from '../store/appStore'
import { useState, useEffect, useRef } from 'react'
import { triggerPipeline, pipelineStreamUrl, fetchFaculties } from '../api/client'

interface FacultyOption {
  name: string
  slug: string
  department_codes: string[]
  course_count: number
}

export default function Header() {
  const connected = useAppStore((s) => s.connected)
  const { setPipelineRunId, setPipelineStatus, updateStep } = useAppStore()
  const location = useLocation()
  const [scraping, setScraping] = useState(false)
  const [showMenu, setShowMenu] = useState(false)
  const [faculties, setFaculties] = useState<FacultyOption[]>([])
  const [selectedFaculty, setSelectedFaculty] = useState<FacultyOption | null>(null)
  const menuRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    fetchFaculties().then(setFaculties).catch(() => {})
  }, [])

  // Close menu on outside click
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setShowMenu(false)
      }
    }
    if (showMenu) document.addEventListener('mousedown', handleClick)
    return () => document.removeEventListener('mousedown', handleClick)
  }, [showMenu])

  async function runScraper(facultyFilter?: string[]) {
    if (scraping) return
    setShowMenu(false)
    setScraping(true)
    try {
      const { run_id } = await triggerPipeline({
        faculty_filter: facultyFilter,
      })
      setPipelineRunId(run_id)
      setPipelineStatus('running')

      const es = new EventSource(pipelineStreamUrl(run_id))
      es.onmessage = (ev) => {
        try {
          const data = JSON.parse(ev.data)
          if (data.type === 'step_update') {
            const phaseNum = data.phase === 'scrape' ? 1 : data.phase === 'resolve' ? 2 : 3
            updateStep(phaseNum, data.message, 'running')
          } else if (data.type === 'pipeline_done') {
            setPipelineStatus(data.status)
            setScraping(false)
            es.close()
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

        {/* Scraper button + dropdown */}
        <div className="relative" ref={menuRef}>
          <div className="flex items-center">
            <button
              onClick={() => {
                if (scraping) return
                if (selectedFaculty) {
                  runScraper([selectedFaculty.name])
                } else {
                  setShowMenu(!showMenu)
                }
              }}
              disabled={scraping}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-l-md cursor-pointer"
              style={{
                background: 'var(--accent)',
                color: '#fff',
                opacity: scraping ? 0.5 : 1,
                border: 'none',
                fontSize: '12px',
              }}
            >
              <Play size={12} />
              {scraping
                ? 'Scraping...'
                : selectedFaculty
                  ? `Scrape ${selectedFaculty.slug}`
                  : 'Scrape'}
            </button>
            <button
              onClick={() => !scraping && setShowMenu(!showMenu)}
              disabled={scraping}
              className="flex items-center px-1.5 py-1.5 rounded-r-md cursor-pointer"
              style={{
                background: 'var(--accent)',
                color: '#fff',
                opacity: scraping ? 0.5 : 1,
                border: 'none',
                borderLeft: '1px solid rgba(255,255,255,0.2)',
                fontSize: '12px',
              }}
            >
              <ChevronDown size={12} />
            </button>
          </div>

          {showMenu && (
            <div
              className="absolute right-0 top-full mt-1 w-72 rounded-lg shadow-lg overflow-hidden z-50"
              style={{ background: 'var(--bg-elevated)', border: '1px solid var(--border)' }}
            >
              {/* All faculties option */}
              <button
                onClick={() => {
                  setSelectedFaculty(null)
                  runScraper(undefined)
                }}
                className="w-full flex items-center justify-between px-3 py-2 text-left text-xs cursor-pointer"
                style={{
                  background: 'transparent',
                  color: 'var(--text-primary)',
                  border: 'none',
                  borderBottom: '1px solid var(--border)',
                }}
              >
                <span className="font-semibold">All 12 Faculties</span>
                <span style={{ color: 'var(--text-muted)' }}>~4900 courses</span>
              </button>

              {/* Clear selection if one is set */}
              {selectedFaculty && (
                <button
                  onClick={() => {
                    setSelectedFaculty(null)
                    setShowMenu(false)
                  }}
                  className="w-full flex items-center gap-2 px-3 py-1.5 text-left text-xs cursor-pointer"
                  style={{
                    background: 'rgba(237,27,47,0.1)',
                    color: 'var(--accent)',
                    border: 'none',
                    borderBottom: '1px solid var(--border)',
                  }}
                >
                  <X size={10} />
                  Clear selection
                </button>
              )}

              {/* Faculty list */}
              <div className="max-h-64 overflow-y-auto">
                {faculties.map((f) => (
                  <button
                    key={f.slug}
                    onClick={() => {
                      setSelectedFaculty(f)
                      runScraper([f.name])
                    }}
                    className="w-full flex items-center justify-between px-3 py-2 text-left text-xs cursor-pointer"
                    style={{
                      background: selectedFaculty?.slug === f.slug ? 'rgba(237,27,47,0.1)' : 'transparent',
                      color: 'var(--text-primary)',
                      border: 'none',
                      borderBottom: '1px solid var(--border)',
                    }}
                    onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--bg-surface)')}
                    onMouseLeave={(e) => (e.currentTarget.style.background = selectedFaculty?.slug === f.slug ? 'rgba(237,27,47,0.1)' : 'transparent')}
                  >
                    <div>
                      <span>{f.name}</span>
                      <span className="ml-1.5 font-mono" style={{ color: 'var(--text-muted)' }}>
                        ({f.department_codes.length} depts)
                      </span>
                    </div>
                    <span style={{ color: 'var(--text-muted)' }}>{f.course_count}</span>
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>

        <div className="flex items-center gap-1.5 ml-2" style={{ color: connected ? '#10b981' : 'var(--text-muted)' }}>
          <Activity size={12} />
          {connected ? 'Live' : 'Offline'}
        </div>
      </nav>
    </header>
  )
}
