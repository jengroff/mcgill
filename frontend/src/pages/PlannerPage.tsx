import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { Plus, FileText, Trash2, Upload, X, ChevronDown, ChevronRight, Sparkles, Loader2 } from 'lucide-react'
import Markdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { useAppStore } from '../store/appStore'
import { usePlanStore } from '../store/planStore'
import {
  fetchPlans,
  createPlan,
  fetchPlan,
  updatePlan,
  deletePlan,
  addSemester,
  updateSemester,
  deleteSemester,
  uploadPlanDocument,
  deletePlanDocument,
  fetchPrograms,
  fetchCourseBatch,
  generatePlan,
  createSession,
  sendMessage,
  sseUrl,
} from '../api/client'
import type { PlanDetail, PlanSemester, FacultyPrograms, CourseInfo } from '../api/client'

export default function PlannerPage() {
  const user = useAppStore((s) => s.user)
  const addToast = useAppStore((s) => s.addToast)
  const { plans, activePlan, loading, setPlans, setActivePlan, setLoading } = usePlanStore()
  const [showNewPlan, setShowNewPlan] = useState(false)
  const [showDocs, setShowDocs] = useState(false)

  useEffect(() => {
    if (!user) return
    setLoading(true)
    fetchPlans()
      .then(setPlans)
      .catch(() => addToast('Failed to load plans'))
      .finally(() => setLoading(false))
  }, [user])

  if (!user) return null

  async function handleCreatePlan(opts: {
    title: string
    interests: string
    programSlug?: string
    startTerm?: string
  }) {
    try {
      const plan = await createPlan({
        title: opts.title || 'My Course Plan',
        student_interests: opts.interests ? opts.interests.split(',').map((s) => s.trim()) : [],
        program_slug: opts.programSlug || undefined,
        start_term: opts.startTerm || undefined,
      })
      setActivePlan(plan)
      setShowNewPlan(false)
      const updated = await fetchPlans()
      setPlans(updated)
    } catch {
      addToast('Failed to create plan')
    }
  }

  async function handleSelectPlan(id: number) {
    setLoading(true)
    try {
      const plan = await fetchPlan(id)
      setActivePlan(plan)
    } catch {
      addToast('Failed to load plan')
    }
    setLoading(false)
  }

  async function handleDeletePlan(id: number) {
    try { await deletePlan(id) } catch { addToast('Failed to delete plan'); return }
    if (activePlan?.id === id) setActivePlan(null)
    const updated = await fetchPlans()
    setPlans(updated)
  }

  return (
    <div className="h-full flex flex-col md:flex-row overflow-hidden">
      {/* Mobile plan selector */}
      <div className="md:hidden flex items-center gap-2 px-4 py-2 border-b" style={{ borderColor: 'var(--border)', background: 'var(--bg-surface)' }}>
        <select
          value={activePlan?.id ?? ''}
          onChange={(e) => { const id = Number(e.target.value); if (id) handleSelectPlan(id) }}
          className="flex-1 rounded-lg px-3 py-2 text-sm outline-none"
          style={{ background: 'var(--bg-elevated)', color: 'var(--text-primary)', border: '1px solid var(--border)' }}
        >
          <option value="">Select a plan</option>
          {plans.map((p) => (
            <option key={p.id} value={p.id}>{p.title}</option>
          ))}
        </select>
        <button
          onClick={() => setShowNewPlan(true)}
          className="p-2 rounded cursor-pointer flex-shrink-0"
          style={{ background: 'var(--accent)', color: '#fff', border: 'none' }}
          title="New plan"
        >
          <Plus size={14} />
        </button>
      </div>

      {/* Left: Plan list (desktop only) */}
      <div className="hidden md:flex w-64 flex-shrink-0 border-r flex-col" style={{ borderColor: 'var(--border)', background: 'var(--bg-surface)' }}>
        <div className="p-3 border-b flex items-center justify-between" style={{ borderColor: 'var(--border)' }}>
          <span className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>Plans</span>
          <button
            onClick={() => setShowNewPlan(true)}
            className="p-1 rounded cursor-pointer"
            style={{ background: 'var(--accent)', color: '#fff', border: 'none' }}
            title="New plan"
          >
            <Plus size={14} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-2 space-y-1">
          {loading && plans.length === 0 && (
            <p className="text-xs p-2" style={{ color: 'var(--text-muted)' }}>Loading...</p>
          )}
          {plans.map((p) => (
            <div
              key={p.id}
              onClick={() => handleSelectPlan(p.id)}
              className="flex items-center justify-between p-2 rounded cursor-pointer group"
              style={{
                background: activePlan?.id === p.id ? 'var(--bg-elevated)' : 'transparent',
                border: activePlan?.id === p.id ? '1px solid var(--border)' : '1px solid transparent',
              }}
            >
              <div className="min-w-0 flex-1">
                <p className="text-xs font-medium truncate" style={{ color: 'var(--text-primary)' }}>{p.title}</p>
                <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
                  {p.status} &middot; {p.target_semesters} sem
                </p>
              </div>
              <button
                onClick={(e) => { e.stopPropagation(); handleDeletePlan(p.id) }}
                className="opacity-0 group-hover:opacity-100 p-1 rounded cursor-pointer"
                style={{ background: 'none', border: 'none', color: 'var(--text-muted)' }}
              >
                <Trash2 size={12} />
              </button>
            </div>
          ))}
          {!loading && plans.length === 0 && (
            <p className="text-xs p-2 text-center" style={{ color: 'var(--text-muted)' }}>
              No plans yet. Create one to get started.
            </p>
          )}
        </div>
      </div>

      {/* Center: Plan detail */}
      <div className="flex-1 overflow-y-auto">
        {showNewPlan ? (
          <NewPlanForm
            onCreate={handleCreatePlan}
            onCancel={() => setShowNewPlan(false)}
          />
        ) : activePlan ? (
          <PlanDetailView
            plan={activePlan}
            showDocs={showDocs}
            onToggleDocs={() => setShowDocs(!showDocs)}
          />
        ) : (
          <div className="flex items-center justify-center h-full">
            <div className="text-center">
              <CalendarDaysIcon />
              <p className="text-sm font-medium mt-3" style={{ color: 'var(--text-primary)' }}>Select or create a plan</p>
              <p className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>
                Plan your semesters, upload transcripts, and track progress
              </p>
            </div>
          </div>
        )}
      </div>

      {/* Right: Advisor chat (hidden on mobile) */}
      {activePlan && !showNewPlan && (
        <div className="hidden lg:flex">
          <PlanAdvisorChat planId={activePlan.id} planTitle={activePlan.title} />
        </div>
      )}
    </div>
  )
}

function CalendarDaysIcon() {
  return (
    <div className="w-12 h-12 rounded-xl flex items-center justify-center mx-auto" style={{ background: 'var(--bg-elevated)', border: '1px solid var(--border)' }}>
      <span className="text-xl">📋</span>
    </div>
  )
}


// ---------------------------------------------------------------------------
// New Plan Form
// ---------------------------------------------------------------------------

function NewPlanForm({ onCreate, onCancel }: {
  onCreate: (opts: { title: string; interests: string; programSlug?: string; startTerm?: string }) => void
  onCancel: () => void
}) {
  const [title, setTitle] = useState('')
  const [interests, setInterests] = useState('')
  const [faculties, setFaculties] = useState<FacultyPrograms[]>([])
  const [selectedFaculty, setSelectedFaculty] = useState('')
  const [selectedProgram, setSelectedProgram] = useState('')
  const [startSeason, setStartSeason] = useState('Fall')
  const [startYear, setStartYear] = useState(new Date().getFullYear())
  const [loadingPrograms, setLoadingPrograms] = useState(true)

  useEffect(() => {
    fetchPrograms()
      .then(setFaculties)
      .catch(() => {})
      .finally(() => setLoadingPrograms(false))
  }, [])

  const programs = faculties.find((f) => f.faculty_slug === selectedFaculty)?.programs ?? []

  function handleFacultyChange(slug: string) {
    setSelectedFaculty(slug)
    setSelectedProgram('')
  }

  function handleProgramChange(slug: string) {
    setSelectedProgram(slug)
    const prog = programs.find((p) => p.slug === slug)
    if (prog && !title) setTitle(prog.title)
  }

  const inputStyle = {
    background: 'var(--bg-elevated)',
    color: 'var(--text-primary)',
    border: '1px solid var(--border)',
  }

  return (
    <div className="max-w-lg mx-auto p-8">
      <h2 className="text-lg font-semibold mb-4" style={{ color: 'var(--text-primary)' }}>New Plan</h2>
      <div className="space-y-4">
        {/* Program picker */}
        <div>
          <label className="block text-xs mb-1" style={{ color: 'var(--text-muted)' }}>Faculty</label>
          <select
            value={selectedFaculty}
            onChange={(e) => handleFacultyChange(e.target.value)}
            className="w-full rounded-lg px-3 py-2 text-sm outline-none cursor-pointer"
            style={inputStyle}
            disabled={loadingPrograms}
          >
            <option value="">{loadingPrograms ? 'Loading...' : 'Select a faculty (optional)'}</option>
            {faculties.map((f) => (
              <option key={f.faculty_slug} value={f.faculty_slug}>{f.faculty_name}</option>
            ))}
          </select>
        </div>

        {selectedFaculty && programs.length > 0 && (
          <div>
            <label className="block text-xs mb-1" style={{ color: 'var(--text-muted)' }}>Program</label>
            <select
              value={selectedProgram}
              onChange={(e) => handleProgramChange(e.target.value)}
              className="w-full rounded-lg px-3 py-2 text-sm outline-none cursor-pointer"
              style={inputStyle}
            >
              <option value="">Select a program</option>
              {programs.map((p) => (
                <option key={p.slug} value={p.slug}>{p.title}</option>
              ))}
            </select>
          </div>
        )}

        {/* Start term */}
        <div>
          <label className="block text-xs mb-1" style={{ color: 'var(--text-muted)' }}>Start Term</label>
          <div className="flex gap-2">
            <select
              value={startSeason}
              onChange={(e) => setStartSeason(e.target.value)}
              className="rounded-lg px-3 py-2 text-sm outline-none cursor-pointer"
              style={inputStyle}
            >
              <option value="Fall">Fall</option>
              <option value="Winter">Winter</option>
            </select>
            <input
              type="number"
              value={startYear}
              onChange={(e) => setStartYear(parseInt(e.target.value) || new Date().getFullYear())}
              className="w-24 rounded-lg px-3 py-2 text-sm outline-none"
              style={inputStyle}
              min={2020}
              max={2035}
            />
          </div>
        </div>

        {/* Title */}
        <div>
          <label className="block text-xs mb-1" style={{ color: 'var(--text-muted)' }}>Plan Title</label>
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="e.g. Food Science Year 1"
            className="w-full rounded-lg px-3 py-2 text-sm outline-none"
            style={inputStyle}
          />
        </div>

        {/* Interests */}
        <div>
          <label className="block text-xs mb-1" style={{ color: 'var(--text-muted)' }}>Interests (comma-separated)</label>
          <input
            value={interests}
            onChange={(e) => setInterests(e.target.value)}
            placeholder="e.g. food chemistry, biology, mathematics"
            className="w-full rounded-lg px-3 py-2 text-sm outline-none"
            style={inputStyle}
          />
        </div>

        <div className="flex gap-2">
          <button
            onClick={() => onCreate({
              title,
              interests,
              programSlug: selectedProgram || undefined,
              startTerm: `${startSeason} ${startYear}`,
            })}
            className="px-4 py-2 rounded-lg text-sm cursor-pointer"
            style={{ background: 'var(--accent)', color: '#fff', border: 'none' }}
          >
            Create Plan
          </button>
          <button
            onClick={onCancel}
            className="px-4 py-2 rounded-lg text-sm cursor-pointer"
            style={{ background: 'var(--bg-elevated)', color: 'var(--text-primary)', border: '1px solid var(--border)' }}
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  )
}


// ---------------------------------------------------------------------------
// Plan Detail View
// ---------------------------------------------------------------------------

function PlanDetailView({ plan, showDocs, onToggleDocs }: { plan: PlanDetail; showDocs: boolean; onToggleDocs: () => void }) {
  const { setActivePlan } = usePlanStore()
  const addToast = useAppStore((s) => s.addToast)
  const [addingTerm, setAddingTerm] = useState('')
  const [addingCourse, setAddingCourse] = useState<{ semId: number; code: string } | null>(null)
  const [courseDetails, setCourseDetails] = useState<Record<string, CourseInfo>>({})
  const [generating, setGenerating] = useState(false)
  const [uploading, setUploading] = useState(false)

  useEffect(() => {
    const allCodes = plan.semesters.flatMap((s) => s.courses)
    const missing = allCodes.filter((c) => !courseDetails[c])
    if (missing.length > 0) {
      fetchCourseBatch(missing).then((details) =>
        setCourseDetails((prev) => ({ ...prev, ...details }))
      ).catch(() => {})
    }
  }, [plan.semesters])

  async function handleGenerate() {
    setGenerating(true)
    try {
      const updated = await generatePlan(plan.id)
      setActivePlan(updated)
    } catch {
      addToast('Plan generation failed — check that the API key is configured', 'error', { label: 'Retry', fn: handleGenerate })
    }
    setGenerating(false)
  }

  async function handleAddSemester() {
    if (!addingTerm.trim()) return
    const maxOrder = plan.semesters.reduce((m, s) => Math.max(m, s.sort_order), -1)
    const sem = await addSemester(plan.id, {
      term: addingTerm.trim(),
      sort_order: maxOrder + 1,
    })
    setActivePlan({ ...plan, semesters: [...plan.semesters, sem] })
    setAddingTerm('')
  }

  async function handleRemoveSemester(semId: number) {
    await deleteSemester(plan.id, semId)
    setActivePlan({ ...plan, semesters: plan.semesters.filter((s) => s.id !== semId) })
  }

  async function handleAddCourse(sem: PlanSemester) {
    if (!addingCourse || !addingCourse.code.trim()) return
    const courses = [...sem.courses, addingCourse.code.trim().toUpperCase()]
    const updated = await updateSemester(plan.id, sem.id, {
      term: sem.term,
      sort_order: sem.sort_order,
      courses,
      total_credits: courses.length * 3, // rough estimate
    })
    setActivePlan({
      ...plan,
      semesters: plan.semesters.map((s) => (s.id === sem.id ? updated : s)),
    })
    setAddingCourse(null)
  }

  async function handleRemoveCourse(sem: PlanSemester, courseCode: string) {
    const courses = sem.courses.filter((c) => c !== courseCode)
    const updated = await updateSemester(plan.id, sem.id, {
      term: sem.term,
      sort_order: sem.sort_order,
      courses,
      total_credits: courses.length * 3,
    })
    setActivePlan({
      ...plan,
      semesters: plan.semesters.map((s) => (s.id === sem.id ? updated : s)),
    })
  }

  async function handleUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    setUploading(true)
    try {
      const doc = await uploadPlanDocument(plan.id, file)
      setActivePlan({ ...plan, documents: [...plan.documents, doc] })
    } catch {
      addToast(`Failed to upload ${file.name}`)
    }
    setUploading(false)
    // Reset input so the same file can be re-selected
    e.target.value = ''
  }

  async function handleDeleteDoc(docId: number) {
    try {
      await deletePlanDocument(plan.id, docId)
      setActivePlan({ ...plan, documents: plan.documents.filter((d) => d.id !== docId) })
    } catch {
      addToast('Failed to delete document')
    }
  }

  async function handleStatusChange(status: string) {
    const updated = await updatePlan(plan.id, { status })
    setActivePlan({ ...plan, status: updated.status })
  }

  const totalCredits = plan.semesters.reduce((t, s) => t + s.total_credits, 0)

  return (
    <div className="p-6 max-w-4xl mx-auto">
      {/* Header */}
      <div className="flex items-start justify-between mb-6">
        <div>
          <h2 className="text-xl font-bold" style={{ color: 'var(--text-primary)' }}>{plan.title}</h2>
          <p className="text-xs mt-1" style={{ color: 'var(--text-muted)' }}>
            {plan.target_semesters} semesters &middot; {totalCredits} credits planned
            {plan.student_interests.length > 0 && (
              <> &middot; {plan.student_interests.join(', ')}</>
            )}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={handleGenerate}
            disabled={generating || plan.semesters.length === 0}
            className="flex items-center gap-1 px-3 py-1 rounded-lg text-xs cursor-pointer"
            style={{
              background: 'var(--accent)',
              color: '#fff',
              border: 'none',
              opacity: generating || plan.semesters.length === 0 ? 0.5 : 1,
            }}
          >
            {generating ? <Loader2 size={12} className="animate-spin" /> : <Sparkles size={12} />}
            {generating ? 'Analyzing...' : plan.plan_markdown ? 'Regenerate' : 'Explain Plan'}
          </button>
          <select
            value={plan.status}
            onChange={(e) => handleStatusChange(e.target.value)}
            className="text-xs rounded px-2 py-1 cursor-pointer"
            style={{ background: 'var(--bg-elevated)', color: 'var(--text-primary)', border: '1px solid var(--border)' }}
          >
            <option value="draft">Draft</option>
            <option value="active">Active</option>
            <option value="archived">Archived</option>
          </select>
        </div>
      </div>

      {/* Documents drawer toggle */}
      <button
        onClick={onToggleDocs}
        className="flex items-center gap-2 text-xs mb-4 cursor-pointer"
        style={{ background: 'none', border: 'none', color: 'var(--text-muted)' }}
      >
        {showDocs ? <ChevronDown size={12} /> : <ChevronRight size={12} />}
        <FileText size={12} />
        Documents ({plan.documents.length})
      </button>

      {showDocs && (
        <div className="mb-6 p-3 rounded-lg" style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)' }}>
          <div className="flex items-center gap-2 mb-2">
            <label
              className="flex items-center gap-1 text-xs px-2 py-1 rounded cursor-pointer"
              style={{ background: 'var(--accent)', color: '#fff', opacity: uploading ? 0.6 : 1 }}
            >
              {uploading ? <Loader2 size={12} className="animate-spin" /> : <Upload size={12} />}
              {uploading ? 'Uploading...' : 'Upload'}
              <input type="file" className="hidden" onChange={handleUpload} accept=".pdf,.txt,.csv,.xlsx" disabled={uploading} />
            </label>
            <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
              Transcripts, AP score reports, course guides
            </span>
          </div>
          {plan.documents.length > 0 && (
            <div className="space-y-1">
              {plan.documents.map((doc) => (
                <div key={doc.id} className="flex items-center justify-between text-xs py-1">
                  <span style={{ color: 'var(--text-primary)' }}>{doc.filename}</span>
                  <button
                    onClick={() => handleDeleteDoc(doc.id)}
                    className="p-1 rounded cursor-pointer"
                    style={{ background: 'none', border: 'none', color: 'var(--text-muted)' }}
                  >
                    <X size={12} />
                  </button>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Semester grid */}
      <div className="space-y-4">
        {plan.semesters.map((sem) => (
          <div key={sem.id} className="rounded-lg p-4" style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)' }}>
            <div className="flex items-center justify-between mb-3">
              <h3 className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>
                {sem.term}
              </h3>
              <div className="flex items-center gap-2">
                <span className="text-xs" style={{ color: 'var(--text-muted)' }}>
                  {sem.total_credits} credits
                </span>
                <button
                  onClick={() => handleRemoveSemester(sem.id)}
                  className="p-1 rounded cursor-pointer"
                  style={{ background: 'none', border: 'none', color: 'var(--text-muted)' }}
                  title="Remove semester"
                >
                  <Trash2 size={12} />
                </button>
              </div>
            </div>

            <div className="space-y-1.5">
              {sem.courses.map((code) => {
                const info = courseDetails[code]
                return (
                  <div
                    key={code}
                    className="flex items-center gap-2 px-3 py-2 rounded-lg text-xs group"
                    style={{ background: 'var(--bg-elevated)', border: '1px solid var(--border)' }}
                  >
                    <Link
                      to={`/course/${code.replace(' ', '-')}`}
                      className="flex-1 min-w-0 no-underline"
                      style={{ color: 'var(--text-primary)' }}
                    >
                      <span className="font-mono font-semibold" style={{ color: 'var(--accent)' }}>{code}</span>
                      {info && (
                        <span className="ml-1.5" style={{ color: 'var(--text-muted)' }}>
                          {info.title}
                          {info.credits != null && <> &middot; {info.credits} cr</>}
                        </span>
                      )}
                    </Link>
                    <button
                      onClick={() => handleRemoveCourse(sem, code)}
                      className="opacity-0 group-hover:opacity-100 cursor-pointer flex-shrink-0"
                      style={{ background: 'none', border: 'none', color: 'var(--text-muted)', padding: 0 }}
                    >
                      <X size={12} />
                    </button>
                  </div>
                )
              })}

              {addingCourse?.semId === sem.id ? (
                <input
                  autoFocus
                  value={addingCourse.code}
                  onChange={(e) => setAddingCourse({ semId: sem.id, code: e.target.value })}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') handleAddCourse(sem)
                    if (e.key === 'Escape') setAddingCourse(null)
                  }}
                  onBlur={() => setAddingCourse(null)}
                  placeholder="COMP 250"
                  className="px-2 py-1 rounded text-xs w-24 outline-none"
                  style={{ background: 'var(--bg-elevated)', color: 'var(--text-primary)', border: '1px solid var(--accent)' }}
                />
              ) : (
                <button
                  onClick={() => setAddingCourse({ semId: sem.id, code: '' })}
                  className="px-2 py-1 rounded text-xs cursor-pointer"
                  style={{ background: 'none', color: 'var(--text-muted)', border: '1px dashed var(--border)' }}
                >
                  + Add Course
                </button>
              )}
            </div>
          </div>
        ))}

        {/* Add semester */}
        <div className="flex items-center gap-2">
          <input
            value={addingTerm}
            onChange={(e) => setAddingTerm(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter') handleAddSemester() }}
            placeholder="e.g. Fall 2026"
            className="px-3 py-2 rounded-lg text-sm outline-none"
            style={{ background: 'var(--bg-elevated)', color: 'var(--text-primary)', border: '1px solid var(--border)' }}
          />
          <button
            onClick={handleAddSemester}
            disabled={!addingTerm.trim()}
            className="px-3 py-2 rounded-lg text-sm cursor-pointer"
            style={{ background: 'var(--accent)', color: '#fff', border: 'none', opacity: addingTerm.trim() ? 1 : 0.4 }}
          >
            Add Semester
          </button>
        </div>
      </div>

      {/* Plan markdown (from AI planner) */}
      {plan.plan_markdown && (
        <div className="mt-8 p-4 rounded-lg" style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)' }}>
          <h3 className="text-sm font-semibold mb-3" style={{ color: 'var(--text-primary)' }}>AI-Generated Plan</h3>
          <div className="text-sm leading-relaxed prose-sm" style={{ color: 'var(--text-primary)' }}>
            <Markdown remarkPlugins={[remarkGfm]}>{plan.plan_markdown}</Markdown>
          </div>
        </div>
      )}
    </div>
  )
}


// ---------------------------------------------------------------------------
// Plan Advisor Chat Panel
// ---------------------------------------------------------------------------

interface AdvisorMessage {
  id: string
  role: 'user' | 'assistant' | 'system'
  content: string
}

function PlanAdvisorChat({ planId, planTitle }: { planId: number; planTitle: string }) {
  const [sessionId, setSessionId] = useState<string | null>(null)
  const [messages, setMessages] = useState<AdvisorMessage[]>([])
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [width, setWidth] = useState(384)
  const scrollRef = useRef<HTMLDivElement>(null)
  const esRef = useRef<EventSource | null>(null)
  const dragRef = useRef<{ startX: number; startW: number } | null>(null)

  // Create session and connect SSE when plan changes
  useEffect(() => {
    let es: EventSource | null = null

    async function init() {
      const sid = await createSession()
      setSessionId(sid)
      setMessages([{
        id: 'welcome',
        role: 'assistant',
        content: `I'm your advisor for **${planTitle}**. Ask me anything about your courses, schedule, or upload documents for analysis.`,
      }])

      es = new EventSource(sseUrl(sid))
      esRef.current = es

      es.onmessage = (ev) => {
        try {
          const data = JSON.parse(ev.data)
          if (data.type === 'assistant' && data.content) {
            setMessages((prev) => [...prev, {
              id: crypto.randomUUID(),
              role: 'assistant',
              content: data.content,
            }])
            setSending(false)
          } else if (data.type === 'error' && data.content) {
            setMessages((prev) => [...prev, {
              id: crypto.randomUUID(),
              role: 'system',
              content: data.content,
            }])
            setSending(false)
          }
        } catch { /* ignore */ }
      }
    }

    init()
    return () => {
      es?.close()
      esRef.current = null
    }
  }, [planId])

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
  }, [messages])

  async function handleSend() {
    const text = input.trim()
    if (!text || !sessionId || sending) return
    setInput('')
    setSending(true)
    setMessages((prev) => [...prev, { id: crypto.randomUUID(), role: 'user', content: text }])
    try {
      await sendMessage(sessionId, text, planId)
    } catch {
      setSending(false)
    }
  }

  function handleDragStart(e: React.MouseEvent) {
    e.preventDefault()
    dragRef.current = { startX: e.clientX, startW: width }
    const handleMove = (ev: MouseEvent) => {
      if (!dragRef.current) return
      const delta = dragRef.current.startX - ev.clientX
      setWidth(Math.max(280, Math.min(800, dragRef.current.startW + delta)))
    }
    const handleUp = () => {
      dragRef.current = null
      document.removeEventListener('mousemove', handleMove)
      document.removeEventListener('mouseup', handleUp)
    }
    document.addEventListener('mousemove', handleMove)
    document.addEventListener('mouseup', handleUp)
  }

  return (
    <div
      className="flex-shrink-0 flex"
      style={{ width }}
    >
      {/* Drag handle */}
      <div
        onMouseDown={handleDragStart}
        className="w-1 cursor-col-resize hover:bg-[var(--accent)]"
        style={{ background: 'var(--border)' }}
      />
      <div
        className="flex-1 border-l flex flex-col min-w-0"
        style={{ borderColor: 'var(--border)', background: 'var(--bg-surface)' }}
      >
      <div className="p-3 border-b" style={{ borderColor: 'var(--border)' }}>
        <div className="flex items-center gap-2">
          <Sparkles size={14} style={{ color: 'var(--accent)' }} />
          <span className="text-sm font-semibold" style={{ color: 'var(--text-primary)' }}>Advisor</span>
        </div>
      </div>

      <div ref={scrollRef} className="flex-1 overflow-y-auto p-3 space-y-3">
        {messages.map((m) => (
          <div
            key={m.id}
            className={`text-xs leading-relaxed ${m.role === 'user' ? 'text-right' : ''}`}
          >
            <div
              className="inline-block rounded-lg px-3 py-2 max-w-[90%]"
              style={{
                background: m.role === 'user' ? 'var(--accent)' : 'var(--bg-elevated)',
                color: m.role === 'user' ? '#fff' : 'var(--text-primary)',
                textAlign: 'left',
              }}
            >
              {m.role === 'assistant' || m.role === 'system' ? (
                <Markdown remarkPlugins={[remarkGfm]}>{m.content}</Markdown>
              ) : (
                m.content
              )}
            </div>
          </div>
        ))}
        {sending && (
          <div className="text-xs" style={{ color: 'var(--text-muted)' }}>
            <span className="animate-pulse">Thinking...</span>
          </div>
        )}
      </div>

      <div className="p-3 border-t" style={{ borderColor: 'var(--border)' }}>
        <div className="flex gap-2">
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); handleSend() } }}
            placeholder=""
            disabled={sending || !sessionId}
            className="flex-1 rounded-lg px-3 py-2 text-xs outline-none"
            style={{ background: 'var(--bg-elevated)', color: 'var(--text-primary)', border: '1px solid var(--border)' }}
          />
          <button
            onClick={handleSend}
            disabled={sending || !input.trim() || !sessionId}
            className="px-3 py-2 rounded-lg text-xs cursor-pointer"
            style={{ background: 'var(--accent)', color: '#fff', border: 'none', opacity: sending || !input.trim() ? 0.5 : 1 }}
          >
            Send
          </button>
        </div>
      </div>
      </div>
    </div>
  )
}
