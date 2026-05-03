import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from 'react'

export type ToastVariant = 'info' | 'success' | 'error'

export type ToastItem = {
  id: string
  message: string
  variant: ToastVariant
}

type ToastContextValue = {
  toasts: ToastItem[]
  pushToast: (message: string, variant?: ToastVariant) => void
  removeToast: (id: string) => void
}

const ToastContext = createContext<ToastContextValue | undefined>(undefined)

const createToastId = () => `toast_${Date.now()}_${Math.random().toString(16).slice(2)}`

export const ToastProvider = ({ children }: { children: ReactNode }) => {
  const [toasts, setToasts] = useState<ToastItem[]>([])
  const timers = useRef<Record<string, number>>({})

  const removeToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((toast) => toast.id !== id))
    if (timers.current[id]) {
      window.clearTimeout(timers.current[id])
      delete timers.current[id]
    }
  }, [])

  const pushToast = useCallback(
    (message: string, variant: ToastVariant = 'info') => {
      const id = createToastId()
      const nextToast: ToastItem = { id, message, variant }
      setToasts((prev) => [...prev, nextToast])

      timers.current[id] = window.setTimeout(() => {
        removeToast(id)
      }, 4200)
    },
    [removeToast],
  )

  const value = useMemo(() => ({ toasts, pushToast, removeToast }), [toasts, pushToast, removeToast])

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="toast-stack" role="status" aria-live="polite" aria-atomic="true">
        {toasts.map((toast) => (
          <button
            key={toast.id}
            type="button"
            className={`toast toast--${toast.variant}`}
            onClick={() => removeToast(toast.id)}
          >
            {toast.message}
          </button>
        ))}
      </div>
    </ToastContext.Provider>
  )
}

// eslint-disable-next-line react-refresh/only-export-components
export const useToast = () => {
  const context = useContext(ToastContext)
  if (!context) {
    throw new Error('useToast must be used within a ToastProvider')
  }
  return context
}
