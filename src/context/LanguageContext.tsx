import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import {
  languageLabels,
  languageOrder,
  locales,
  type LanguageCode,
  type LocaleContent,
} from '../locales'
import panelEn from '../locales/panel_en.json'
import panelHi from '../locales/panel_hi.json'
import panelPa from '../locales/panel_pa.json'

export type PanelContent = typeof panelEn

const panelLocales: Record<LanguageCode, PanelContent> = {
  EN: panelEn,
  HI: panelHi as PanelContent,
  PA: panelPa as PanelContent,
}

type LanguageContextValue = {
  language: LanguageCode
  languageLabel: string
  content: LocaleContent
  panel: PanelContent
  setLanguage: (lang: LanguageCode) => void
  cycleLanguage: () => void
}

const LanguageContext = createContext<LanguageContextValue | undefined>(undefined)

const LANG_STORAGE_KEY = 'ks_language'

const getSavedLanguage = (): LanguageCode => {
  try {
    const saved = localStorage.getItem(LANG_STORAGE_KEY)
    if (saved && languageOrder.includes(saved as LanguageCode)) {
      return saved as LanguageCode
    }
  } catch { /* ignore */ }
  return 'EN'
}

export const LanguageProvider = ({ children }: { children: ReactNode }) => {
  const [language, setLanguageState] = useState<LanguageCode>(getSavedLanguage)

  const setLanguage = useCallback((lang: LanguageCode) => {
    setLanguageState(lang)
    try { localStorage.setItem(LANG_STORAGE_KEY, lang) } catch { /* ignore */ }
  }, [])

  const cycleLanguage = useCallback(() => {
    setLanguage(languageOrder[(languageOrder.indexOf(language) + 1) % languageOrder.length])
  }, [language, setLanguage])

  const content = locales[language]
  const panel = panelLocales[language]

  useEffect(() => {
    document.title = content.meta.title
  }, [content])

  useEffect(() => {
    const root = document.documentElement
    root.classList.toggle('language-large-text', language === 'HI' || language === 'PA')
    return () => root.classList.remove('language-large-text')
  }, [language])

  const value = useMemo(
    () => ({ language, languageLabel: languageLabels[language], content, panel, setLanguage, cycleLanguage }),
    [language, content, panel, setLanguage, cycleLanguage],
  )

  return <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>
}

// eslint-disable-next-line react-refresh/only-export-components
export const useLanguage = () => {
  const context = useContext(LanguageContext)
  if (!context) throw new Error('useLanguage must be used within a LanguageProvider')
  return context
}
