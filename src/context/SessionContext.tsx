import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react'

type SessionContextValue = {
  farmerId: string
  fieldId: string
  setFarmerId: (value: string) => void
  setFieldId: (value: string) => void
}

const SessionContext = createContext<SessionContextValue | undefined>(undefined)

const FARMER_ID_STORAGE_KEY = 'ks_farmer_id'
const LEGACY_FARMER_ID_STORAGE_KEY = 'ks_last_farmer_id'
const FIELD_ID_STORAGE_KEY = 'ks_field_id'

const getStorageValue = (key: string) => {
  if (typeof window === 'undefined') return ''
  return window.localStorage.getItem(key) ?? ''
}

const setStorageValue = (key: string, value: string) => {
  if (typeof window === 'undefined') return
  if (value) {
    window.localStorage.setItem(key, value)
  } else {
    window.localStorage.removeItem(key)
  }
}

export const SessionProvider = ({ children }: { children: ReactNode }) => {
  const [farmerId, setFarmerIdState] = useState(() => getStorageValue(FARMER_ID_STORAGE_KEY))
  const [fieldId, setFieldIdState] = useState(() => getStorageValue(FIELD_ID_STORAGE_KEY))

  const setFarmerId = useCallback((value: string) => {
    const normalized = value.trim()
    setFarmerIdState(normalized)
    setStorageValue(FARMER_ID_STORAGE_KEY, normalized)
    setStorageValue(LEGACY_FARMER_ID_STORAGE_KEY, normalized)
  }, [])

  const setFieldId = useCallback((value: string) => {
    const normalized = value.trim()
    setFieldIdState(normalized)
    setStorageValue(FIELD_ID_STORAGE_KEY, normalized)
  }, [])

  const value = useMemo(
    () => ({ farmerId, fieldId, setFarmerId, setFieldId }),
    [farmerId, fieldId, setFarmerId, setFieldId],
  )

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>
}

// eslint-disable-next-line react-refresh/only-export-components
export const useSession = () => {
  const context = useContext(SessionContext)
  if (!context) {
    throw new Error('useSession must be used within a SessionProvider')
  }
  return context
}
