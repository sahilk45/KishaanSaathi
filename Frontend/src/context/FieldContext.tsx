import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { apiClient } from '../services/apiClient'
import { useSession } from './SessionContext'
import type { FarmerFieldItem } from '../types/api'

type FieldContextValue = {
  fields: FarmerFieldItem[]
  selectedField: FarmerFieldItem | null
  loading: boolean
  selectField: (fieldId: string) => void
  refreshFields: () => void
}

const FieldContext = createContext<FieldContextValue | undefined>(undefined)

export const FieldProvider = ({ children }: { children: ReactNode }) => {
  const { farmerId, fieldId, setFieldId } = useSession()
  const [fields, setFields] = useState<FarmerFieldItem[]>([])
  const [loading, setLoading] = useState(false)

  const loadFields = useCallback(async () => {
    if (!farmerId) {
      setFields([])
      return
    }
    setLoading(true)
    try {
      const payload = await apiClient.getFarmerFields(farmerId)
      setFields(payload.fields ?? [])
      // Auto-select first field if none selected
      if (!fieldId && payload.fields.length > 0) {
        setFieldId(payload.fields[0].field_id)
      }
    } catch {
      setFields([])
    } finally {
      setLoading(false)
    }
  }, [farmerId, fieldId, setFieldId])

  useEffect(() => {
    loadFields()
  }, [loadFields])

  const selectedField = useMemo(
    () => fields.find((f) => f.field_id === fieldId) ?? null,
    [fields, fieldId],
  )

  const selectField = useCallback(
    (id: string) => {
      setFieldId(id)
    },
    [setFieldId],
  )

  const value = useMemo(
    () => ({ fields, selectedField, loading, selectField, refreshFields: loadFields }),
    [fields, selectedField, loading, selectField, loadFields],
  )

  return <FieldContext.Provider value={value}>{children}</FieldContext.Provider>
}

// eslint-disable-next-line react-refresh/only-export-components
export const useFields = () => {
  const context = useContext(FieldContext)
  if (!context) {
    throw new Error('useFields must be used within a FieldProvider')
  }
  return context
}
