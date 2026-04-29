import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'

type MandiMaster = Record<string, Record<string, string[]>>

type ApmcMasterResponse = {
  master: MandiMaster
}

type ApmcHistoryRow = {
  arrival_date: string
  min_price: number
  max_price: number
  modal_price: number
}

type ApmcHistoryResponse = {
  state: string
  district: string
  market: string
  commodity: string
  source: string
  latest_real_date: string
  records: ApmcHistoryRow[]
}

const COMMON_COMMODITIES = [
  'Wheat',
  'Rice',
  'Maize',
  'Soyabean',
  'Cotton',
  'Mustard',
  'Groundnut',
  'Potato',
  'Onion',
  'Tomato',
]

const HISTORY_DAYS = 25

const ApmcPage = () => {
  const apiBaseUrl = ((import.meta.env.VITE_API_BASE_URL as string | undefined) ?? 'http://127.0.0.1:8000').replace(
    /\/+$/,
    '',
  )

  const [master, setMaster] = useState<MandiMaster>({})
  const [masterLoading, setMasterLoading] = useState(true)
  const [masterError, setMasterError] = useState<string | null>(null)

  const [stateName, setStateName] = useState('')
  const [districtName, setDistrictName] = useState('')
  const [marketName, setMarketName] = useState('')
  const [commodity, setCommodity] = useState(COMMON_COMMODITIES[0])

  const [historyLoading, setHistoryLoading] = useState(false)
  const [historyError, setHistoryError] = useState<string | null>(null)
  const [historyData, setHistoryData] = useState<ApmcHistoryResponse | null>(null)

  useEffect(() => {
    const loadMaster = async () => {
      setMasterLoading(true)
      setMasterError(null)

      try {
        const response = await fetch(`${apiBaseUrl}/apmc/master`)
        if (!response.ok) {
          throw new Error(`Could not load mandi master (${response.status})`)
        }

        const payload = (await response.json()) as ApmcMasterResponse
        const masterPayload = payload.master ?? {}

        setMaster(masterPayload)

        const firstState = Object.keys(masterPayload)[0] ?? ''
        setStateName(firstState)

        const firstDistrict = firstState ? Object.keys(masterPayload[firstState] ?? {})[0] ?? '' : ''
        setDistrictName(firstDistrict)

        const firstMarket = firstState && firstDistrict ? (masterPayload[firstState]?.[firstDistrict]?.[0] ?? '') : ''
        setMarketName(firstMarket)
      } catch (error) {
        setMasterError(error instanceof Error ? error.message : 'Failed to load mandi master data.')
      } finally {
        setMasterLoading(false)
      }
    }

    void loadMaster()
  }, [apiBaseUrl])

  const states = useMemo(() => Object.keys(master), [master])

  const districts = useMemo(() => {
    if (!stateName) return []
    return Object.keys(master[stateName] ?? {})
  }, [master, stateName])

  const markets = useMemo(() => {
    if (!stateName || !districtName) return []
    return master[stateName]?.[districtName] ?? []
  }, [districtName, master, stateName])

  useEffect(() => {
    if (!stateName) return

    const validDistricts = Object.keys(master[stateName] ?? {})
    if (validDistricts.length === 0) {
      setDistrictName('')
      setMarketName('')
      return
    }

    if (!validDistricts.includes(districtName)) {
      const nextDistrict = validDistricts[0]
      setDistrictName(nextDistrict)
      const nextMarket = master[stateName]?.[nextDistrict]?.[0] ?? ''
      setMarketName(nextMarket)
    }
  }, [districtName, master, stateName])

  useEffect(() => {
    if (!stateName || !districtName) return

    const validMarkets = master[stateName]?.[districtName] ?? []
    if (validMarkets.length === 0) {
      setMarketName('')
      return
    }

    if (!validMarkets.includes(marketName)) {
      setMarketName(validMarkets[0])
    }
  }, [districtName, marketName, master, stateName])

  const canFetchHistory = Boolean(stateName && districtName && marketName && commodity.trim())

  const handleFetchHistory = async () => {
    if (!canFetchHistory) return

    setHistoryLoading(true)
    setHistoryError(null)

    try {
      const response = await fetch(`${apiBaseUrl}/apmc/history`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          state: stateName,
          district: districtName,
          market: marketName,
          commodity: commodity.trim(),
          days: HISTORY_DAYS,
        }),
      })

      if (!response.ok) {
        const payload = (await response.json().catch(() => null)) as { detail?: unknown } | null
        const detail = payload?.detail
        if (typeof detail === 'string') {
          throw new Error(detail)
        }
        throw new Error(`Could not load mandi history (${response.status})`)
      }

      const payload = (await response.json()) as ApmcHistoryResponse
      setHistoryData(payload)
    } catch (error) {
      setHistoryError(error instanceof Error ? error.message : 'Failed to fetch mandi history.')
    } finally {
      setHistoryLoading(false)
    }
  }

  return (
    <main className="panel-page apmc-route-page" aria-label="APMC mandi insights">
      <section className="apmc-shell">
        <header className="apmc-header">
          <div>
            <p className="apmc-kicker">Live APMC Pricing</p>
            <h1>APMC Mandi Explorer</h1>
            <p>
              Select state, district, and corresponding mandi to fetch latest commodity prices and simulated {HISTORY_DAYS}
              -day history.
            </p>
          </div>
          <Link to="/panel/market-insights" className="apmc-back-link">
            Back to panel
          </Link>
        </header>

        <section className="apmc-card">
          <h2>Selection</h2>

          {masterLoading ? <p className="apmc-message">Loading mandi master data...</p> : null}
          {masterError ? <p className="apmc-message apmc-message--error">{masterError}</p> : null}

          <div className="apmc-grid">
            <label className="apmc-field">
              State
              <select value={stateName} onChange={(event) => setStateName(event.target.value)} disabled={masterLoading}>
                {states.map((state) => (
                  <option key={state} value={state}>
                    {state}
                  </option>
                ))}
              </select>
            </label>

            <label className="apmc-field">
              District
              <select
                value={districtName}
                onChange={(event) => setDistrictName(event.target.value)}
                disabled={masterLoading || !stateName}
              >
                {districts.map((district) => (
                  <option key={district} value={district}>
                    {district}
                  </option>
                ))}
              </select>
            </label>

            <label className="apmc-field">
              APMC Mandi
              <select
                value={marketName}
                onChange={(event) => setMarketName(event.target.value)}
                disabled={masterLoading || !districtName}
              >
                {markets.map((market) => (
                  <option key={market} value={market}>
                    {market}
                  </option>
                ))}
              </select>
            </label>

            <label className="apmc-field">
              Commodity / Crop
              <select value={commodity} onChange={(event) => setCommodity(event.target.value)}>
                {COMMON_COMMODITIES.map((item) => (
                  <option key={item} value={item}>
                    {item}
                  </option>
                ))}
              </select>
            </label>
          </div>

          <div className="apmc-actions">
            <button type="button" className="apmc-btn" disabled={!canFetchHistory || historyLoading} onClick={handleFetchHistory}>
              {historyLoading ? 'Fetching...' : `Fetch ${HISTORY_DAYS}-day history`}
            </button>
          </div>

          {historyError ? <p className="apmc-message apmc-message--error">{historyError}</p> : null}
        </section>

        <section className="apmc-card">
          <div className="apmc-table-head">
            <h2>Price Table</h2>
            <div className="apmc-meta">
              <span>Source: {historyData?.source ?? 'N/A'}</span>
              <span>Latest real date: {historyData?.latest_real_date ?? 'N/A'}</span>
            </div>
          </div>

          {!historyData ? (
            <p className="apmc-message">Choose filters and fetch mandi history to view min/max/modal prices.</p>
          ) : (
            <div className="apmc-table-wrap">
              <table className="apmc-table">
                <thead>
                  <tr>
                    <th>Date</th>
                    <th>Min Price</th>
                    <th>Max Price</th>
                    <th>Modal Price</th>
                  </tr>
                </thead>
                <tbody>
                  {historyData.records.map((row) => (
                    <tr key={row.arrival_date}>
                      <td>{row.arrival_date}</td>
                      <td>{row.min_price.toFixed(2)}</td>
                      <td>{row.max_price.toFixed(2)}</td>
                      <td>{row.modal_price.toFixed(2)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </section>
    </main>
  )
}

export default ApmcPage
