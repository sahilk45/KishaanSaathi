import { useEffect, useState } from 'react'
import { apiClient } from '../../../services/apiClient'
import { getLocalizedApiError } from '../../../services/apiErrors'
import { useLanguage } from '../../../context/LanguageContext'
import { useSession } from '../../../context/SessionContext'
import { useToast } from '../../../context/ToastContext'
import type { FieldHistoryResponse } from '../../../types/api'
import { formatScore } from './panelUtils'

const CropTimelinePanel = () => {
  const { content } = useLanguage()
  const { pushToast } = useToast()
  const { fieldId } = useSession()
  const [history, setHistory] = useState<FieldHistoryResponse | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!fieldId) return
    let active = true
    const loadTimeline = async () => {
      setLoading(true)
      try {
        const payload = await apiClient.getFieldHistory(fieldId)
        if (!active) return
        setHistory(payload)
      } catch (error) {
        const message = getLocalizedApiError(error, content)
        if (!active) return
        pushToast(message, 'error')
      } finally {
        if (active) setLoading(false)
      }
    }

    loadTimeline()

    return () => {
      active = false
    }
  }, [content, fieldId, pushToast])

  if (!fieldId) {
    return <p className="panel-empty">Field not registered yet. Register your field in My Farm to unlock timeline.</p>
  }

  return (
    <div className="panel-cards">
      <article className="panel-card">
        <div className="panel-card__head">
          <h3>Growth Stage Timeline</h3>
          <span className="panel-card__metric">History</span>
        </div>
        <p>Historic predictions sorted by year.</p>
        {loading ? (
          <div className="panel-skeleton" />
        ) : (
          <ul className="panel-list">
            {(history?.history ?? []).slice(0, 8).map((item) => (
              <li key={`${item.crop_type}-${item.year}`}>
                {item.year} · {item.crop_type} · {formatScore(item.health.final_health_score)}
              </li>
            ))}
          </ul>
        )}
      </article>

      <article className="panel-card">
        <div className="panel-card__head">
          <h3>Milestone Log</h3>
          <span className="panel-card__metric">Predictions</span>
        </div>
        <p>Recent prediction runs with calculated timestamp.</p>
        {loading ? (
          <div className="panel-skeleton" />
        ) : (
          <ul className="panel-list">
            {(history?.history ?? []).slice(0, 5).map((item) => (
              <li key={`${item.crop_type}-${item.year}-calc`}>{new Date(item.calculated_at).toLocaleDateString()}</li>
            ))}
          </ul>
        )}
      </article>
    </div>
  )
}

export default CropTimelinePanel
