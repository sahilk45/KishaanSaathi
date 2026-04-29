import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { apiClient } from '../services/apiClient'
import { getLocalizedApiError } from '../services/apiErrors'
import { useLanguage } from './LanguageContext'
import { useToast } from './ToastContext'
import type { CropItem } from '../types/api'

type CropContextValue = {
  crops: CropItem[]
  loading: boolean
  error: string
}

const CropContext = createContext<CropContextValue | undefined>(undefined)

export const CropProvider = ({ children }: { children: ReactNode }) => {
  const { content } = useLanguage()
  const { pushToast } = useToast()
  const [crops, setCrops] = useState<CropItem[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  useEffect(() => {
    let isActive = true
    const loadCrops = async () => {
      setLoading(true)
      setError('')
      try {
        const payload = await apiClient.getCrops()
        if (!isActive) return
        setCrops(payload.crops ?? [])
      } catch (err) {
        const message = getLocalizedApiError(err, content)
        if (!isActive) return
        setError(message)
        pushToast(message, 'error')
      } finally {
        if (isActive) setLoading(false)
      }
    }

    loadCrops()

    return () => {
      isActive = false
    }
  }, [content, pushToast])

  const value = useMemo(() => ({ crops, loading, error }), [crops, loading, error])

  return <CropContext.Provider value={value}>{children}</CropContext.Provider>
}

// eslint-disable-next-line react-refresh/only-export-components
export const useCrops = () => {
  const context = useContext(CropContext)
  if (!context) {
    throw new Error('useCrops must be used within a CropProvider')
  }
  return context
}
