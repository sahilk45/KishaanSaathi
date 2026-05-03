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
  const { content, panel } = useLanguage()
  const p = panel.panel.loanEligibility
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
    return <p className="panel-empty">{p.noFieldsAvailable}</p>
  }

  const healthScore = prediction?.health.final_health_score ?? 0
  const risk = getRiskLabel(prediction?.health.risk_level)

  return (
    <div style={{ maxWidth: '800px', margin: '0 auto', width: '100%' }}>
      {!submitted ? (
        <article className="panel-card" style={{ padding: '32px' }}>
          <div className="panel-card__head" style={{ justifyContent: 'center', marginBottom: '24px' }}>
            <h2 style={{ fontSize: '1.5rem', fontWeight: 600 }}>{p.formTitle}</h2>
          </div>
          <p style={{ textAlign: 'center', marginBottom: '32px', color: 'var(--text-muted)' }}>
            Fill out your farm details for an instant, AI-driven loan eligibility analysis.
          </p>

          <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px' }}>
              <label className="panel-myfarm-field">
                {p.farmerName}
                <input type="text" value={farmerName} onChange={(e) => setFarmerName(e.target.value)} required />
              </label>
              <label className="panel-myfarm-field">
                {p.farmerPhone}
                <input type="tel" value={phone} onChange={(e) => setPhone(e.target.value)} required />
              </label>
            </div>
            
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px' }}>
              <label className="panel-myfarm-field">
                {p.selectField}
                <select 
                  value={selectedFieldId} 
                  onChange={(e) => setSelectedFieldId(e.target.value)}
                  disabled={fieldsLoading}
                  required
                >
                  <option value="">-- {p.selectFieldPlaceholder} --</option>
                  {fields.map(f => (
                    <option key={f.field_id} value={f.field_id}>{f.field_name} {f.area_hectares ? `(${f.area_hectares} ha)` : ''}</option>
                  ))}
                </select>
              </label>
              <label className="panel-myfarm-field">
                {p.loanAmount}
                <input type="number" value={loanAmount} onChange={(e) => setLoanAmount(e.target.value)} placeholder="e.g. 50000" min="1" required />
              </label>
            </div>

            <div style={{ borderTop: '1px solid var(--border-light)', margin: '12px 0 0 0', paddingTop: '24px' }}>
              <h4 style={{ marginBottom: '20px', fontSize: '1rem', color: 'var(--text-main)' }}>Farm Analysis Inputs</h4>
              
              <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
                <label className="panel-myfarm-field">
                  {p.cropType}
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
                    {p.npkInput}
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
                    {p.irrigationRatio}
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
                {loading ? p.analyzing : p.submitApplication}
              </button>
            </div>
          </form>
        </article>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
          <article className="panel-card" style={{ padding: '32px' }}>
            <div className="panel-card__head" style={{ justifyContent: 'center', marginBottom: '24px' }}>
              <h2 style={{ fontSize: '1.5rem', fontWeight: 600 }}>{p.eligibilityResult}</h2>
            </div>
            
            <div className={`panel-loan-result panel-loan-result--${loanResult}`} style={{ marginTop: '16px', padding: '24px', textAlign: 'center' }}>
              <h4 style={{ fontSize: '1.3rem', marginBottom: '12px' }}>
                {loanResult === 'eligible' ? p.loanApproved : p.loanRejected}
              </h4>
              <p style={{ fontSize: '1.05rem', color: 'var(--text-main)', opacity: 0.9 }}>
                {loanResult === 'eligible'
                  ? p.loanApprovedDesc?.replace('{amount}', Number(loanAmount).toLocaleString())
                  : p.loanRejectedDesc?.replace('{amount}', Number(loanAmount).toLocaleString())}
              </p>
              
              <div style={{ display: 'flex', justifyContent: 'space-around', alignItems: 'center', marginTop: '32px', padding: '24px', background: 'var(--bg-card)', borderRadius: '12px' }}>
                <div style={{ textAlign: 'center' }}>
                  <span style={{ fontSize: '0.9rem', color: 'var(--text-muted)', display: 'block', marginBottom: '4px' }}>{p.healthScore}</span>
                  <strong style={{ fontSize: '2rem', color: 'var(--text-main)' }}>{formatScore(healthScore)}</strong>
                  <div style={{ fontSize: '0.8rem', color: `var(--risk-${risk.tone})`, marginTop: '4px' }}>{risk.label}</div>

                </div>
                <div style={{ textAlign: 'center' }}>
                  <span style={{ fontSize: '0.9rem', color: 'var(--text-muted)', display: 'block', marginBottom: '4px' }}>{p.predictedYield}</span>
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
              <h3>{p.scoreFactors}</h3>
              <span className="panel-card__metric">{p.assessment}</span>
            </div>
            <p>{p.assessmentDesc}</p>
            <ul className="panel-list" style={{ marginTop: '20px', gap: '12px', display: 'flex', flexDirection: 'column' }}>
              <li style={{ padding: '12px', background: 'var(--bg-body)', borderRadius: '8px' }}>
                <strong>{p.yieldScoreDesc?.replace('{score}', formatScore(prediction?.health.yield_score))}</strong>
              </li>
              <li style={{ padding: '12px', background: 'var(--bg-body)', borderRadius: '8px' }}>
                <strong>{p.soilScoreDesc?.replace('{score}', formatScore(prediction?.health.soil_score))}</strong>
              </li>
              <li style={{ padding: '12px', background: 'var(--bg-body)', borderRadius: '8px' }}>
                <strong>{p.waterScoreDesc?.replace('{score}', formatScore(prediction?.health.water_score))}</strong>
              </li>
              <li style={{ padding: '12px', background: 'var(--bg-body)', borderRadius: '8px' }}>
                <strong>{p.climateScoreDesc?.replace('{score}', formatScore(prediction?.health.climate_score))}</strong>
              </li>
              <li style={{ padding: '12px', background: 'var(--bg-body)', borderRadius: '8px' }}>
                <strong>{p.ndviScoreDesc?.replace('{score}', formatScore(prediction?.health.ndvi_score))}</strong>
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
