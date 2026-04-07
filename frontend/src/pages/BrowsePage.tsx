import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { BookOpen, ChevronRight } from 'lucide-react'
import { fetchFaculties } from '../api/client'
import { useAppStore } from '../store/appStore'
import SearchBar from '../components/SearchBar'

interface FacultyItem {
  name: string
  slug: string
  department_codes: string[]
  course_count: number
}

const FACULTY_ICONS: Record<string, string> = {
  'engineering': 'E',
  'science': 'S',
  'arts': 'A',
  'music': 'Mu',
  'agri-env-sci': 'Ag',
  'management': 'Mg',
}

const HIDDEN_FACULTIES = new Set([
  'education',
  'law',
  'nursing',
  'medicine',
  'environment',
  'dental',
])

export default function BrowsePage() {
  const user = useAppStore((s) => s.user)
  const addToast = useAppStore((s) => s.addToast)
  const [faculties, setFaculties] = useState<FacultyItem[]>([])
  const [loading, setLoading] = useState(true)

  function loadFaculties() {
    setLoading(true)
    fetchFaculties()
      .then(setFaculties)
      .catch(() => addToast('Failed to load faculties', 'error', { label: 'Retry', fn: loadFaculties }))
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    if (!user) return
    loadFaculties()
  }, [user])

  return (
    <div className="h-full overflow-y-auto p-6">
      <div className="max-w-4xl mx-auto">
        <div className="text-center mb-8">
          <h1 className="text-2xl font-bold mb-2" style={{ color: 'var(--text-primary)' }}>
            Welcome back{user ? `, ${user.name.split(' ')[0]}` : ''}
          </h1>
          <p className="text-sm" style={{ color: 'var(--text-muted)' }}>Explore faculties, departments, and courses</p>
          <div className="max-w-md mx-auto mt-4">
            <SearchBar />
          </div>
        </div>

        {loading ? (
          <div className="text-center py-8" style={{ color: 'var(--text-muted)' }}>Loading faculties...</div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {faculties.filter((f) => !HIDDEN_FACULTIES.has(f.slug)).map((f) => (
              <Link
                key={f.slug}
                to={`/faculty/${f.slug}`}
                className="rounded-lg p-4 transition-all no-underline hover:scale-[1.02]"
                style={{ background: 'var(--bg-surface)', border: '1px solid var(--border)' }}
              >
                <div className="flex items-center gap-3 mb-2">
                  <div className="w-10 h-10 rounded-lg flex items-center justify-center text-sm font-bold" style={{ background: 'var(--accent)', color: '#fff' }}>
                    {FACULTY_ICONS[f.slug] ?? f.name[0]}
                  </div>
                  <div className="flex-1 min-w-0">
                    <h3 className="text-sm font-semibold truncate" style={{ color: 'var(--text-primary)' }}>{f.name}</h3>
                    <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
                      {f.department_codes.length} departments
                    </p>
                  </div>
                  <ChevronRight size={16} style={{ color: 'var(--text-muted)' }} />
                </div>
                <div className="flex items-center gap-1 text-xs" style={{ color: 'var(--text-muted)' }}>
                  <BookOpen size={12} />
                  {f.course_count} courses
                </div>
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
