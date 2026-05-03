import { useEffect, useMemo, useState } from 'react'
import { apiClient } from '../../../services/apiClient'
import { getLocalizedApiError } from '../../../services/apiErrors'
import { useLanguage } from '../../../context/LanguageContext'
import { useSession } from '../../../context/SessionContext'
import { useToast } from '../../../context/ToastContext'
import { useCrops } from '../../../context/CropContext'
import type { AgroSnapshotResponse, FieldHistoryResponse, PredictResponse } from '../../../types/api'
import { formatNumber, formatScore, getCurrentYear, getDefaultCrop, getRiskLabel, latestPrediction } from './panelUtils'

const DEFAULT_NPK = 120
const DEFAULT_IRR = 0.8

const OverviewPanel = () => {
  const { content, panel } = useLanguage()
  const p = panel.panel.overview
  const { pushToast } = useToast()
  const { fieldId } = useSession()
  const { crops, loading: cropsLoading } = useCrops()

  const [, setHistory] = useState<FieldHistoryResponse | null>(null)
  const [snapshot, setSnapshot] = useState<AgroSnapshotResponse | null>(null)
  const [prediction, setPrediction] = useState<PredictResponse | null>(null)
  const [loading, setLoading] = useState(false)

  const defaultCrop = useMemo(() => getDefaultCrop(crops), [crops])
  const year = getCurrentYear()

  useEffect(() => {
    if (!fieldId || cropsLoading || !defaultCrop) return

    let active = true
    const loadOverview = async () => {
      setLoading(true)
      try {
        const [historyPayload, snapshotPayload] = await Promise.all([
          apiClient.getFieldHistory(fieldId),
          apiClient.getAgroSnapshot(fieldId),
        ])
        if (!active) return
        setHistory(historyPayload)
        setSnapshot(snapshotPayload)

        if (!historyPayload.history.length) {
          const predicted = await apiClient.predict({
            field_id: fieldId,
            crop_type: defaultCrop.crop_type,
            npk_input: DEFAULT_NPK,
            year,
            irrigation_ratio: DEFAULT_IRR,
          })
          if (!active) return
          setPrediction(predicted)
        } else {
          setPrediction(latestPrediction(historyPayload.history))
        }
      } catch (error) {
        const message = getLocalizedApiError(error, content)
        if (!active) return
        pushToast(message, 'error')
      } finally {
        if (active) setLoading(false)
      }
    }

    loadOverview()

    return () => {
      active = false
    }
  }, [content, cropsLoading, defaultCrop, fieldId, pushToast, year])

  if (!fieldId) {
    return <p className="panel-empty">{p.noData || 'Field not registered yet.'}</p>
  }

  const currentPrediction = prediction
  const risk = getRiskLabel(currentPrediction?.health.risk_level)

  return (
    <div className="panel-cards">
      <article className="panel-card">
        <div className="panel-card__head">
          <h3>{p.healthScore}</h3>
          <span className="panel-card__metric">{p.latest}</span>
        </div>
        <p>{p.healthScoreDesc}</p>
        {loading ? (
          <div className="panel-skeleton" />
        ) : (
          <div className="panel-metric">
            <strong>{formatScore(currentPrediction?.health.final_health_score)}</strong>
            <span>Risk: {risk.label}</span>
          </div>
        )}
      </article>

      <article className="panel-card">
        <div className="panel-card__head">
          <h3>{p.weatherSnapshot}</h3>
          <span className="panel-card__metric">{p.live}</span>
        </div>
        <p>{p.weatherSnapshotDesc}</p>
        {loading ? (
          <div className="panel-skeleton" />
        ) : (
          <div className="panel-metric">
            <strong>{formatNumber(snapshot?.weather?.air_temp, 1)}°C</strong>
            <span>Humidity {formatNumber(snapshot?.weather?.humidity, 0)}%</span>
          </div>
        )}
      </article>

      <article className="panel-card">
        <div className="panel-card__head">
          <h3>{p.activeAlerts}</h3>
          <span className="panel-card__metric">{p.signals}</span>
        </div>
        <p>{p.activeAlertsDesc}</p>
        {loading ? (
          <div className="panel-skeleton" />
        ) : (
          <ul className="panel-alerts">
            <li>Risk level: {risk.label}</li>
            <li>Cloud cover: {formatNumber(snapshot?.weather?.cloud_cover, 0)}%</li>
            <li>Soil moisture: {formatNumber(snapshot?.soil?.soil_moisture, 2)}</li>
          </ul>
        )}
      </article>

      <article className="panel-card">
        <div className="panel-card__head">
          <h3>{p.aiInsight}</h3>
          <span className="panel-card__metric">{p.summary}</span>
        </div>
        <p>{p.aiInsightDesc}</p>
        {loading ? (
          <div className="panel-skeleton" />
        ) : (
          <div className="panel-insight">
            <strong>Loan decision: {currentPrediction?.health.loan_decision ?? 'N/A'}</strong>
            <span>Suggested crop: {defaultCrop?.display_name ?? 'N/A'}</span>
          </div>
        )}
      </article>
    </div>
  )
}

export default OverviewPanel
