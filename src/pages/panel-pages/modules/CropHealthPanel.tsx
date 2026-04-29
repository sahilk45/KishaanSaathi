import { useEffect, useState } from 'react'
import { apiClient } from '../../../services/apiClient'
import { getLocalizedApiError } from '../../../services/apiErrors'
import { useLanguage } from '../../../context/LanguageContext'
import { useSession } from '../../../context/SessionContext'
import { useToast } from '../../../context/ToastContext'
import type { AgroSnapshotResponse, FieldHistoryResponse } from '../../../types/api'
import { formatNumber, formatScore } from './panelUtils'

const CropHealthPanel = () => {
  const { content } = useLanguage()
  const { pushToast } = useToast()
  const { fieldId } = useSession()
  const [history, setHistory] = useState<FieldHistoryResponse | null>(null)
  const [snapshot, setSnapshot] = useState<AgroSnapshotResponse | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!fieldId) return
    let active = true
    const loadData = async () => {
      setLoading(true)
      try {
        const [historyPayload, snapshotPayload] = await Promise.all([
          apiClient.getFieldHistory(fieldId),
          apiClient.getAgroSnapshot(fieldId),
        ])
        if (!active) return
        setHistory(historyPayload)
        setSnapshot(snapshotPayload)
      } catch (error) {
        const message = getLocalizedApiError(error, content)
        if (!active) return
        pushToast(message, 'error')
      } finally {
        if (active) setLoading(false)
      }
    }

    loadData()

    return () => {
      active = false
    }
  }, [content, fieldId, pushToast])

  if (!fieldId) {
    return <p className="panel-empty">Field not registered yet. Register your field in My Farm to unlock crop health.</p>
  }

  const latest = history?.history?.[0]

  return (
    <div className="panel-cards">
      <article className="panel-card">
        <div className="panel-card__head">
          <h3>NDVI Map</h3>
          <span className="panel-card__metric">Satellite</span>
        </div>
        <p>Latest NDVI stats from the agro snapshot feed.</p>
        {loading ? (
          <div className="panel-skeleton" />
        ) : (
          <div className="panel-metric">
            <strong>{formatNumber(snapshot?.ndvi_stats?.mean, 3)}</strong>
            <span>Max NDVI {formatNumber(snapshot?.ndvi_stats?.max, 3)}</span>
          </div>
        )}
      </article>

      <article className="panel-card">
        <div className="panel-card__head">
          <h3>Health Score</h3>
          <span className="panel-card__metric">Latest</span>
        </div>
        <p>Composite score powered by yield + NDVI.</p>
        {loading ? (
          <div className="panel-skeleton" />
        ) : (
          <div className="panel-metric">
            <strong>{formatScore(latest?.health.final_health_score)}</strong>
            <span>NDVI score {formatScore(latest?.health.ndvi_score)}</span>
          </div>
        )}
      </article>

      <article className="panel-card">
        <div className="panel-card__head">
          <h3>Health Trend</h3>
          <span className="panel-card__metric">History</span>
        </div>
        <p>Recent prediction history for the field.</p>
        {loading ? (
          <div className="panel-skeleton" />
        ) : (
          <ul className="panel-list">
            {(history?.history ?? []).slice(0, 5).map((item) => (
              <li key={`${item.crop_type}-${item.year}`}>{item.year} · {formatScore(item.health.final_health_score)}</li>
            ))}
          </ul>
        )}
      </article>
    </div>
  )
}

export default CropHealthPanel
