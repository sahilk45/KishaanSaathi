import { useEffect, useMemo, useState } from 'react'
import { apiClient } from '../../../services/apiClient'
import { getLocalizedApiError } from '../../../services/apiErrors'
import { useLanguage } from '../../../context/LanguageContext'
import { useSession } from '../../../context/SessionContext'
import { useToast } from '../../../context/ToastContext'
import { useCrops } from '../../../context/CropContext'
import type { PredictResponse } from '../../../types/api'
import { formatScore, getCurrentYear, getDefaultCrop, getRiskLabel } from './panelUtils'

const HEALTH_BENCHMARK = 60
const GOOGLE_USER_KEY = 'ks_google_user'
const FARMER_PROFILE_KEY = 'ks_farmer_profile'

const getStoredName = (): string => {
  if (typeof window === 'undefined') return ''
  try {
    const profile = window.localStorage.getItem(FARMER_PROFILE_KEY)
    if (profile) {
      const parsed = JSON.parse(profile)
      if (parsed.name) return parsed.name
    }
    const google = window.localStorage.getItem(GOOGLE_USER_KEY)
    if (google) {
      const parsed = JSON.parse(google)
      if (parsed.name) return parsed.name
    }
  } catch { /* ignore */ }
  return ''
}

const getStoredPhone = (): string => {
  if (typeof window === 'undefined') return ''
  try {
    const profile = window.localStorage.getItem(FARMER_PROFILE_KEY)
    if (profile) {
      const parsed = JSON.parse(profile)
      if (parsed.phone) return parsed.phone
    }
  } catch { /* ignore */ }
  return ''
}

const LoanEligibilityPanel = () => {
  const { content } = useLanguage()
  const { pushToast } = useToast()
  const { fieldId } = useSession()
  const { crops, loading: cropsLoading } = useCrops()
  const [prediction, setPrediction] = useState<PredictResponse | null>(null)
  const [loading, setLoading] = useState(false)

  // Form state
  const [farmerName, setFarmerName] = useState(() => getStoredName())
  const [phone, setPhone] = useState(() => getStoredPhone())
  const [loanAmount, setLoanAmount] = useState('')
  const [submitted, setSubmitted] = useState(false)
  const [loanResult, setLoanResult] = useState<'eligible' | 'rejected' | null>(null)

  const defaultCrop = useMemo(() => getDefaultCrop(crops), [crops])
  const year = getCurrentYear()

  // Auto-fetch latest prediction for health score
  useEffect(() => {
    if (!fieldId) return
    let active = true
    const loadPrediction = async () => {
      setLoading(true)
      try {
        const histPayload = await apiClient.getFieldHistory(fieldId)
        if (!active) return
        if (histPayload.history.length > 0) {
          setPrediction(histPayload.history[0])
        } else if (defaultCrop && !cropsLoading) {
          const predicted = await apiClient.predict({
            field_id: fieldId,
            crop_type: defaultCrop.crop_type,
            npk_input: 120,
            year,
            irrigation_ratio: 0.8,
          }, true) // dry_run for auto-fetch
          if (!active) return
          setPrediction(predicted)
        }
      } catch (error) {
        const message = getLocalizedApiError(error, content)
        if (!active) return
        pushToast(message, 'error')
      } finally {
        if (active) setLoading(false)
      }
    }
    loadPrediction()
    return () => { active = false }
  }, [content, cropsLoading, defaultCrop, fieldId, pushToast, year])

  const healthScore = prediction?.health.final_health_score ?? 0
  const risk = getRiskLabel(prediction?.health.risk_level)

  const handleSubmit = (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    if (!farmerName.trim() || !phone.trim() || !loanAmount.trim()) {
      pushToast('Please fill all required fields.', 'error')
      return
    }
    const amount = Number(loanAmount)
    if (!Number.isFinite(amount) || amount <= 0) {
      pushToast('Enter a valid loan amount.', 'error')
      return
    }

    setSubmitted(true)
    if (healthScore >= HEALTH_BENCHMARK) {
      setLoanResult('eligible')
      pushToast(
        `✅ Loan application submitted! Your health score (${Math.round(healthScore)}) meets the benchmark (${HEALTH_BENCHMARK}). Loan of ₹${amount.toLocaleString()} is under process.`,
        'success',
      )
    } else {
      setLoanResult('rejected')
      pushToast(
        `❌ Your health score (${Math.round(healthScore)}) is below the minimum benchmark (${HEALTH_BENCHMARK}). Loan cannot be processed at this time.`,
        'error',
      )
    }
  }

  if (!fieldId) {
    return <p className="panel-empty">Field not registered yet. Register your field in My Farm to unlock loan eligibility.</p>
  }

  return (
    <div className="panel-cards">
      {/* ── Eligibility overview ──────────────────────── */}
      <article className="panel-card">
        <div className="panel-card__head">
          <h3>Eligibility Score</h3>
          <span className={`panel-card__metric panel-risk panel-risk--${risk.tone}`}>{risk.label}</span>
        </div>
        <p>Loan eligibility based on crop health and predicted yield. Minimum benchmark: <strong>{HEALTH_BENCHMARK}%</strong></p>
        {loading ? (
          <div className="panel-skeleton" />
        ) : (
          <div className="panel-metric">
            <strong>{formatScore(healthScore)}</strong>
            <span>
              {healthScore >= HEALTH_BENCHMARK
                ? '✅ Eligible for loan'
                : '❌ Below benchmark — improve crop health'}
            </span>
          </div>
        )}
      </article>

      {/* ── Application form ─────────────────────────── */}
      <article className="panel-card">
        <div className="panel-card__head">
          <h3>Loan Application</h3>
          <span className="panel-card__metric">Form</span>
        </div>
        <p>Submit your loan application. Fields are auto-filled from your profile.</p>

        {submitted && loanResult ? (
          <div className={`panel-loan-result panel-loan-result--${loanResult}`}>
            <h4>{loanResult === 'eligible' ? '✅ Loan Under Process' : '❌ Application Rejected'}</h4>
            <p>
              {loanResult === 'eligible'
                ? `Your loan of ₹${Number(loanAmount).toLocaleString()} is being processed. Health Score: ${Math.round(healthScore)}%.`
                : `Health Score ${Math.round(healthScore)}% is below the benchmark of ${HEALTH_BENCHMARK}%. Please improve your farm conditions and try again.`}
            </p>
            <button type="button" className="panel-mapbox__button" onClick={() => { setSubmitted(false); setLoanResult(null) }}>
              Submit New Application
            </button>
          </div>
        ) : (
          <form className="panel-simulator" onSubmit={handleSubmit}>
            <label className="panel-myfarm-field">
              Farmer Name (auto-filled)
              <input type="text" value={farmerName} onChange={(e) => setFarmerName(e.target.value)} required />
            </label>
            <label className="panel-myfarm-field">
              Phone Number (auto-filled)
              <input type="tel" value={phone} onChange={(e) => setPhone(e.target.value)} required />
            </label>
            <label className="panel-myfarm-field">
              Health Score
              <input type="text" value={loading ? 'Loading...' : formatScore(healthScore)} readOnly className="panel-input--readonly" />
            </label>
            <label className="panel-myfarm-field">
              Loan Amount (₹)
              <input type="number" value={loanAmount} onChange={(e) => setLoanAmount(e.target.value)} placeholder="50000" min="1" required />
            </label>
            <button type="submit" className="panel-mapbox__button" disabled={loading}>
              Submit Loan Application
            </button>
          </form>
        )}
      </article>

      {/* ── Score Breakdown ───────────────────────────── */}
      <article className="panel-card">
        <div className="panel-card__head">
          <h3>Score Factors</h3>
          <span className="panel-card__metric">Assessment</span>
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
            <li>NDVI score: {formatScore(prediction?.health.ndvi_score)}</li>
          </ul>
        )}
      </article>
    </div>
  )
}

export default LoanEligibilityPanel
