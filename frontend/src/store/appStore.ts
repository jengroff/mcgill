import { create } from 'zustand'

export type PhaseStatus = 'idle' | 'running' | 'done' | 'error'

export interface PhaseStep {
  phase: number
  label: string
  status: PhaseStatus
}

export interface ChatMessage {
  id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  timestamp: number
}

export interface CourseSource {
  code: string
  title: string
}

export interface AuthUser {
  id: number
  email: string
  name: string
}

export interface Toast {
  id: string
  message: string
  type: 'error' | 'info'
  action?: { label: string; fn: () => void }
}

interface AppState {
  // Auth
  user: AuthUser | null
  token: string | null

  // Chat
  sessionId: string | null
  connected: boolean
  steps: PhaseStep[]
  messages: ChatMessage[]
  sending: boolean
  sources: CourseSource[]

  // Pipeline
  pipelineRunId: string | null
  pipelineStatus: string | null

  // Toasts
  toasts: Toast[]

  setUser: (user: AuthUser | null) => void
  setToken: (token: string | null) => void
  loginUser: (token: string, user: AuthUser) => void
  logout: () => void
  setSessionId: (id: string) => void
  setConnected: (v: boolean) => void
  updateStep: (phase: number, label: string, status: PhaseStatus) => void
  addMessage: (role: ChatMessage['role'], content: string) => void
  setSending: (v: boolean) => void
  setSources: (s: CourseSource[]) => void
  setPipelineRunId: (id: string | null) => void
  setPipelineStatus: (s: string | null) => void
  addToast: (message: string, type?: 'error' | 'info', action?: { label: string; fn: () => void }) => void
  dismissToast: (id: string) => void
  reset: () => void
}

const initial = {
  user: null,
  token: localStorage.getItem('token'),
  sessionId: null,
  connected: false,
  steps: [],
  messages: [],
  sending: false,
  sources: [],
  pipelineRunId: null,
  pipelineStatus: null,
  toasts: [] as Toast[],
}

export const useAppStore = create<AppState>((set) => ({
  ...initial,

  setUser: (user) => set({ user }),
  setToken: (token) => {
    if (token) {
      localStorage.setItem('token', token)
    } else {
      localStorage.removeItem('token')
    }
    set({ token })
  },
  loginUser: (token, user) => {
    localStorage.setItem('token', token)
    set({ token, user })
  },
  logout: () => {
    localStorage.removeItem('token')
    set({ token: null, user: null })
  },

  setSessionId: (id) => set({ sessionId: id }),
  setConnected: (v) => set({ connected: v }),

  updateStep: (phase, label, status) =>
    set((s) => {
      const existing = s.steps.find((st) => st.phase === phase)
      if (existing) {
        return { steps: s.steps.map((st) => (st.phase === phase ? { ...st, status, label } : st)) }
      }
      return { steps: [...s.steps, { phase, label, status }] }
    }),

  addMessage: (role, content) =>
    set((s) => ({
      messages: [...s.messages, { id: crypto.randomUUID(), role, content, timestamp: Date.now() }],
      sending: role === 'assistant' ? false : s.sending,
    })),

  setSending: (v) => set({ sending: v }),
  setSources: (sources) => set({ sources }),
  setPipelineRunId: (id) => set({ pipelineRunId: id }),
  setPipelineStatus: (s) => set({ pipelineStatus: s }),
  addToast: (message, type = 'error', action) => {
    const id = crypto.randomUUID()
    set((s) => ({ toasts: [...s.toasts, { id, message, type, action }] }))
    setTimeout(() => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })), 5000)
  },
  dismissToast: (id) => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),
  reset: () => set({ ...initial, token: localStorage.getItem('token') }),
}))
