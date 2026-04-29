import type { CropItem, PredictResponse } from '../../../types/api'

export const getCurrentYear = () => new Date().getFullYear()

export const getDefaultCrop = (crops: CropItem[]) => crops[0]

export const formatScore = (value?: number | null) => {
  if (value === null || value === undefined || Number.isNaN(value)) return 'N/A'
  return `${Math.round(value)}%`
}

export const formatNumber = (value?: number | null, digits = 2) => {
  if (value === null || value === undefined || Number.isNaN(value)) return 'N/A'
  return value.toFixed(digits)
}

export const latestPrediction = (history: PredictResponse[]) => {
  if (!history.length) return null
  return history[0]
}

export const getRiskLabel = (riskLevel?: string) => {
  const normalized = (riskLevel || '').toUpperCase()
  if (normalized === 'LOW') return { label: 'Low Risk', tone: 'low' }
  if (normalized === 'MEDIUM') return { label: 'Moderate Risk', tone: 'medium' }
  if (normalized === 'HIGH') return { label: 'High Risk', tone: 'high' }
  return { label: riskLevel || 'Unknown', tone: 'neutral' }
}
