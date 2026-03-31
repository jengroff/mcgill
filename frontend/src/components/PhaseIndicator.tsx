import { CheckCircle, Circle, Loader } from 'lucide-react'
import { useAppStore, type PhaseStep } from '../store/appStore'

const PHASE_COLORS: Record<number, string> = {
  1: 'var(--phase1)',
  2: 'var(--phase2)',
  3: 'var(--phase3)',
}

const PHASE_LABELS: Record<number, string> = {
  1: 'Scrape',
  2: 'Resolve',
  3: 'Embed',
}

function StepIcon({ step }: { step: PhaseStep }) {
  const color = PHASE_COLORS[step.phase] ?? 'var(--text-muted)'
  if (step.status === 'done') return <CheckCircle size={16} style={{ color }} />
  if (step.status === 'running') return <Loader size={16} className="animate-spin" style={{ color }} />
  return <Circle size={16} style={{ color: 'var(--border)' }} />
}

export default function PhaseIndicator() {
  const steps = useAppStore((s) => s.steps)

  if (steps.length === 0) return null

  return (
    <div className="flex flex-col gap-2 p-4 rounded-lg" style={{ background: 'var(--bg-elevated)' }}>
      <p className="text-xs font-medium uppercase tracking-wide" style={{ color: 'var(--text-muted)' }}>Pipeline</p>
      {steps.map((step) => (
        <div key={step.phase} className="flex items-center gap-2 text-xs">
          <StepIcon step={step} />
          <span style={{ color: step.status === 'idle' ? 'var(--text-muted)' : 'var(--text-primary)' }}>
            {PHASE_LABELS[step.phase] ?? `Phase ${step.phase}`}: {step.label}
          </span>
        </div>
      ))}
    </div>
  )
}
