import { useEffect, useState } from 'react'
import { apiClient } from '../../../services/apiClient'
import { getLocalizedApiError } from '../../../services/apiErrors'
import { useLanguage } from '../../../context/LanguageContext'
import { useSession } from '../../../context/SessionContext'
import { useToast } from '../../../context/ToastContext'
import type { AgroSnapshotResponse } from '../../../types/api'
import { formatNumber } from './panelUtils'

const WeatherAlertsPanel = () => {
  const { content } = useLanguage()
  const { pushToast } = useToast()
  const { fieldId } = useSession()
  const [snapshot, setSnapshot] = useState<AgroSnapshotResponse | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!fieldId) return
    let active = true
    const loadSnapshot = async () => {
      setLoading(true)
      try {
        const payload = await apiClient.getAgroSnapshot(fieldId)
        if (!active) return
        setSnapshot(payload)
      } catch (error) {
        const message = getLocalizedApiError(error, content)
        if (!active) return
        pushToast(message, 'error')
      } finally {
        if (active) setLoading(false)
      }
    }

    loadSnapshot()

    return () => {
      active = false
    }
  }, [content, fieldId, pushToast])

  if (!fieldId) {
    return <p className="panel-empty">Field not registered yet. Register your field in My Farm to unlock alerts.</p>
  }

  return (
    <div className="panel-cards">
      <article className="panel-card">
        <div className="panel-card__head">
          <h3>7-Day Forecast</h3>
          <span className="panel-card__metric">Snapshot</span>
        </div>
        <p>Live weather signal from the agro snapshot feed.</p>
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
          <h3>Alerts Log</h3>
          <span className="panel-card__metric">Latest</span>
        </div>
        <p>Auto-detected alerts from soil + atmosphere signals.</p>
        {loading ? (
          <div className="panel-skeleton" />
        ) : (
          <ul className="panel-list">
            <li>Cloud cover: {formatNumber(snapshot?.weather?.cloud_cover, 0)}%</li>
            <li>Soil moisture: {formatNumber(snapshot?.soil?.soil_moisture, 2)}</li>
            <li>Soil temp: {formatNumber(snapshot?.soil?.soil_temp_surface, 1)}°C</li>
          </ul>
        )}
      </article>
    </div>
  )
}

export default WeatherAlertsPanel
