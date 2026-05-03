import english from './ENGLISH.JSON'
import hindi from './HINDI.JSON'
import punjabi from './PUNJABI.JSON'

export type LanguageCode = 'EN' | 'HI' | 'PA'

export const languageOrder: LanguageCode[] = ['EN', 'HI', 'PA']

export const languageLabels: Record<LanguageCode, string> = {
  EN: 'EN',
  HI: 'हिं',
  PA: 'ਪੰ',
}

export const locales = {
  EN: english,
  HI: hindi,
  PA: punjabi,
} as const

export type LocaleContent = (typeof locales)['EN']
