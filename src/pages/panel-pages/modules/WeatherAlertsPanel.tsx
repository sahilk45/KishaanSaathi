import { useEffect, useState } from 'react'
import { Thermometer, Droplets, Cloud, Sprout, AlertTriangle, CheckCircle, Info, Clock } from 'lucide-react'
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
        if (payload.history.length > 0) setLatest(payload.history[0])
      } catch (error) {
        const message = getLocalizedApiError(error, content)
        if (!active) return
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
    return <p className="panel-empty">Field not registered yet. Register your field in My Farm to unlock weather &amp; alerts.</p>
  }

  const risk = getRiskLabel(latest?.health.risk_level)

  const alerts: { message: string; severity: 'info' | 'warning' | 'danger' }[] = []
  if (latest) {
    if (latest.cloud_cover !== null && latest.cloud_cover !== undefined && latest.cloud_cover > 70)
      alerts.push({ message: `Heavy cloud cover detected (${formatNumber(latest.cloud_cover, 0)}%)`, severity: 'warning' })
    if (latest.humidity !== null && latest.humidity !== undefined && latest.humidity > 85)
      alerts.push({ message: `High humidity alert (${formatNumber(latest.humidity, 0)}%)`, severity: 'warning' })
    if (latest.air_temp !== null && latest.air_temp !== undefined && latest.air_temp > 40)
      alerts.push({ message: `Extreme heat warning (${formatNumber(latest.air_temp, 1)}°C)`, severity: 'danger' })
    if (latest.soil_moisture !== null && latest.soil_moisture !== undefined && latest.soil_moisture < 0.1)
      alerts.push({ message: `Low soil moisture (${formatNumber(latest.soil_moisture, 2)})`, severity: 'danger' })
    if (latest.health.climate_score < 50)
      alerts.push({ message: `Climate stress detected (score: ${formatScore(latest.health.climate_score)})`, severity: 'warning' })
    if (risk.tone === 'high')
      alerts.push({ message: `Overall risk level: ${risk.label}`, severity: 'danger' })
    if (alerts.length === 0)
      alerts.push({ message: 'All conditions within normal range.', severity: 'info' })
  }

  const weatherTiles = latest ? [
    { Icon: Thermometer, label: 'Air Temp', value: `${formatNumber(latest.air_temp, 1)}°C` },
    { Icon: Droplets, label: 'Humidity', value: `${formatNumber(latest.humidity, 0)}%` },
    { Icon: Cloud, label: 'Cloud Cover', value: `${formatNumber(latest.cloud_cover, 0)}%` },
    { Icon: Sprout, label: 'Soil Moisture', value: formatNumber(latest.soil_moisture, 3) },
    { Icon: CheckCircle, label: 'Climate Score', value: formatScore(latest.health.climate_score) },
    { Icon: Clock, label: 'Last Updated', value: new Date(latest.calculated_at).toLocaleString() },
  ] : []

  return (
    <div className="panel-cards panel-cards--stacked">
      {/* Weather snapshot card */}
      <article className="panel-card">
        <div className="panel-card__head">
          <h3>{p.title}</h3>
          <span className="panel-card__metric">From prediction</span>
        </div>
        <p>Weather conditions captured during the latest prediction run.</p>

        {loading ? (
          <div className="panel-skeleton" />
        ) : latest ? (
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginTop: 12 }}>
            {weatherTiles.map(({ Icon, label, value }) => (
              <div key={label} style={{
                background: 'var(--bg-body, #f4faf6)',
                border: '1px solid var(--border-light, #deeee5)',
                borderRadius: 8, padding: '10px 14px',
                display: 'flex', alignItems: 'center', gap: 12,
              }}>
                <span style={{ width: 32, height: 32, borderRadius: 8, background: '#f0fdf4', color: '#16a34a', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                  <Icon size={15} />
                </span>
                <div>
                  <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)', display: 'block', textTransform: 'uppercase', letterSpacing: '0.05em' }}>{label}</span>
                  <strong style={{ fontSize: '0.88rem' }}>{value}</strong>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <p className="panel-empty">No prediction data yet. Run a prediction in Crop Health first.</p>
        )}
      </article>

      {/* Alerts log card */}
      <article className="panel-card">
        <div className="panel-card__head">
          <h3>{p.alertsLog}</h3>
          <span className={`panel-card__metric panel-risk panel-risk--${risk.tone}`}>{risk.label}</span>
        </div>
        <p>Auto-generated alerts based on weather and soil conditions.</p>

        {loading ? (
          <div className="panel-skeleton" />
        ) : (
          <ul style={{ listStyle: 'none', display: 'flex', flexDirection: 'column', gap: 8, marginTop: 12 }}>
            {alerts.map((alert, i) => {
              const Icon = alert.severity === 'danger' ? AlertTriangle : alert.severity === 'warning' ? AlertTriangle : Info
              const bg = alert.severity === 'danger' ? '#fef2f2' : alert.severity === 'warning' ? '#fff7ed' : '#f0fdf4'
              const border = alert.severity === 'danger' ? '#fecaca' : alert.severity === 'warning' ? '#fed7aa' : '#bbf7d0'
              const color = alert.severity === 'danger' ? '#dc2626' : alert.severity === 'warning' ? '#d97706' : '#16a34a'
              return (
                <li key={i} style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '9px 12px', borderRadius: 8, background: bg, border: `1px solid ${border}` }}>
                  <Icon size={14} color={color} />
                  <span style={{ fontSize: '0.85rem', color: 'var(--text-main)' }}>{alert.message}</span>
                </li>
              )
            })}
          </ul>
        )}
      </article>
    </div>
  )
}

export default WeatherAlertsPanel
