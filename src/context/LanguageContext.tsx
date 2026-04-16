import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import {
  languageLabels,
  languageOrder,
  locales,
  type LanguageCode,
  type LocaleContent,
} from '../locales'

type LanguageContextValue = {
  language: LanguageCode
  languageLabel: string
  content: LocaleContent
  cycleLanguage: () => void
}

const LanguageContext = createContext<LanguageContextValue | undefined>(undefined)

const getNextLanguage = (current: LanguageCode): LanguageCode => {
  const currentIndex = languageOrder.indexOf(current)
  return languageOrder[(currentIndex + 1) % languageOrder.length]
}

export const LanguageProvider = ({ children }: { children: ReactNode }) => {
  const [language, setLanguage] = useState<LanguageCode>('EN')

  const cycleLanguage = () => {
    setLanguage((currentLanguage) => getNextLanguage(currentLanguage))
  }

  const content = locales[language]

  useEffect(() => {
    document.title = content.meta.title
  }, [content])

  useEffect(() => {
    const rootElement = document.documentElement
    const shouldIncreaseTextSize = language === 'HI' || language === 'PA'

    rootElement.classList.toggle('language-large-text', shouldIncreaseTextSize)

    return () => {
      rootElement.classList.remove('language-large-text')
    }
  }, [language])

  const value = useMemo(
    () => ({
      language,
      languageLabel: languageLabels[language],
      content,
      cycleLanguage,
    }),
    [language, content],
  )

  return <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>
}

// eslint-disable-next-line react-refresh/only-export-components
export const useLanguage = () => {
  const context = useContext(LanguageContext)

  if (!context) {
    throw new Error('useLanguage must be used within a LanguageProvider')
  }

  return context
}
