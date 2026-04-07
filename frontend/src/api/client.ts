const BASE = ''

function authHeaders(): Record<string, string> {
  const token = localStorage.getItem('token')
  return token ? { Authorization: `Bearer ${token}` } : {}
}

// --- Auth ---
export async function register(name: string, email: string, password: string) {
  const res = await fetch(`${BASE}/api/v1/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, email, password }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Registration failed' }))
    throw new Error(err.detail || 'Registration failed')
  }
  return res.json()
}

export async function login(email: string, password: string) {
  const res = await fetch(`${BASE}/api/v1/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Login failed' }))
    throw new Error(err.detail || 'Login failed')
  }
  return res.json()
}

export async function fetchMe() {
  const res = await fetch(`${BASE}/api/v1/auth/me`, {
    headers: authHeaders(),
  })
  if (!res.ok) throw new Error('Not authenticated')
  return res.json()
}

// --- Chat ---
export async function createSession(sessionId?: string): Promise<string> {
  const res = await fetch(`${BASE}/api/v1/chat/session`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify({ session_id: sessionId }),
  })
  const data = await res.json()
  return data.session_id
}

export async function sendMessage(sessionId: string, message: string) {
  await fetch(`${BASE}/api/v1/chat/ask`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify({ session_id: sessionId, message }),
  })
}

export function sseUrl(sessionId: string): string {
  return `${BASE}/api/v1/chat/stream?session_id=${sessionId}`
}

// --- Browse ---
export async function fetchFaculties() {
  const res = await fetch(`${BASE}/api/v1/faculties`)
  return res.json()
}

export async function fetchFaculty(slug: string) {
  const res = await fetch(`${BASE}/api/v1/faculties/${slug}`)
  return res.json()
}

export async function fetchDepartments(slug: string) {
  const res = await fetch(`${BASE}/api/v1/faculties/${slug}/departments`)
  return res.json()
}

export async function fetchDepartmentCourses(code: string) {
  const res = await fetch(`${BASE}/api/v1/departments/${code}/courses`)
  return res.json()
}

export async function fetchCourse(code: string) {
  const res = await fetch(`${BASE}/api/v1/courses/${encodeURIComponent(code)}`)
  return res.json()
}

export async function searchCourses(query: string, mode = 'keyword', topK = 10) {
  const params = new URLSearchParams({ q: query, mode, top_k: String(topK) })
  const res = await fetch(`${BASE}/api/v1/search?${params}`)
  return res.json()
}

export async function fetchPrereqTree(code: string) {
  const res = await fetch(`${BASE}/api/v1/graph/tree/${encodeURIComponent(code)}`)
  return res.json()
}

export interface CourseInfo {
  title: string
  credits: number | null
  terms: string[]
  description: string
  dept: string
  faculty: string
}

export async function fetchCourseBatch(codes: string[]): Promise<Record<string, CourseInfo>> {
  if (!codes.length) return {}
  const res = await fetch(`${BASE}/api/v1/courses/batch`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ codes }),
  })
  if (!res.ok) return {}
  return res.json()
}

// --- Pipeline ---
export async function triggerPipeline(config: {
  faculty_filter?: string[]
  dept_filter?: string[]
  max_course_pages?: number
  max_program_pages?: number
}) {
  const res = await fetch(`${BASE}/api/v1/pipeline/run`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(config),
  })
  return res.json()
}

export function pipelineStreamUrl(runId: string): string {
  return `${BASE}/api/v1/pipeline/stream/${runId}`
}

export async function fetchPipelineStatus(runId: string) {
  const res = await fetch(`${BASE}/api/v1/pipeline/status/${runId}`)
  return res.json()
}

// --- Programs ---
export interface ProgramInfo {
  slug: string
  title: string
  path: string
  faculty_slug: string
}

export interface FacultyPrograms {
  faculty_slug: string
  faculty_name: string
  programs: ProgramInfo[]
}

export async function fetchPrograms(): Promise<FacultyPrograms[]> {
  const res = await fetch(`${BASE}/api/v1/programs`)
  if (!res.ok) throw new Error('Failed to fetch programs')
  return res.json()
}

// --- Plans ---
export interface PlanSummary {
  id: number
  title: string
  program_slug: string | null
  status: string
  target_semesters: number
  created_at: string
  updated_at: string
}

export interface PlanSemester {
  id: number
  plan_id: number
  term: string
  sort_order: number
  courses: string[]
  total_credits: number
}

export interface PlanDocument {
  id: number
  plan_id: number
  filename: string
  content_type: string
  uploaded_at: string
}

export interface PlanDetail extends PlanSummary {
  student_interests: string[]
  completed_codes: string[]
  plan_markdown: string
  semesters: PlanSemester[]
  documents: PlanDocument[]
  conversation_ids: number[]
}

export async function fetchPlans(): Promise<PlanSummary[]> {
  const res = await fetch(`${BASE}/api/v1/plans`, { headers: authHeaders() })
  if (!res.ok) throw new Error('Failed to fetch plans')
  return res.json()
}

export async function createPlan(body: {
  title?: string
  program_slug?: string
  start_term?: string
  target_semesters?: number
  student_interests?: string[]
  completed_codes?: string[]
}): Promise<PlanDetail> {
  const res = await fetch(`${BASE}/api/v1/plans`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error('Failed to create plan')
  return res.json()
}

export async function fetchPlan(planId: number): Promise<PlanDetail> {
  const res = await fetch(`${BASE}/api/v1/plans/${planId}`, { headers: authHeaders() })
  if (!res.ok) throw new Error('Failed to fetch plan')
  return res.json()
}

export async function updatePlan(planId: number, body: Record<string, unknown>): Promise<PlanDetail> {
  const res = await fetch(`${BASE}/api/v1/plans/${planId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error('Failed to update plan')
  return res.json()
}

export async function deletePlan(planId: number): Promise<void> {
  const res = await fetch(`${BASE}/api/v1/plans/${planId}`, {
    method: 'DELETE',
    headers: authHeaders(),
  })
  if (!res.ok) throw new Error('Failed to delete plan')
}

export async function addSemester(planId: number, body: {
  term: string
  sort_order: number
  courses?: string[]
  total_credits?: number
}): Promise<PlanSemester> {
  const res = await fetch(`${BASE}/api/v1/plans/${planId}/semesters`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error('Failed to add semester')
  return res.json()
}

export async function updateSemester(planId: number, semId: number, body: {
  term: string
  sort_order: number
  courses: string[]
  total_credits: number
}): Promise<PlanSemester> {
  const res = await fetch(`${BASE}/api/v1/plans/${planId}/semesters/${semId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json', ...authHeaders() },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error('Failed to update semester')
  return res.json()
}

export async function deleteSemester(planId: number, semId: number): Promise<void> {
  const res = await fetch(`${BASE}/api/v1/plans/${planId}/semesters/${semId}`, {
    method: 'DELETE',
    headers: authHeaders(),
  })
  if (!res.ok) throw new Error('Failed to delete semester')
}

export async function uploadPlanDocument(planId: number, file: File): Promise<PlanDocument> {
  const form = new FormData()
  form.append('file', file)
  const res = await fetch(`${BASE}/api/v1/plans/${planId}/documents`, {
    method: 'POST',
    headers: authHeaders(),
    body: form,
  })
  if (!res.ok) throw new Error('Failed to upload document')
  return res.json()
}

export async function deletePlanDocument(planId: number, docId: number): Promise<void> {
  const res = await fetch(`${BASE}/api/v1/plans/${planId}/documents/${docId}`, {
    method: 'DELETE',
    headers: authHeaders(),
  })
  if (!res.ok) throw new Error('Failed to delete document')
}

export async function generatePlan(planId: number): Promise<PlanDetail> {
  const res = await fetch(`${BASE}/api/v1/plans/${planId}/generate`, {
    method: 'POST',
    headers: authHeaders(),
  })
  if (!res.ok) throw new Error('Failed to generate plan')
  return res.json()
}

// --- Health ---
export async function fetchHealth() {
  const res = await fetch(`${BASE}/health`)
  return res.json()
}
