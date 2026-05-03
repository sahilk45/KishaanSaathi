import { useEffect, useMemo, useState } from 'react'
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  BarElement,
  PointElement,
  LineElement,
  Title,
  Tooltip,
  Legend,
} from 'chart.js'
import { Bar } from 'react-chartjs-2'
import { apiClient } from '../../../services/apiClient'
import { getLocalizedApiError } from '../../../services/apiErrors'
import { useLanguage } from '../../../context/LanguageContext'
import { useSession } from '../../../context/SessionContext'
import { useToast } from '../../../context/ToastContext'
import type { ApmcPriceRecord } from '../../../types/api'

ChartJS.register(CategoryScale, LinearScale, BarElement, PointElement, LineElement, Title, Tooltip, Legend)

const COMMODITIES = [
  'Wheat', 'Rice', 'Maize', 'Soyabean', 'Cotton', 'Mustard',
  'Groundnut', 'Potato', 'Onion', 'Tomato', 'Gram', 'Barley',
]

const MarketInsightsPanel = () => {
  const { content, panel } = useLanguage()
  const p = panel.panel.marketInsights
  const { pushToast } = useToast()
  const { farmerId } = useSession()
  const [commodity, setCommodity] = useState(COMMODITIES[0])
  const [prices, setPrices] = useState<ApmcPriceRecord[]>([])
  const [mandis, setMandis] = useState<string[]>([])
  const [state, setState] = useState('')
  const [district, setDistrict] = useState('')
  const [loading, setLoading] = useState(false)
  const [fetched, setFetched] = useState(false)

  const handleFetch = async () => {
    if (!farmerId) {
      pushToast('Farmer profile not found.', 'error')
      return
    }
    setLoading(true)
    setFetched(false)
    try {
      const payload = await apiClient.getApmcPrices(farmerId, commodity)
      setPrices(payload.prices)
      setMandis(payload.mandis_available)
      setState(payload.state)
      setDistrict(payload.district)
      setFetched(true)
      if (payload.prices.length === 0) {
        pushToast(`No price data found for ${commodity} in ${payload.district}, ${payload.state}.`, 'error')
      }
    } catch (error) {
      const message = getLocalizedApiError(error, content)
      pushToast(message, 'error')
    } finally {
      setLoading(false)
    }
  }

  // Auto-fetch on first load
  useEffect(() => {
    if (farmerId) handleFetch()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [farmerId])

  // Group prices by market for chart
  const chartData = useMemo(() => {
    if (!prices.length) return null
    // Deduplicate by market, take latest modal_price per market
    const marketMap = new Map<string, ApmcPriceRecord>()
    for (const p of prices) {
      if (!marketMap.has(p.market)) {
        marketMap.set(p.market, p)
      }
    }
    const entries = Array.from(marketMap.values())
    return {
      labels: entries.map((e) => e.market),
      datasets: [
        {
          label: 'Min Price (₹/Q)',
          data: entries.map((e) => e.min_price),
          backgroundColor: 'rgba(59, 130, 246, 0.6)',
          borderColor: 'rgba(59, 130, 246, 1)',
          borderWidth: 1,
        },
        {
          label: 'Modal Price (₹/Q)',
          data: entries.map((e) => e.modal_price),
          backgroundColor: 'rgba(16, 185, 129, 0.6)',
          borderColor: 'rgba(16, 185, 129, 1)',
          borderWidth: 1,
        },
        {
          label: 'Max Price (₹/Q)',
          data: entries.map((e) => e.max_price),
          backgroundColor: 'rgba(245, 158, 11, 0.6)',
          borderColor: 'rgba(245, 158, 11, 1)',
          borderWidth: 1,
        },
      ],
    }
  }, [prices])

  const chartOptions = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { position: 'top' as const, labels: { color: '#cbd5e1' } },
      title: { display: true, text: `${commodity} — APMC Price Comparison`, color: '#f1f5f9' },
    },
    scales: {
      x: { ticks: { color: '#94a3b8' }, grid: { color: 'rgba(148,163,184,0.1)' } },
      y: { ticks: { color: '#94a3b8' }, grid: { color: 'rgba(148,163,184,0.1)' } },
    },
  }

  if (!farmerId) {
    return <p className="panel-empty">Farmer profile not found. Complete registration to view market insights.</p>
  }

  return (
    <div className="panel-cards">
      {/* ── Selection ────────────────────────────────── */}
      <article className="panel-card">
        <div className="panel-card__head">
          <h3>{p.marketSelection}</h3>
          <span className="panel-card__metric">{state || 'Auto-detect'}</span>
        </div>
        <p>{p.autoDetected}</p>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '20px', marginTop: '16px' }}>
          <label className="panel-myfarm-field">
            {p.commodity}
            <select value={commodity} onChange={(e) => setCommodity(e.target.value)}>
              {COMMODITIES.map((c) => (
                <option key={c} value={c}>{c}</option>
              ))}
            </select>
          </label>
          {fetched ? (
            <p className="panel-myfarm-feedback" style={{ fontSize: '0.9rem', color: 'var(--text-main)' }}>
              Showing APMCs in <strong>{district}, {state}</strong> — {mandis.length} {p.mandisFound}, {prices.length} {p.priceRecords}.
            </p>
          ) : null}
          <div style={{ marginTop: '8px' }}>
            <button 
              type="button" 
              className="panel-mapbox__button" 
              onClick={handleFetch} 
              disabled={loading}
              style={{ width: '100%', padding: '12px', borderRadius: '12px', fontSize: '1.05rem', fontWeight: 600, display: 'flex', justifyContent: 'center' }}
            >
              {loading ? p.fetching : p.fetchPrices}
            </button>
          </div>
        </div>
      </article>

      {/* ── Chart ────────────────────────────────────── */}
      <article className="panel-card">
        <div className="panel-card__head">
          <h3>{p.priceComparison}</h3>
          <span className="panel-card__metric">{prices.length} records</span>
        </div>
        <p>{p.priceDesc}</p>
        {loading ? (
          <div className="panel-skeleton" style={{ height: 300 }} />
        ) : chartData ? (
          <div style={{ height: 320, position: 'relative' }}>
            <Bar data={chartData} options={chartOptions} />
          </div>
        ) : (
          <p className="panel-empty">{fetched ? p.noPriceData : 'Fetch prices to see the chart.'}</p>
        )}
      </article>

      {/* ── Price table ──────────────────────────────── */}
      {prices.length > 0 ? (
        <article className="panel-card">
          <div className="panel-card__head">
            <h3>Price Table</h3>
            <span className="panel-card__metric">Details</span>
          </div>
          <div className="apmc-table-wrap">
            <table className="apmc-table">
              <thead>
                <tr>
                  <th>Market</th>
                  <th>Min ₹</th>
                  <th>Modal ₹</th>
                  <th>Max ₹</th>
                  <th>Date</th>
                </tr>
              </thead>
              <tbody>
                {prices.map((row, i) => (
                  <tr key={`${row.market}-${i}`}>
                    <td>{row.market}</td>
                    <td>{row.min_price.toFixed(0)}</td>
                    <td>{row.modal_price.toFixed(0)}</td>
                    <td>{row.max_price.toFixed(0)}</td>
                    <td>{row.arrival_date}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </article>
      ) : null}

      {/* ── Available mandis ─────────────────────────── */}
      {mandis.length > 0 ? (
        <article className="panel-card">
          <div className="panel-card__head">
            <h3>{p.nearbyApmcs}</h3>
            <span className="panel-card__metric">{mandis.length} mandis</span>
          </div>
          <p>APMCs in {district}, {state} from mandi_master.json</p>
          <ul className="panel-list">
            {mandis.map((m) => (
              <li key={m}>{m}</li>
            ))}
          </ul>
        </article>
      ) : null}
    </div>
  )
}

export default MarketInsightsPanel
