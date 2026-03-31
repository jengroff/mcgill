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

interface AppState {
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

  setSessionId: (id: string) => void
  setConnected: (v: boolean) => void
  updateStep: (phase: number, label: string, status: PhaseStatus) => void
  addMessage: (role: ChatMessage['role'], content: string) => void
  setSending: (v: boolean) => void
  setSources: (s: CourseSource[]) => void
  setPipelineRunId: (id: string | null) => void
  setPipelineStatus: (s: string | null) => void
  reset: () => void
}

const initial = {
  sessionId: null,
  connected: false,
  steps: [],
  messages: [],
  sending: false,
  sources: [],
  pipelineRunId: null,
  pipelineStatus: null,
}

export const useAppStore = create<AppState>((set) => ({
  ...initial,

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
  reset: () => set(initial),
}))
