import { Routes, Route } from 'react-router-dom'
import Header from './components/Header'
import BrowsePage from './pages/BrowsePage'
import FacultyPage from './pages/FacultyPage'
import DepartmentPage from './pages/DepartmentPage'
import CoursePage from './pages/CoursePage'
import ChatPage from './pages/ChatPage'

export default function App() {
  return (
    <div className="h-screen flex flex-col" style={{ background: 'var(--bg-primary)' }}>
      <Header />
      <main className="flex-1 overflow-hidden">
        <Routes>
          <Route path="/" element={<BrowsePage />} />
          <Route path="/faculty/:slug" element={<FacultyPage />} />
          <Route path="/dept/:code" element={<DepartmentPage />} />
          <Route path="/course/:code" element={<CoursePage />} />
          <Route path="/chat" element={<ChatPage />} />
        </Routes>
      </main>
    </div>
  )
}
