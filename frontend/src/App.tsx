import { useEffect, useRef } from 'react'
import { Routes, Route, useLocation } from 'react-router-dom'
import Header from './components/Header'
import AuthPrompt from './components/AuthPrompt'
import Toasts from './components/Toasts'
import BrowsePage from './pages/BrowsePage'
import FacultyPage from './pages/FacultyPage'
import DepartmentPage from './pages/DepartmentPage'
import CoursePage from './pages/CoursePage'
import ChatPage from './pages/ChatPage'
import PlannerPage from './pages/PlannerPage'
import GuidePage from './pages/GuidePage'
import { useAppStore } from './store/appStore'
import { fetchMe, createSession, sseUrl } from './api/client'

export default function App() {
  const token = useAppStore((s) => s.token)
  const setUser = useAppStore((s) => s.setUser)
  const logout = useAppStore((s) => s.logout)
  const sessionId = useAppStore((s) => s.sessionId)
  const setSessionId = useAppStore((s) => s.setSessionId)
  const setConnected = useAppStore((s) => s.setConnected)
  const addMessage = useAppStore((s) => s.addMessage)
  const streamToken = useAppStore((s) => s.streamToken)
  const finalizeStream = useAppStore((s) => s.finalizeStream)
  const updateStep = useAppStore((s) => s.updateStep)
  const setSources = useAppStore((s) => s.setSources)
  const esRef = useRef<EventSource | null>(null)

  useEffect(() => {
    if (!token) return
    fetchMe()
      .then(setUser)
      .catch(() => logout())
  }, [token])

  // Establish SSE connection on app load so Live indicator works on all tabs
  useEffect(() => {
    async function connect() {
      const sid = sessionId ?? await createSession()
      if (!sessionId) setSessionId(sid)

      const es = new EventSource(sseUrl(sid))
      esRef.current = es
      es.onopen = () => setConnected(true)
      es.onerror = () => setConnected(false)

      es.onmessage = (ev) => {
        try {
          const data = JSON.parse(ev.data)
          if (data.type === 'token') {
            streamToken(data.content)
          } else if (data.type === 'assistant_done') {
            finalizeStream()
          } else if (data.type === 'assistant') {
            addMessage('assistant', data.content)
          } else if (data.type === 'step_update') {
            updateStep(data.phase, data.label, data.status)
          } else if (data.type === 'error') {
            addMessage('system', data.content)
          } else if (data.type === 'sources') {
            setSources(data.sources ?? [])
          }
        } catch { /* ignore */ }
      }
    }

    connect()
    return () => { esRef.current?.close() }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const user = useAppStore((s) => s.user)
  const location = useLocation()
  const isPublicRoute = location.pathname === '/guide'

  return (
    <div className="h-screen flex flex-col" style={{ background: 'var(--bg-primary)' }}>
      <Header />
      <main className="flex-1 overflow-hidden relative">
        <Routes>
          <Route path="/" element={<BrowsePage />} />
          <Route path="/faculty/:slug" element={<FacultyPage />} />
          <Route path="/dept/:code" element={<DepartmentPage />} />
          <Route path="/course/:code" element={<CoursePage />} />
          <Route path="/chat" element={<ChatPage />} />
          <Route path="/planner" element={<PlannerPage />} />
          <Route path="/guide" element={<GuidePage />} />
        </Routes>
        {!user && !isPublicRoute && (
          <div
            className="absolute inset-0 z-50 flex items-center justify-center"
            style={{ background: 'rgba(0, 0, 0, 0.6)', backdropFilter: 'blur(4px)' }}
          >
            <AuthPrompt />
          </div>
        )}
      </main>
      <Toasts />
    </div>
  )
}
