import { useEffect, useMemo, useState } from 'react'
import { apiClient } from '../../../services/apiClient'
import { getLocalizedApiError } from '../../../services/apiErrors'
import { useLanguage } from '../../../context/LanguageContext'
import { useSession } from '../../../context/SessionContext'
import { useToast } from '../../../context/ToastContext'
import { useCrops } from '../../../context/CropContext'
import type { CropItem, PredictResponse } from '../../../types/api'
import { formatNumber, formatScore, getCurrentYear, getRiskLabel } from './panelUtils'

const KHARIF_KEYWORDS = ['RICE', 'PEARL MILLET', 'GROUNDNUT', 'SUGARCANE', 'MAIZE', 'COTTON', 'SOYABEAN', 'SESAMUM', 'KHARIF SORGHUM', 'FINGER MILLET']
const RABI_KEYWORDS = ['CHICKPEA', 'WHEAT', 'MUSTARD', 'LENTIL', 'BARLEY', 'LINSEED', 'SAFFLOWER', 'RABI SORGHUM', 'RAPESEED']

const isSeasonMatch = (cropType: string, season: 'kharif' | 'rabi' | 'all') => {
  if (season === 'all') return true
  const normalized = cropType.toUpperCase()
  const keywords = season === 'kharif' ? KHARIF_KEYWORDS : RABI_KEYWORDS
  return keywords.some((keyword) => normalized.includes(keyword))
}

const CropHealthPanel = () => {
  const { content } = useLanguage()
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
    return <p className="panel-empty">Field not registered yet. Register your field in My Farm to unlock crop health.</p>
  }

  const risk = getRiskLabel(prediction?.health.risk_level)

  return (
    <div className="panel-cards">
      {/* ── Input form ──────────────────────────────────── */}
      <article className="panel-card">
        <div className="panel-card__head">
          <h3>My Crop — Predict & Save</h3>
          <span className="panel-card__metric">Inputs</span>
        </div>
        <p>Select the crop you want to grow and get a real, persisted prediction.</p>
        {cropsLoading ? (
          <div className="panel-skeleton" />
        ) : (
          <div className="panel-simulator">
            <div className="panel-toggle">
              <button type="button" className={season === 'kharif' ? 'active' : ''} onClick={() => setSeason('kharif')}>Kharif</button>
              <button type="button" className={season === 'rabi' ? 'active' : ''} onClick={() => setSeason('rabi')}>Rabi</button>
              <button type="button" className={season === 'all' ? 'active' : ''} onClick={() => setSeason('all')}>All</button>
            </div>
            <label className="panel-myfarm-field">
              Crop type
              <select value={selectedCrop} onChange={(e) => setSelectedCrop(e.target.value)}>
                <option value="">Select crop</option>
                {cropOptions.map((crop: CropItem) => (
                  <option key={crop.crop_type} value={crop.crop_type}>{crop.display_name}</option>
                ))}
              </select>
            </label>
            <label className="panel-myfarm-field">
              NPK input (kg/ha)
              <input type="number" value={npkInput} onChange={(e) => setNpkInput(e.target.value)} />
            </label>
            <label className="panel-myfarm-field">
              Irrigation ratio (0-1)
              <input type="number" step="0.01" value={irrigationRatio} onChange={(e) => setIrrigationRatio(e.target.value)} />
            </label>
            <label className="panel-myfarm-field">
              Year
              <input type="number" value={year} onChange={(e) => setYear(e.target.value)} />
            </label>
            <button type="button" className="panel-mapbox__button" onClick={handlePredict} disabled={loading}>
              {loading ? 'Predicting…' : 'Predict & Save'}
            </button>
          </div>
        )}
      </article>

      {/* ── Health Score Results ─────────────────────────── */}
      <article className="panel-card">
        <div className="panel-card__head">
          <h3>Health Score</h3>
          <span className={`panel-card__metric panel-risk panel-risk--${risk.tone}`}>{risk.label}</span>
        </div>
        <p>Latest prediction results for your crop.</p>
        {loading || historyLoading ? (
          <div className="panel-skeleton" />
        ) : prediction ? (
          <>
            <div className="panel-metric">
              <strong>{formatScore(prediction.health.final_health_score)}</strong>
              <span>Yield: {formatNumber(prediction.predicted_yield, 1)} kg/ha</span>
              <span>Benchmark: {formatNumber(prediction.benchmark_yield, 1)} kg/ha</span>
            </div>
            <ul className="panel-list" style={{ marginTop: 12 }}>
              <li>Yield score: {formatScore(prediction.health.yield_score)}</li>
              <li>Soil score: {formatScore(prediction.health.soil_score)}</li>
              <li>Water score: {formatScore(prediction.health.water_score)}</li>
              <li>Climate score: {formatScore(prediction.health.climate_score)}</li>
              <li>NDVI score: {formatScore(prediction.health.ndvi_score)}</li>
              <li>Loan: {prediction.health.loan_decision}</li>
            </ul>
          </>
        ) : (
          <p className="panel-empty">Run your first prediction above to see health score.</p>
        )}
      </article>

      {/* ── History ─────────────────────────────────────── */}
      <article className="panel-card">
        <div className="panel-card__head">
          <h3>Prediction History</h3>
          <span className="panel-card__metric">{history.length} records</span>
        </div>
        <p>All saved predictions for this field.</p>
        {historyLoading ? (
          <div className="panel-skeleton" />
        ) : history.length === 0 ? (
          <p className="panel-empty">No predictions yet.</p>
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
