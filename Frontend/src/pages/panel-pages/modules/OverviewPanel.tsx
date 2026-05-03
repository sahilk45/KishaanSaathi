import { useEffect, useMemo, useState } from 'react'
import {
  Leaf, Thermometer, Droplets, TrendingUp, Map, Activity,
  CloudRain, Bell, BrainCircuit, AlertTriangle,
} from 'lucide-react'
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

const ScoreBar = ({ score, tone }: { score: number | undefined; tone: string }) => {
  const val = Math.round(score ?? 0)
  const color = tone === 'green' ? '#16a34a' : tone === 'yellow' ? '#d97706' : '#dc2626'
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
      <div style={{ flex: 1, height: 6, background: '#e5e7eb', borderRadius: 99, overflow: 'hidden' }}>
        <div style={{ width: `${val}%`, height: '100%', background: color, borderRadius: 99, transition: 'width 0.6s ease' }} />
      </div>
      <span style={{ fontSize: '0.8rem', fontWeight: 700, color, minWidth: 34, textAlign: 'right' }}>{val}%</span>
    </div>
  )
}

const OverviewBlock = ({
  icon: Icon, title, badge, badgeTone, summary, children, defaultOpen = false,
}: {
  icon: React.ElementType
  title: string
  badge?: string
  badgeTone?: string
  summary: string
  children: React.ReactNode
  defaultOpen?: boolean
}) => {
  const [open, setOpen] = useState(defaultOpen)
  const toneColor = badgeTone === 'green' ? '#16a34a' : badgeTone === 'yellow' ? '#d97706' : badgeTone === 'red' ? '#dc2626' : '#6b7280'
  const toneBg = badgeTone === 'green' ? '#dcfce7' : badgeTone === 'yellow' ? '#fef9c3' : badgeTone === 'red' ? '#fee2e2' : '#f3f4f6'

  return (
    <article className="panel-card" style={{ cursor: 'pointer', padding: 0, overflow: 'hidden' }}>
      <div
        onClick={() => setOpen(o => !o)}
        style={{
          display: 'flex', alignItems: 'center', gap: 14, padding: '14px 18px',
          borderBottom: open ? '1px solid var(--border-light)' : 'none',
          userSelect: 'none',
        }}
      >
        <span style={{
          width: 36, height: 36, borderRadius: 10, background: '#f0fdf4', color: '#16a34a',
          display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0,
        }}>
          <Icon size={18} />
        </span>
        <div style={{ flex: 1 }}>
          <p style={{ fontWeight: 700, fontSize: '0.95rem', color: 'var(--text-main)', margin: 0 }}>{title}</p>
          <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', margin: '2px 0 0' }}>{summary}</p>
        </div>
        {badge && (
          <span style={{
            background: toneBg, color: toneColor, border: `1px solid ${toneColor}33`,
            borderRadius: 99, padding: '3px 10px', fontSize: '0.72rem', fontWeight: 700,
            textTransform: 'uppercase', letterSpacing: '0.06em', whiteSpace: 'nowrap',
          }}>{badge}</span>
        )}
        <span style={{ fontSize: '0.9rem', color: 'var(--text-muted)', transition: 'transform 0.2s', transform: open ? 'rotate(180deg)' : 'rotate(0)', display: 'inline-block' }}>▾</span>
      </div>
      {open && (
        <div style={{ padding: '14px 18px', background: 'var(--bg-body)' }}>{children}</div>
      )}
    </article>
  )
}

const StatRow = ({ label, value, muted = false }: { label: string; value: string; muted?: boolean }) => (
  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '7px 0', borderBottom: '1px solid var(--border-light)' }}>
    <span style={{ fontSize: '0.83rem', color: 'var(--text-muted)' }}>{label}</span>
    <span style={{ fontSize: '0.85rem', fontWeight: 600, color: muted ? 'var(--text-muted)' : 'var(--text-main)' }}>{value}</span>
  </div>
)

const OverviewPanel = () => {
  const { content, panel } = useLanguage()
  const p = panel.panel.overview
  const { pushToast } = useToast()
  const { fieldId, farmerProfile, fields } = useSession()
  const { crops, loading: cropsLoading } = useCrops()

  const [, setHistory] = useState<FieldHistoryResponse | null>(null)
  const [snapshot, setSnapshot] = useState<AgroSnapshotResponse | null>(null)
  const [prediction, setPrediction] = useState<PredictResponse | null>(null)
  const [loading, setLoading] = useState(false)

  const defaultCrop = useMemo(() => getDefaultCrop(crops), [crops])
  const year = getCurrentYear()
  const activeField = useMemo(() => fields.find(f => f.field_id === fieldId), [fields, fieldId])

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
          const predicted = await apiClient.predict({ field_id: fieldId, crop_type: defaultCrop.crop_type, npk_input: DEFAULT_NPK, year, irrigation_ratio: DEFAULT_IRR })
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
    return () => { active = false }
  }, [content, cropsLoading, defaultCrop, fieldId, pushToast, year])

  if (!fieldId) return <p className="panel-empty">{p.noData || 'Field not registered yet.'}</p>

  const risk = getRiskLabel(prediction?.health.risk_level)
  const healthScore = prediction?.health.final_health_score ?? 0

  const heroStats = [
    { Icon: Leaf, label: p.healthScore, value: loading ? '…' : formatScore(healthScore), sub: risk.label, tone: risk.tone },
    { Icon: Thermometer, label: p.weatherSnapshot, value: loading ? '…' : `${formatNumber(snapshot?.weather?.air_temp, 1)}°C`, sub: `Humidity ${formatNumber(snapshot?.weather?.humidity, 0)}%`, tone: 'neutral' },
    { Icon: Droplets, label: 'Soil Moisture', value: loading ? '…' : formatNumber(snapshot?.soil?.soil_moisture, 2), sub: `Cloud ${formatNumber(snapshot?.weather?.cloud_cover, 0)}%`, tone: 'neutral' },
    { Icon: TrendingUp, label: 'Predicted Yield', value: loading ? '…' : `${formatNumber(prediction?.predicted_yield, 0)} kg/ha`, sub: `Benchmark ${formatNumber(prediction?.benchmark_yield, 0)} kg/ha`, tone: 'neutral' },
  ]

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>

      {/* Hero stats */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '0.75rem' }}>
        {heroStats.map(({ Icon, label, value, sub, tone }) => (
          <div key={label} className="panel-card" style={{ padding: '14px 16px', textAlign: 'center' }}>
            <span style={{ width: 34, height: 34, borderRadius: 10, background: '#f0fdf4', color: '#16a34a', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto 8px' }}>
              <Icon size={17} />
            </span>
            <p style={{ fontSize: '0.72rem', color: 'var(--text-muted)', margin: 0, textTransform: 'uppercase', letterSpacing: '0.06em' }}>{label}</p>
            {loading ? (
              <div className="panel-skeleton" style={{ height: 28, marginTop: 6, borderRadius: 6 }} />
            ) : (
              <>
                <p style={{ fontSize: '1.3rem', fontWeight: 800, margin: '4px 0 2px', color: tone === 'green' ? '#16a34a' : tone === 'red' ? '#dc2626' : tone === 'yellow' ? '#d97706' : 'var(--text-main)' }}>{value}</p>
                <p style={{ fontSize: '0.72rem', color: 'var(--text-muted)', margin: 0 }}>{sub}</p>
              </>
            )}
          </div>
        ))}
      </div>

      {/* Farm info */}
      <OverviewBlock icon={Map} title="Your Farm" badge={activeField ? 'Active' : 'No field'} badgeTone={activeField ? 'green' : 'red'} summary={activeField ? `${activeField.field_name} · ${activeField.area_hectares ?? '—'} ha · ${activeField.state_name ?? ''}` : 'No field registered'} defaultOpen>
        <StatRow label="Field Name" value={activeField?.field_name ?? '—'} />
        <StatRow label="Field ID" value={fieldId} muted />
        <StatRow label="Area" value={activeField?.area_hectares ? `${activeField.area_hectares} ha` : '—'} />
        <StatRow label="Location" value={activeField?.city_name && activeField?.state_name ? `${activeField.city_name}, ${activeField.state_name}` : '—'} />
        <StatRow label="Farmer" value={farmerProfile?.name ?? '—'} />
        <StatRow label="District" value={farmerProfile?.dist_name ?? '—'} />
      </OverviewBlock>

      {/* Health score */}
      <OverviewBlock icon={Activity} title={p.healthScore} badge={loading ? '…' : formatScore(healthScore)} badgeTone={risk.tone} summary={p.healthScoreDesc}>
        {loading ? <div className="panel-skeleton" style={{ height: 80 }} /> : prediction ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            {([['Yield Score', prediction.health.yield_score], ['Soil Score', prediction.health.soil_score], ['Water Score', prediction.health.water_score], ['Climate Score', prediction.health.climate_score], ['NDVI Score', prediction.health.ndvi_score]] as [string, number][]).map(([label, score]) => (
              <div key={label}>
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4 }}>
                  <span style={{ fontSize: '0.82rem', color: 'var(--text-muted)' }}>{label}</span>
                </div>
                <ScoreBar score={score} tone={risk.tone} />
              </div>
            ))}
            <div style={{ marginTop: 8, paddingTop: 8, borderTop: '1px solid var(--border-light)', display: 'flex', justifyContent: 'space-between' }}>
              <span style={{ fontSize: '0.82rem', color: 'var(--text-muted)' }}>Loan Decision</span>
              <span style={{ fontSize: '0.85rem', fontWeight: 700 }}>{prediction.health.loan_decision}</span>
            </div>
          </div>
        ) : <p className="panel-empty">Run a Crop Health prediction first.</p>}
      </OverviewBlock>

      {/* Weather */}
      <OverviewBlock icon={CloudRain} title={p.weatherSnapshot} badge={snapshot ? `${formatNumber(snapshot.weather?.air_temp, 1)}°C` : loading ? '…' : 'N/A'} badgeTone="neutral" summary={p.weatherSnapshotDesc}>
        {loading ? <div className="panel-skeleton" style={{ height: 80 }} /> : snapshot ? (
          <>
            <StatRow label="Air Temperature" value={`${formatNumber(snapshot.weather?.air_temp, 1)}°C`} />
            <StatRow label="Humidity" value={`${formatNumber(snapshot.weather?.humidity, 1)}%`} />
            <StatRow label="Cloud Cover" value={`${formatNumber(snapshot.weather?.cloud_cover, 1)}%`} />
            <StatRow label="Soil Moisture" value={formatNumber(snapshot.soil?.soil_moisture, 3)} />
            <StatRow label="Soil Surface Temp" value={`${formatNumber(snapshot.soil?.soil_temp_surface, 1)}°C`} />
            <StatRow label="Latest Image Date" value={snapshot.latest_image_date ?? 'N/A'} muted />
          </>
        ) : <p className="panel-empty">Weather data not available yet.</p>}
      </OverviewBlock>

      {/* Alerts */}
      <OverviewBlock icon={Bell} title={p.activeAlerts} badge={p.signals} badgeTone={risk.tone === 'red' ? 'red' : 'neutral'} summary={p.activeAlertsDesc}>
        {loading ? <div className="panel-skeleton" style={{ height: 60 }} /> : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {[
              { label: 'Risk Level', value: risk.label, urgent: risk.tone === 'red' || risk.tone === 'yellow', Icon: AlertTriangle },
              { label: 'Cloud Cover', value: `${formatNumber(snapshot?.weather?.cloud_cover, 0)}%`, urgent: (snapshot?.weather?.cloud_cover ?? 0) > 70, Icon: CloudRain },
              { label: 'Soil Moisture', value: formatNumber(snapshot?.soil?.soil_moisture, 3), urgent: false, Icon: Droplets },
              { label: 'Loan Decision', value: prediction?.health.loan_decision ?? 'N/A', urgent: prediction?.health.loan_decision === 'DECLINE', Icon: AlertTriangle },
            ].map(({ label, value, urgent, Icon: AlertIcon }) => (
              <div key={label} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '8px 12px', borderRadius: 8, background: urgent ? '#fff7ed' : 'var(--bg-card)', border: urgent ? '1px solid #fed7aa' : '1px solid var(--border-light)' }}>
                <span style={{ display: 'flex', alignItems: 'center', gap: 7, fontSize: '0.83rem', color: 'var(--text-muted)' }}>
                  <AlertIcon size={13} color={urgent ? '#c2410c' : 'currentColor'} />
                  {label}
                </span>
                <span style={{ fontSize: '0.85rem', fontWeight: 700, color: urgent ? '#c2410c' : 'var(--text-main)' }}>{value}</span>
              </div>
            ))}
          </div>
        )}
      </OverviewBlock>

      {/* AI Insight */}
      <OverviewBlock icon={BrainCircuit} title={p.aiInsight} badge={p.summary} badgeTone="neutral" summary={p.aiInsightDesc}>
        {loading ? <div className="panel-skeleton" style={{ height: 60 }} /> : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
            <div style={{ background: 'var(--bg-card)', borderRadius: 10, padding: '12px 14px', border: '1px solid var(--border-light)' }}>
              <p style={{ fontSize: '0.83rem', color: 'var(--text-muted)', margin: '0 0 4px' }}>Recommended Crop</p>
              <p style={{ fontWeight: 700, margin: 0 }}>{defaultCrop?.display_name ?? 'N/A'}</p>
            </div>
            <div style={{ background: 'var(--bg-card)', borderRadius: 10, padding: '12px 14px', border: '1px solid var(--border-light)' }}>
              <p style={{ fontSize: '0.83rem', color: 'var(--text-muted)', margin: '0 0 4px' }}>Loan Assessment</p>
              <p style={{ fontWeight: 700, margin: 0 }}>{prediction?.health.loan_decision ?? 'Run a prediction first'}</p>
            </div>
            <StatRow label="NDVI Mean" value={snapshot?.ndvi_stats?.mean?.toFixed(3) ?? 'N/A'} />
            <StatRow label="NDVI Max" value={snapshot?.ndvi_stats?.max?.toFixed(3) ?? 'N/A'} />
            <StatRow label="Data Source" value={snapshot?.source ?? 'N/A'} muted />
          </div>
        )}
      </OverviewBlock>
    </div>
  )
}

export default OverviewPanel
