import { useMemo, useState } from 'react'
import { apiClient } from '../../../services/apiClient'
import { getLocalizedApiError } from '../../../services/apiErrors'
import { useLanguage } from '../../../context/LanguageContext'
import { useSession } from '../../../context/SessionContext'
import { useFields } from '../../../context/FieldContext'
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
  const { fieldId: sessionFieldId } = useSession()
  const { fields, loading: fieldsLoading } = useFields()
  const { crops, loading: cropsLoading } = useCrops()

  const [prediction, setPrediction] = useState<PredictResponse | null>(null)
  const [loading, setLoading] = useState(false)

  const defaultCrop = useMemo(() => getDefaultCrop(crops), [crops])
  const year = getCurrentYear()

  // Form state
  const [farmerName, setFarmerName] = useState(() => getStoredName())
  const [phone, setPhone] = useState(() => getStoredPhone())
  const [loanAmount, setLoanAmount] = useState('')
  const [selectedFieldId, setSelectedFieldId] = useState(sessionFieldId || '')
  
  // Agricultural inputs for analysis
  const [cropType, setCropType] = useState<string>(defaultCrop?.crop_type || '')
  const [npkInput, setNpkInput] = useState<string>('120')
  const [irrigationRatio, setIrrigationRatio] = useState<string>('0.8')

  const [submitted, setSubmitted] = useState(false)
  const [loanResult, setLoanResult] = useState<'eligible' | 'rejected' | null>(null)

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    if (!selectedFieldId) {
      pushToast('Please select a field for the loan application.', 'error')
      return
    }
    if (!farmerName.trim() || !phone.trim() || !loanAmount.trim() || !cropType) {
      pushToast('Please fill all required fields.', 'error')
      return
    }
    const amount = Number(loanAmount)
    if (!Number.isFinite(amount) || amount <= 0) {
      pushToast('Enter a valid loan amount.', 'error')
      return
    }

    setLoading(true)
    try {
      const predicted = await apiClient.predict({
        field_id: selectedFieldId,
        crop_type: cropType,
        npk_input: Number(npkInput),
        irrigation_ratio: Number(irrigationRatio),
        year,
      }, true) // dry_run to not pollute DB
      
      setPrediction(predicted)
      
      const healthScore = predicted.health.final_health_score
      setSubmitted(true)
      
      if (healthScore >= HEALTH_BENCHMARK) {
        setLoanResult('eligible')
        pushToast(
          `✅ Loan application submitted! Your health score (${Math.round(healthScore)}) meets the benchmark.`,
          'success',
        )
      } else {
        setLoanResult('rejected')
        pushToast(
          `❌ Your health score (${Math.round(healthScore)}) is below the minimum benchmark (${HEALTH_BENCHMARK}).`,
          'error',
        )
      }
    } catch (error) {
      const message = getLocalizedApiError(error, content)
      pushToast(message, 'error')
    } finally {
      setLoading(false)
    }
  }

  if (!fieldsLoading && fields.length === 0) {
    return <p className="panel-empty">No fields registered yet. Register a field in My Farm to unlock loan eligibility.</p>
  }

  const healthScore = prediction?.health.final_health_score ?? 0
  const risk = getRiskLabel(prediction?.health.risk_level)

  return (
    <div style={{ maxWidth: '800px', margin: '0 auto', width: '100%' }}>
      {!submitted ? (
        <article className="panel-card" style={{ padding: '32px' }}>
          <div className="panel-card__head" style={{ justifyContent: 'center', marginBottom: '24px' }}>
            <h2 style={{ fontSize: '1.5rem', fontWeight: 600 }}>Loan Application Assessment</h2>
          </div>
          <p style={{ textAlign: 'center', marginBottom: '32px', color: 'var(--text-muted)' }}>
            Fill out your farm details for an instant, AI-driven loan eligibility analysis.
          </p>

          <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px' }}>
              <label className="panel-myfarm-field">
                Farmer Name
                <input type="text" value={farmerName} onChange={(e) => setFarmerName(e.target.value)} required />
              </label>
              <label className="panel-myfarm-field">
                Phone Number
                <input type="tel" value={phone} onChange={(e) => setPhone(e.target.value)} required />
              </label>
            </div>
            
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px' }}>
              <label className="panel-myfarm-field">
                Select Field
                <select 
                  value={selectedFieldId} 
                  onChange={(e) => setSelectedFieldId(e.target.value)}
                  disabled={fieldsLoading}
                  required
                >
                  <option value="">-- Choose a field --</option>
                  {fields.map(f => (
                    <option key={f.field_id} value={f.field_id}>{f.field_name} {f.area_hectares ? `(${f.area_hectares} ha)` : ''}</option>
                  ))}
                </select>
              </label>
              <label className="panel-myfarm-field">
                Loan Amount Required (₹)
                <input type="number" value={loanAmount} onChange={(e) => setLoanAmount(e.target.value)} placeholder="e.g. 50000" min="1" required />
              </label>
            </div>

            <div style={{ borderTop: '1px solid var(--border-light)', margin: '12px 0 0 0', paddingTop: '24px' }}>
              <h4 style={{ marginBottom: '20px', fontSize: '1rem', color: 'var(--text-main)' }}>Farm Analysis Inputs</h4>
              
              <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
                <label className="panel-myfarm-field">
                  Target Crop Type
                  <select
                    value={cropType}
                    onChange={(e) => setCropType(e.target.value)}
                    disabled={cropsLoading}
                    required
                  >
                    {cropsLoading && <option value="">Loading crops...</option>}
                    {crops.map((c) => (
                      <option key={c.crop_type} value={c.crop_type}>
                        {c.display_name}
                      </option>
                    ))}
                  </select>
                </label>

                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px' }}>
                  <label className="panel-myfarm-field">
                    Expected NPK Input (kg/ha)
                    <input 
                      type="number" 
                      value={npkInput} 
                      onChange={(e) => setNpkInput(e.target.value)} 
                      min="0" 
                      max="500"
                      required 
                    />
                  </label>
                  <label className="panel-myfarm-field">
                    Irrigation Coverage (0.0 - 1.0)
                    <input 
                      type="number" 
                      value={irrigationRatio} 
                      onChange={(e) => setIrrigationRatio(e.target.value)} 
                      min="0" 
                      max="1" 
                      step="0.1"
                      required 
                    />
                  </label>
                </div>
              </div>
            </div>

            <div style={{ marginTop: '24px' }}>
              <button 
                type="submit" 
                className="panel-mapbox__button" 
                disabled={loading} 
                style={{ 
                  width: '100%',
                  padding: '14px', 
                  fontSize: '1.05rem',
                  borderRadius: '12px',
                  fontWeight: 600,
                  display: 'flex',
                  justifyContent: 'center'
                }}
              >
                {loading ? 'Analyzing Application...' : 'Analyze & Submit Application'}
              </button>
            </div>
          </form>
        </article>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
          <article className="panel-card" style={{ padding: '32px' }}>
            <div className="panel-card__head" style={{ justifyContent: 'center', marginBottom: '24px' }}>
              <h2 style={{ fontSize: '1.5rem', fontWeight: 600 }}>Eligibility Result</h2>
            </div>
            
            <div className={`panel-loan-result panel-loan-result--${loanResult}`} style={{ marginTop: '16px', padding: '24px', textAlign: 'center' }}>
              <h4 style={{ fontSize: '1.3rem', marginBottom: '12px' }}>
                {loanResult === 'eligible' ? '✅ Loan Approved for Processing' : '❌ Application Rejected'}
              </h4>
              <p style={{ fontSize: '1.05rem', color: 'var(--text-main)', opacity: 0.9 }}>
                {loanResult === 'eligible'
                  ? `Your loan of ₹${Number(loanAmount).toLocaleString()} is being processed. Your farm scored well above the minimum criteria.`
                  : `Health Score is below the benchmark of ${HEALTH_BENCHMARK}%. Please improve your farm conditions and try again.`}
              </p>
              
              <div style={{ display: 'flex', justifyContent: 'space-around', alignItems: 'center', marginTop: '32px', padding: '24px', background: 'var(--bg-card)', borderRadius: '12px' }}>
                <div style={{ textAlign: 'center' }}>
                  <span style={{ fontSize: '0.9rem', color: 'var(--text-muted)', display: 'block', marginBottom: '4px' }}>Farm Health Score</span>
                  <strong style={{ fontSize: '2rem', color: 'var(--text-main)' }}>{formatScore(healthScore)}</strong>
                  <div style={{ fontSize: '0.8rem', color: `var(--risk-${risk.tone})`, marginTop: '4px' }}>{risk.label} Risk</div>
                </div>
                <div style={{ textAlign: 'center' }}>
                  <span style={{ fontSize: '0.9rem', color: 'var(--text-muted)', display: 'block', marginBottom: '4px' }}>Predicted Yield</span>
                  <strong style={{ fontSize: '1.5rem', color: 'var(--text-main)' }}>{Math.round(prediction?.predicted_yield || 0)} kg/ha</strong>
                </div>
                <div style={{ textAlign: 'center' }}>
                  <span style={{ fontSize: '0.9rem', color: 'var(--text-muted)', display: 'block', marginBottom: '4px' }}>Loan Amount</span>
                  <strong style={{ fontSize: '1.5rem', color: 'var(--text-main)' }}>₹{Number(loanAmount).toLocaleString()}</strong>
                </div>
              </div>
            </div>
          </article>

          <article className="panel-card" style={{ padding: '32px' }}>
            <div className="panel-card__head">
              <h3>Score Factors</h3>
              <span className="panel-card__metric">Assessment</span>
            </div>
            <p>Key factors used in the automated credit assessment by our AI model.</p>
            <ul className="panel-list" style={{ marginTop: '20px', gap: '12px', display: 'flex', flexDirection: 'column' }}>
              <li style={{ padding: '12px', background: 'var(--bg-body)', borderRadius: '8px' }}>
                <strong>Yield Score: {formatScore(prediction?.health.yield_score)}</strong> — <em>Based on estimated output</em>
              </li>
              <li style={{ padding: '12px', background: 'var(--bg-body)', borderRadius: '8px' }}>
                <strong>Soil Score: {formatScore(prediction?.health.soil_score)}</strong> — <em>Based on district soil health</em>
              </li>
              <li style={{ padding: '12px', background: 'var(--bg-body)', borderRadius: '8px' }}>
                <strong>Water Score: {formatScore(prediction?.health.water_score)}</strong> — <em>Based on rainfall & irrigation</em>
              </li>
              <li style={{ padding: '12px', background: 'var(--bg-body)', borderRadius: '8px' }}>
                <strong>Climate Score: {formatScore(prediction?.health.climate_score)}</strong> — <em>Based on historical weather</em>
              </li>
              <li style={{ padding: '12px', background: 'var(--bg-body)', borderRadius: '8px' }}>
                <strong>NDVI Score: {formatScore(prediction?.health.ndvi_score)}</strong> — <em>Based on satellite vegetation index</em>
              </li>
            </ul>

            <div style={{ display: 'flex', justifyContent: 'center', marginTop: '32px' }}>
              <button 
                type="button" 
                className="panel-mapbox__button panel-mapbox__button--secondary" 
                onClick={() => { setSubmitted(false); setPrediction(null); setLoanResult(null) }}
                style={{ padding: '10px 32px', borderRadius: '24px' }}
              >
                Start New Application
              </button>
            </div>
          </article>
        </div>
      )}
    </div>
  )
}

export default LoanEligibilityPanel
