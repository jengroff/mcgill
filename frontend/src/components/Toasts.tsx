import { X } from 'lucide-react'
import { useAppStore } from '../store/appStore'

export default function Toasts() {
  const toasts = useAppStore((s) => s.toasts)
  const dismiss = useAppStore((s) => s.dismissToast)

  if (!toasts.length) return null

  return (
    <div className="fixed bottom-4 right-4 z-[100] space-y-2 max-w-sm">
      {toasts.map((t) => (
        <div
          key={t.id}
          className="flex items-start gap-2 rounded-lg px-4 py-3 text-xs shadow-lg animate-in fade-in slide-in-from-bottom-2"
          style={{
            background: t.type === 'error' ? '#991b1b' : 'var(--bg-elevated)',
            color: t.type === 'error' ? '#fecaca' : 'var(--text-primary)',
            border: `1px solid ${t.type === 'error' ? '#dc2626' : 'var(--border)'}`,
          }}
        >
          <span className="flex-1">{t.message}</span>
          <div className="flex items-center gap-2 flex-shrink-0">
            {t.action && (
              <button
                onClick={() => { dismiss(t.id); t.action!.fn() }}
                className="cursor-pointer text-xs font-medium underline"
                style={{ background: 'none', border: 'none', color: 'inherit', padding: 0 }}
              >
                {t.action.label}
              </button>
            )}
            <button
              onClick={() => dismiss(t.id)}
              className="cursor-pointer"
              style={{ background: 'none', border: 'none', color: 'inherit', padding: 0 }}
            >
              <X size={12} />
            </button>
          </div>
        </div>
      ))}
    </div>
  )
}
