import { useMemo, useState } from 'react'
import { apiClient } from '../../../services/apiClient'
import { getLocalizedApiError } from '../../../services/apiErrors'
import { useLanguage } from '../../../context/LanguageContext'
import { useSession } from '../../../context/SessionContext'
import { useToast } from '../../../context/ToastContext'
import { useCrops } from '../../../context/CropContext'
import type { CropItem, PredictResponse } from '../../../types/api'
import { formatNumber, formatScore, getCurrentYear } from './panelUtils'

const KHARIF_KEYWORDS = ['RICE', 'PEARL MILLET', 'GROUNDNUT', 'SUGARCANE', 'MAIZE', 'COTTON', 'SOYABEAN', 'SESAMUM', 'KHARIF SORGHUM', 'FINGER MILLET']
const RABI_KEYWORDS = ['CHICKPEA', 'WHEAT', 'MUSTARD', 'LENTIL', 'BARLEY', 'LINSEED', 'SAFFLOWER', 'RABI SORGHUM', 'RAPESEED']

const isSeasonMatch = (cropType: string, season: 'kharif' | 'rabi' | 'all') => {
  if (season === 'all') return true
  const normalized = cropType.toUpperCase()
  const keywords = season === 'kharif' ? KHARIF_KEYWORDS : RABI_KEYWORDS
  return keywords.some((keyword) => normalized.includes(keyword))
}

const WhatIfSimulatorPanel = () => {
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

  const filteredCrops = useMemo(() => crops.filter((crop) => isSeasonMatch(crop.crop_type, season)), [crops, season])

  const cropOptions = filteredCrops.length ? filteredCrops : crops

  const handleSimulate = async () => {
    if (!fieldId) {
      const message = content.errors.fieldId
      pushToast(message, 'error')
      return
    }

    const cropType = selectedCrop || cropOptions[0]?.crop_type
    if (!cropType) {
      const message = content.errors.cropType
      pushToast(message, 'error')
      return
    }

    const npk = Number(npkInput)
    const irr = Number(irrigationRatio)
    const yr = Number(year)

    if (!Number.isFinite(npk) || !Number.isFinite(irr) || !Number.isFinite(yr)) {
      const message = content.errors.validation
      pushToast(message, 'error')
      return
    }

    setLoading(true)
    try {
      // dry_run = true — What-If is preview only, no DB persistence
      const payload = await apiClient.predict({
        field_id: fieldId,
        crop_type: cropType,
        npk_input: npk,
        year: yr,
        irrigation_ratio: irr,
      }, true)
      setPrediction(payload)
    } catch (error) {
      const message = getLocalizedApiError(error, content)
      pushToast(message, 'error')
    } finally {
      setLoading(false)
    }
  }

  if (!fieldId) {
    return <p className="panel-empty">Field not registered yet. Register your field in My Farm to run simulations.</p>
  }

  return (
    <div className="panel-cards">
      <article className="panel-card">
        <div className="panel-card__head">
          <h3>Scenario Controls</h3>
          <span className="panel-card__metric">Inputs</span>
        </div>
        <p>Adjust crop, irrigation, and input values to simulate outcomes.</p>
        {cropsLoading ? (
          <div className="panel-skeleton" />
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '20px', marginTop: '16px' }}>
            <div className="panel-toggle" style={{ justifyContent: 'flex-start', marginBottom: '8px' }}>
              <button type="button" className={season === 'kharif' ? 'active' : ''} onClick={() => setSeason('kharif')}>
                Kharif
              </button>
              <button type="button" className={season === 'rabi' ? 'active' : ''} onClick={() => setSeason('rabi')}>
                Rabi
              </button>
              <button type="button" className={season === 'all' ? 'active' : ''} onClick={() => setSeason('all')}>
                All
              </button>
            </div>
            
            <div style={{ display: 'grid', gridTemplateColumns: '1fr', gap: '20px' }}>
              <label className="panel-myfarm-field">
                Crop type
                <select value={selectedCrop} onChange={(event) => setSelectedCrop(event.target.value)}>
                  <option value="">Select crop</option>
                  {cropOptions.map((crop: CropItem) => (
                    <option key={crop.crop_type} value={crop.crop_type}>
                      {crop.display_name}
                    </option>
                  ))}
                </select>
              </label>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px' }}>
              <label className="panel-myfarm-field">
                NPK input (kg/ha)
                <input type="number" value={npkInput} onChange={(event) => setNpkInput(event.target.value)} />
              </label>
              <label className="panel-myfarm-field">
                Irrigation ratio (0-1)
                <input type="number" step="0.01" value={irrigationRatio} onChange={(event) => setIrrigationRatio(event.target.value)} />
              </label>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px' }}>
              <label className="panel-myfarm-field">
                Year
                <input type="number" value={year} onChange={(event) => setYear(event.target.value)} />
              </label>
            </div>

            <div style={{ marginTop: '16px' }}>
              <button 
                type="button" 
                className="panel-mapbox__button" 
                onClick={handleSimulate} 
                disabled={loading}
                style={{ 
                  width: '100%',
                  padding: '12px', 
                  fontSize: '1.05rem',
                  borderRadius: '12px',
                  fontWeight: 600,
                  display: 'flex',
                  justifyContent: 'center'
                }}
              >
                {loading ? 'Simulating…' : 'Run simulation'}
              </button>
            </div>
          </div>
        )}
      </article>

      <article className="panel-card">
        <div className="panel-card__head">
          <h3>Live Output</h3>
          <span className="panel-card__metric">Result</span>
        </div>
        <p>Projected yield and health impact for the selected scenario.</p>
        {loading ? (
          <div className="panel-skeleton" />
        ) : prediction ? (
          <div className="panel-metric">
            <strong>{formatNumber(prediction.predicted_yield, 1)} kg/ha</strong>
            <span>Health score {formatScore(prediction.health.final_health_score)}</span>
            <span>Loan: {prediction.health.loan_decision}</span>
          </div>
        ) : (
          <p className="panel-empty">Run a simulation to see output.</p>
        )}
      </article>
    </div>
  )
}

export default WhatIfSimulatorPanel
