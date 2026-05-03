import { useEffect, useState } from 'react'
import { apiClient } from '../../../services/apiClient'
import { getLocalizedApiError } from '../../../services/apiErrors'
import { useLanguage } from '../../../context/LanguageContext'
import { useSession } from '../../../context/SessionContext'
import { useToast } from '../../../context/ToastContext'
import type { PredictResponse } from '../../../types/api'
import { formatNumber, formatScore, getRiskLabel } from './panelUtils'

const WeatherAlertsPanel = () => {
  const { content, panel } = useLanguage()
  const p = panel.panel.weather
  const { pushToast } = useToast()
  const { fieldId } = useSession()
  const [latest, setLatest] = useState<PredictResponse | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!fieldId) return
    let active = true
    const loadData = async () => {
      setLoading(true)
      try {
        const payload = await apiClient.getFieldHistory(fieldId)
        if (!active) return
        if (payload.history.length > 0) {
          setLatest(payload.history[0])
        }
      } catch (error) {
        const message = getLocalizedApiError(error, content)
        if (!active) return
        // 404 is expected if no predictions yet
        if (error && typeof error === 'object' && 'status' in error && (error as { status: number }).status !== 404) {
          pushToast(message, 'error')
        }
      } finally {
        if (active) setLoading(false)
      }
    }

    loadData()
    return () => { active = false }
  }, [content, fieldId, pushToast])

  if (!fieldId) {
    return <p className="panel-empty">Field not registered yet. Register your field in My Farm to unlock weather & alerts.</p>
  }

  const risk = getRiskLabel(latest?.health.risk_level)

  // Generate alerts from prediction data thresholds
  const alerts: { message: string; severity: 'info' | 'warning' | 'danger' }[] = []
  if (latest) {
    if (latest.cloud_cover !== null && latest.cloud_cover !== undefined && latest.cloud_cover > 70) {
      alerts.push({ message: `Heavy cloud cover detected (${formatNumber(latest.cloud_cover, 0)}%)`, severity: 'warning' })
    }
    if (latest.humidity !== null && latest.humidity !== undefined && latest.humidity > 85) {
      alerts.push({ message: `High humidity alert (${formatNumber(latest.humidity, 0)}%)`, severity: 'warning' })
    }
    if (latest.air_temp !== null && latest.air_temp !== undefined && latest.air_temp > 40) {
      alerts.push({ message: `Extreme heat warning (${formatNumber(latest.air_temp, 1)}°C)`, severity: 'danger' })
    }
    if (latest.soil_moisture !== null && latest.soil_moisture !== undefined && latest.soil_moisture < 0.1) {
      alerts.push({ message: `Low soil moisture (${formatNumber(latest.soil_moisture, 2)})`, severity: 'danger' })
    }
    if (latest.health.climate_score < 50) {
      alerts.push({ message: `Climate stress detected (score: ${formatScore(latest.health.climate_score)})`, severity: 'warning' })
    }
    if (risk.tone === 'high') {
      alerts.push({ message: `Overall risk level: ${risk.label}`, severity: 'danger' })
    }
    if (alerts.length === 0) {
      alerts.push({ message: 'All conditions within normal range.', severity: 'info' })
    }
  }

  return (
    <div className="panel-cards panel-cards--stacked">
      <article className="panel-card">
        <div className="panel-card__head">
          <h3>{p.title}</h3>
          <span className="panel-card__metric">From prediction</span>
        </div>
        <p>Weather conditions captured during the latest prediction run.</p>
        {loading ? (
          <div className="panel-skeleton" />
        ) : latest ? (
          <div className="panel-myfarm-grid">
            <div className="panel-myfarm-stat">
              <span>Air Temp</span>
              <strong>{formatNumber(latest.air_temp, 1)}°C</strong>
            </div>
            <div className="panel-myfarm-stat">
              <span>Humidity</span>
              <strong>{formatNumber(latest.humidity, 0)}%</strong>
            </div>
            <div className="panel-myfarm-stat">
              <span>Cloud Cover</span>
              <strong>{formatNumber(latest.cloud_cover, 0)}%</strong>
            </div>
            <div className="panel-myfarm-stat">
              <span>Soil Moisture</span>
              <strong>{formatNumber(latest.soil_moisture, 3)}</strong>
            </div>
            <div className="panel-myfarm-stat">
              <span>Climate Score</span>
              <strong>{formatScore(latest.health.climate_score)}</strong>
            </div>
            <div className="panel-myfarm-stat">
              <span>Last Updated</span>
              <strong>{new Date(latest.calculated_at).toLocaleString()}</strong>
            </div>
          </div>
        ) : (
          <p className="panel-empty">No prediction data yet. Run a prediction in Crop Health first.</p>
        )}
      </article>

      <article className="panel-card">
        <div className="panel-card__head">
          <h3>{p.alertsLog}</h3>
          <span className={`panel-card__metric panel-risk panel-risk--${risk.tone}`}>{risk.label}</span>
        </div>
        <p>Auto-generated alerts based on weather and soil conditions.</p>
        {loading ? (
          <div className="panel-skeleton" />
        ) : (
          <ul className="panel-alerts">
            {alerts.map((alert, i) => (
              <li key={i} className={`panel-alert panel-alert--${alert.severity}`}>
                {alert.severity === 'danger' ? '🔴' : alert.severity === 'warning' ? '🟡' : '🟢'} {alert.message}
              </li>
            ))}
          </ul>
        )}
      </article>
    </div>
  )
}

export default WeatherAlertsPanel
