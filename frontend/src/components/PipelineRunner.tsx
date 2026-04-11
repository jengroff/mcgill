import { useState, useRef, useCallback } from 'react'
import { Play, CheckCircle, Circle, Loader, XCircle } from 'lucide-react'
import { triggerPipeline, pipelineStreamUrl } from '../api/client'

type PhaseStatus = 'idle' | 'running' | 'done' | 'error'

interface Phase {
  name: string
  label: string
  status: PhaseStatus
}

const INITIAL_PHASES: Phase[] = [
  { name: 'precheck', label: 'Pre-check', status: 'idle' },
  { name: 'scrape', label: 'Scrape', status: 'idle' },
  { name: 'resolve', label: 'Resolve', status: 'idle' },
  { name: 'embed', label: 'Embed', status: 'idle' },
]

const PHASE_ORDER = ['precheck', 'scrape', 'resolve', 'embed']

function PhaseIcon({ status }: { status: PhaseStatus }) {
  if (status === 'done') return <CheckCircle size={14} style={{ color: 'var(--phase1)' }} />
  if (status === 'running') return <Loader size={14} className="animate-spin" style={{ color: 'var(--phase2)' }} />
  if (status === 'error') return <XCircle size={14} style={{ color: 'var(--accent)' }} />
  return <Circle size={14} style={{ color: 'var(--border)' }} />
}

interface PipelineRunnerProps {
  facultyFilter?: string[]
  deptFilter?: string[]
}

export default function PipelineRunner({ facultyFilter, deptFilter }: PipelineRunnerProps) {
  const [force, setForce] = useState(false)
  const [running, setRunning] = useState(false)
  const [phases, setPhases] = useState<Phase[]>(INITIAL_PHASES)
  const [result, setResult] = useState<Record<string, unknown> | null>(null)
  const [error, setError] = useState<string | null>(null)
  const evtSourceRef = useRef<EventSource | null>(null)

  const run = useCallback(async () => {
    setRunning(true)
    setError(null)
    setResult(null)
    setPhases(INITIAL_PHASES.map((p) => ({ ...p, status: 'idle' })))

    try {
      const { run_id } = await triggerPipeline({ faculty_filter: facultyFilter, dept_filter: deptFilter, force })

      // Mark first phase as running
      setPhases((prev) => prev.map((p, i) => (i === 0 ? { ...p, status: 'running' } : p)))

      const es = new EventSource(pipelineStreamUrl(run_id))
      evtSourceRef.current = es

      es.onmessage = (evt) => {
        const data = JSON.parse(evt.data)

        if (data.type === 'step_update' && data.status === 'done') {
          const doneIdx = PHASE_ORDER.indexOf(data.node)
          setPhases((prev) =>
            prev.map((p, i) => {
              if (i === doneIdx) return { ...p, status: 'done' }
              if (i === doneIdx + 1) return { ...p, status: 'running' }
              return p
            }),
          )
        }

        if (data.type === 'pipeline_done') {
          es.close()
          evtSourceRef.current = null
          setRunning(false)
          if (data.status === 'error') {
            setError(data.result?.error ?? 'Pipeline failed')
            setPhases((prev) => prev.map((p) => (p.status === 'running' ? { ...p, status: 'error' } : p)))
          } else {
            setResult(data.result)
            setPhases((prev) => prev.map((p) => (p.status !== 'done' ? { ...p, status: 'done' } : p)))
          }
        }
      }

      es.onerror = () => {
        es.close()
        evtSourceRef.current = null
        setRunning(false)
        setError('Lost connection to pipeline stream')
        setPhases((prev) => prev.map((p) => (p.status === 'running' ? { ...p, status: 'error' } : p)))
      }
    } catch {
      setRunning(false)
      setError('Failed to start pipeline')
    }
  }, [facultyFilter, deptFilter, force])

  const hasActivity = running || result || error

  return (
    <div className="rounded-lg p-4" style={{ background: 'var(--bg-elevated)', border: '1px solid var(--border)' }}>
      <div className="flex items-center gap-3 flex-wrap">
        <button
          onClick={run}
          disabled={running}
          className="flex items-center gap-2 px-3 py-1.5 rounded text-xs font-medium transition-colors cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
          style={{ background: 'var(--accent)', color: '#fff' }}
        >
          <Play size={12} />
          {running ? 'Running...' : 'Run Pipeline'}
        </button>
        <label className="flex items-center gap-1.5 text-xs cursor-pointer" style={{ color: 'var(--text-muted)' }}>
          <input
            type="checkbox"
            checked={force}
            onChange={(e) => setForce(e.target.checked)}
            disabled={running}
            className="accent-[var(--accent)]"
          />
          Force re-process
        </label>
      </div>

      {hasActivity && (
        <div className="mt-3 flex flex-col gap-1.5">
          {phases.map((p) => (
            <div key={p.name} className="flex items-center gap-2 text-xs">
              <PhaseIcon status={p.status} />
              <span style={{ color: p.status === 'idle' ? 'var(--text-muted)' : 'var(--text-primary)' }}>
                {p.label}
              </span>
            </div>
          ))}

          {result && (
            <div className="mt-2 text-xs space-y-0.5" style={{ color: 'var(--text-muted)' }}>
              <p>Scraped {(result.courses_scraped as number) ?? 0} courses</p>
              <p>Created {(result.entities_created as number) ?? 0} entities, {(result.relationships_created as number) ?? 0} relationships</p>
              <p>Embedded {(result.chunks_created as number) ?? 0} chunks</p>
            </div>
          )}

          {error && (
            <p className="mt-2 text-xs" style={{ color: 'var(--accent)' }}>{error}</p>
          )}
        </div>
      )}
    </div>
  )
}
