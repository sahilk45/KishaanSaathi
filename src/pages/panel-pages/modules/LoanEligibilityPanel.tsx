import { useEffect, useMemo, useState } from 'react'
import { apiClient } from '../../../services/apiClient'
import { getLocalizedApiError } from '../../../services/apiErrors'
import { useLanguage } from '../../../context/LanguageContext'
import { useSession } from '../../../context/SessionContext'
import { useToast } from '../../../context/ToastContext'
import { useCrops } from '../../../context/CropContext'
import type { PredictResponse } from '../../../types/api'
import { formatScore, getCurrentYear, getDefaultCrop, getRiskLabel } from './panelUtils'

const DEFAULT_NPK = 120
const DEFAULT_IRR = 0.8

const LoanEligibilityPanel = () => {
  const { content } = useLanguage()
  const { pushToast } = useToast()
  const { fieldId } = useSession()
  const { crops, loading: cropsLoading } = useCrops()
  const [prediction, setPrediction] = useState<PredictResponse | null>(null)
  const [loading, setLoading] = useState(false)

  const defaultCrop = useMemo(() => getDefaultCrop(crops), [crops])
  const year = getCurrentYear()

  useEffect(() => {
    if (!fieldId || cropsLoading || !defaultCrop) return
    let active = true
    const loadEligibility = async () => {
      setLoading(true)
      try {
        const payload = await apiClient.predict({
          field_id: fieldId,
          crop_type: defaultCrop.crop_type,
          npk_input: DEFAULT_NPK,
          year,
          irrigation_ratio: DEFAULT_IRR,
        })
        if (!active) return
        setPrediction(payload)
      } catch (error) {
        const message = getLocalizedApiError(error, content)
        if (!active) return
        pushToast(message, 'error')
      } finally {
        if (active) setLoading(false)
      }
    }

    loadEligibility()

    return () => {
      active = false
    }
  }, [content, cropsLoading, defaultCrop, fieldId, pushToast, year])

  if (!fieldId) {
    return <p className="panel-empty">Field not registered yet. Register your field in My Farm to unlock loan eligibility.</p>
  }

  const risk = getRiskLabel(prediction?.health.risk_level)

  return (
    <div className="panel-cards">
      <article className="panel-card">
        <div className="panel-card__head">
          <h3>Eligibility Score</h3>
          <span className={`panel-card__metric panel-risk panel-risk--${risk.tone}`}>{risk.label}</span>
        </div>
        <p>Loan eligibility based on crop health and predicted yield.</p>
        {loading ? (
          <div className="panel-skeleton" />
        ) : (
          <div className="panel-metric">
            <strong>{formatScore(prediction?.health.final_health_score)}</strong>
            <span>Decision: {prediction?.health.loan_decision ?? 'N/A'}</span>
          </div>
        )}
      </article>

      <article className="panel-card">
        <div className="panel-card__head">
          <h3>Bank-style Report</h3>
          <span className="panel-card__metric">Summary</span>
        </div>
        <p>Key factors used in the automated credit assessment.</p>
        {loading ? (
          <div className="panel-skeleton" />
        ) : (
          <ul className="panel-list">
            <li>Yield score: {formatScore(prediction?.health.yield_score)}</li>
            <li>Soil score: {formatScore(prediction?.health.soil_score)}</li>
            <li>Water score: {formatScore(prediction?.health.water_score)}</li>
            <li>Climate score: {formatScore(prediction?.health.climate_score)}</li>
          </ul>
        )}
      </article>
    </div>
  )
}

export default LoanEligibilityPanel
