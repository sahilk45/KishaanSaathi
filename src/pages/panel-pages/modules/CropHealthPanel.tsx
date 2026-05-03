import { useEffect, useMemo, useState } from 'react'
import { apiClient } from '../../../services/apiClient'
import { getLocalizedApiError } from '../../../services/apiErrors'
import { useLanguage } from '../../../context/LanguageContext'
import { useSession } from '../../../context/SessionContext'
import { useToast } from '../../../context/ToastContext'
import { useCrops } from '../../../context/CropContext'
import type { CropItem, PredictResponse } from '../../../types/api'
import { formatNumber, formatScore, getCurrentYear, getRiskLabel } from './panelUtils'

const LAST_CROP_INPUTS_KEY = 'ks_last_crop_inputs'

export const saveLastCropInputs = (cropType: string, npk: string, irrigation: string) => {
  try {
    localStorage.setItem(LAST_CROP_INPUTS_KEY, JSON.stringify({ cropType, npk, irrigation }))
  } catch { /* ignore */ }
}

export const loadLastCropInputs = (): { cropType: string; npk: string; irrigation: string } | null => {
  try {
    const raw = localStorage.getItem(LAST_CROP_INPUTS_KEY)
    if (raw) return JSON.parse(raw)
  } catch { /* ignore */ }
  return null
}

const KHARIF_KEYWORDS = ['RICE', 'PEARL MILLET', 'GROUNDNUT', 'SUGARCANE', 'MAIZE', 'COTTON', 'SOYABEAN', 'SESAMUM', 'KHARIF SORGHUM', 'FINGER MILLET']
const RABI_KEYWORDS = ['CHICKPEA', 'WHEAT', 'MUSTARD', 'LENTIL', 'BARLEY', 'LINSEED', 'SAFFLOWER', 'RABI SORGHUM', 'RAPESEED']

const isSeasonMatch = (cropType: string, season: 'kharif' | 'rabi' | 'all') => {
  if (season === 'all') return true
  const normalized = cropType.toUpperCase()
  const keywords = season === 'kharif' ? KHARIF_KEYWORDS : RABI_KEYWORDS
  return keywords.some((keyword) => normalized.includes(keyword))
}

const CropHealthPanel = () => {
  const { content, panel } = useLanguage()
  const p = panel.panel.cropHealth
  const { pushToast } = useToast()
  const { fieldId } = useSession()
  const { crops, loading: cropsLoading } = useCrops()

  const [season, setSeason] = useState<'all' | 'kharif' | 'rabi'>('all')
  const [selectedCrop, setSelectedCrop] = useState<string>('')
  const [npkInput, setNpkInput] = useState('120')
  const [irrigationRatio, setIrrigationRatio] = useState('0.8')
  const [year, setYear] = useState(`${getCurrentYear()}`)
  const [prediction, setPrediction] = useState<PredictResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [history, setHistory] = useState<PredictResponse[]>([])
  const [historyLoading, setHistoryLoading] = useState(false)

  const filteredCrops = useMemo(() => crops.filter((crop) => isSeasonMatch(crop.crop_type, season)), [crops, season])
  const cropOptions = filteredCrops.length ? filteredCrops : crops

  // Load existing history on mount
  useEffect(() => {
    if (!fieldId) return
    let active = true
    const loadHistory = async () => {
      setHistoryLoading(true)
      try {
        const payload = await apiClient.getFieldHistory(fieldId)
        if (!active) return
        setHistory(payload.history ?? [])
        if (payload.history.length > 0) {
          setPrediction(payload.history[0])
        }
      } catch {
        // No history yet — that's fine
      } finally {
        if (active) setHistoryLoading(false)
      }
    }
    loadHistory()
    return () => { active = false }
  }, [fieldId])

  const handlePredict = async () => {
    if (!fieldId) {
      pushToast(content.errors.fieldId || 'Register a field first.', 'error')
      return
    }
    const cropType = selectedCrop || cropOptions[0]?.crop_type
    if (!cropType) {
      pushToast(content.errors.cropType || 'Select a crop.', 'error')
      return
    }
    const npk = Number(npkInput)
    const irr = Number(irrigationRatio)
    const yr = Number(year)
    if (!Number.isFinite(npk) || !Number.isFinite(irr) || !Number.isFinite(yr)) {
      pushToast(content.errors.validation || 'Enter valid numbers.', 'error')
      return
    }

    setLoading(true)
    try {
      // persist = true (no dry_run) — this is the real crop prediction
      const payload = await apiClient.predict({
        field_id: fieldId,
        crop_type: cropType,
        npk_input: npk,
        year: yr,
        irrigation_ratio: irr,
      }, false)
      setPrediction(payload)
      // Save inputs for Loan Eligibility auto-fill
      saveLastCropInputs(cropType, npkInput, irrigationRatio)
      // Refresh history
      try {
        const histPayload = await apiClient.getFieldHistory(fieldId)
        setHistory(histPayload.history ?? [])
      } catch { /* ignore */ }
      pushToast('Crop prediction saved successfully!', 'success')
    } catch (error) {
      const message = getLocalizedApiError(error, content)
      pushToast(message, 'error')
    } finally {
      setLoading(false)
    }
  }

  if (!fieldId) {
    return <p className="panel-empty">{p.fieldNotRegistered}</p>
  }

  const risk = getRiskLabel(prediction?.health.risk_level)

  return (
    <div className="panel-cards panel-cards--stacked">
      {/* ── Input form ──────────────────────────────────── */}
      <article className="panel-card">
        <div className="panel-card__head">
          <h3>{p.formTitle}</h3>
          <span className="panel-card__metric">{p.formInputs}</span>
        </div>
        <p>{p.formDescription}</p>
        {cropsLoading ? (
          <div className="panel-skeleton" />
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '16px', marginTop: '12px' }}>
            {/* Season filter */}
            <div className="panel-toggle">
              <button type="button" className={season === 'kharif' ? 'active' : ''} onClick={() => setSeason('kharif')}>{p.kharif}</button>
              <button type="button" className={season === 'rabi' ? 'active' : ''} onClick={() => setSeason('rabi')}>{p.rabi}</button>
              <button type="button" className={season === 'all' ? 'active' : ''} onClick={() => setSeason('all')}>{p.all}</button>
            </div>

            {/* Crop selector — full width */}
            <label className="panel-myfarm-field">
              {p.cropType}
              <select value={selectedCrop} onChange={(e) => setSelectedCrop(e.target.value)}>
                <option value="">{p.cropTypePlaceholder}</option>
                {cropOptions.map((crop: CropItem) => (
                  <option key={crop.crop_type} value={crop.crop_type}>{crop.display_name}</option>
                ))}
              </select>
            </label>

            {/* NPK + Irrigation in a row */}
            <div className="panel-stack-row">
              <label className="panel-myfarm-field">
                {p.npkInput}
                <input type="number" value={npkInput} onChange={(e) => setNpkInput(e.target.value)} />
              </label>
              <label className="panel-myfarm-field">
                {p.irrigationRatio}
                <input type="number" step="0.01" value={irrigationRatio} onChange={(e) => setIrrigationRatio(e.target.value)} />
              </label>
            </div>

            {/* Year + Submit */}
            <div className="panel-stack-row">
              <label className="panel-myfarm-field">
                {p.year}
                <input type="number" value={year} onChange={(e) => setYear(e.target.value)} />
              </label>
              <div style={{ display: 'flex', alignItems: 'flex-end' }}>
                <button
                  type="button"
                  className="panel-mapbox__button"
                  onClick={handlePredict}
                  disabled={loading}
                  style={{ width: '100%', height: '42px' }}
                >
                  {loading ? p.predicting : p.predictAndSave}
                </button>
              </div>
            </div>
          </div>
        )}
      </article>

      {/* ── Health Score Results ─────────────────────────── */}
      <article className="panel-card">
        <div className="panel-card__head">
          <h3>{p.healthScore}</h3>
          <span className={`panel-card__metric panel-risk panel-risk--${risk.tone}`}>{risk.label}</span>
        </div>
        <p>{p.latestPrediction}</p>

        {loading || historyLoading ? (
          <div className="panel-skeleton" style={{ marginTop: 12 }} />
        ) : prediction ? (
          <div style={{ marginTop: 14 }}>
            {/* Big score + yield hero row */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: 8, marginBottom: 12 }}>
              <div className="panel-farmer-info-cell" style={{ gridColumn: '1 / -1', flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', padding: '14px 18px' }}>
                <div>
                  <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Overall Health</span>
                  <div style={{ fontSize: '2rem', fontWeight: 800, color: risk.tone === 'green' ? '#16a34a' : risk.tone === 'yellow' ? '#d97706' : '#dc2626', lineHeight: 1.1 }}>
                    {formatScore(prediction.health.final_health_score)}
                  </div>
                </div>
                <div style={{ textAlign: 'right' }}>
                  <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>{p.yield}</div>
                  <div style={{ fontWeight: 700, fontSize: '1rem' }}>{formatNumber(prediction.predicted_yield, 1)} kg/ha</div>
                  <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', marginTop: 4 }}>{p.benchmark}</div>
                  <div style={{ fontWeight: 600, fontSize: '0.88rem', color: 'var(--text-muted)' }}>{formatNumber(prediction.benchmark_yield, 1)} kg/ha</div>
                </div>
              </div>
            </div>

            {/* Sub-score tiles — 2 col grid with bar */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
              {([
                [p.yieldScore, prediction.health.yield_score],
                [p.soilScore, prediction.health.soil_score],
                [p.waterScore, prediction.health.water_score],
                [p.climateScore, prediction.health.climate_score],
                [p.ndviScore, prediction.health.ndvi_score],
              ] as [string, number][]).map(([label, score]) => {
                const pct = Math.round(score)
                const barColor = pct >= 70 ? '#16a34a' : pct >= 45 ? '#d97706' : '#dc2626'
                return (
                  <div key={label} className="panel-farmer-info-cell">
                    <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 6 }}>
                      <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>{label}</span>
                      <strong style={{ fontSize: '0.82rem', color: barColor }}>{pct}%</strong>
                    </div>
                    <div style={{ height: 5, background: '#e5e7eb', borderRadius: 99, overflow: 'hidden' }}>
                      <div style={{ width: `${pct}%`, height: '100%', background: barColor, borderRadius: 99, transition: 'width 0.5s ease' }} />
                    </div>
                  </div>
                )
              })}

              {/* Loan decision — full width */}
              <div className="panel-farmer-info-cell" style={{ gridColumn: '1 / -1', flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }}>
                <span style={{ fontSize: '0.78rem', color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.05em' }}>{p.loan}</span>
                <strong style={{
                  fontSize: '0.88rem',
                  color: prediction.health.loan_decision === 'ELIGIBLE' ? '#16a34a' : prediction.health.loan_decision === 'REVIEW' ? '#d97706' : '#dc2626',
                  background: prediction.health.loan_decision === 'ELIGIBLE' ? '#dcfce7' : prediction.health.loan_decision === 'REVIEW' ? '#fef9c3' : '#fee2e2',
                  padding: '4px 12px', borderRadius: 99,
                }}>
                  {prediction.health.loan_decision}
                </strong>
              </div>
            </div>
          </div>
        ) : (
          <p className="panel-empty">{p.runFirstPrediction}</p>
        )}
      </article>

      {/* ── History ─────────────────────────────────────── */}
      <article className="panel-card">
        <div className="panel-card__head">
          <h3>{p.predictionHistory}</h3>
          <span className="panel-card__metric">{history.length} {p.records}</span>
        </div>
        <p>{p.allSavedPredictions}</p>
        {historyLoading ? (
          <div className="panel-skeleton" />
        ) : history.length === 0 ? (
          <p className="panel-empty">{p.noPredictionsYet}</p>
        ) : (
          <ul className="panel-list">
            {history.slice(0, 8).map((item, i) => (
              <li key={`${item.crop_type}-${item.year}-${i}`}>
                {item.year} · {item.crop_type.replace(/\.?YIELD.*$/i, '').replace(/\./g, ' ').trim()} · Health {formatScore(item.health.final_health_score)} · {formatNumber(item.predicted_yield, 0)} kg/ha
              </li>
            ))}
          </ul>
        )}
      </article>
    </div>
  )
}

export default CropHealthPanel
