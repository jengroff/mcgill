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

// --- Health ---
export async function fetchHealth() {
  const res = await fetch(`${BASE}/health`)
  return res.json()
}
