import type { LocaleContent } from '../locales'
import type { ApiErrorDetail } from './apiClient'

const normalize = (value: string) => value.toLowerCase()

export const getLocalizedApiError = (error: unknown, content: LocaleContent) => {
  if (error && typeof error === 'object' && 'detail' in error) {
    const detail = String((error as ApiErrorDetail).detail ?? '')
    const normalized = normalize(detail)

    if (normalized.includes('not found')) return content.errors.notFound
    if (normalized.includes('validation') || normalized.includes('invalid')) return content.errors.validation
    if (normalized.includes('already registered') || normalized.includes('conflict')) return content.errors.conflict
    if (normalized.includes('unauthorized') || normalized.includes('forbidden')) return content.errors.unauthorized
    if (normalized.includes('chatbot error')) return content.errors.chatbot
    if (normalized.includes('crop_type')) return content.errors.cropType
    if (normalized.includes('field_id')) return content.errors.fieldId

    return detail || content.errors.unknown
  }

  return content.errors.network
}
