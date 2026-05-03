import { useEffect, useMemo, useState } from 'react'
import { apiClient } from '../../../services/apiClient'
import { getLocalizedApiError } from '../../../services/apiErrors'
import { useLanguage } from '../../../context/LanguageContext'
import { useSession } from '../../../context/SessionContext'
import { useToast } from '../../../context/ToastContext'
import type { PredictResponse } from '../../../types/api'
import { formatScore, getCurrentYear, getRiskLabel } from './panelUtils'

const HEALTH_BENCHMARK = 60

const LoanEligibilityPanel = () => {
  const { content, panel } = useLanguage()
  const p = panel.panel.loanEligibility
  const { pushToast } = useToast()
  const { fieldId, farmerId, farmerProfile, fields } = useSession()

  // ── Latest prediction (fetched from DB — read-only inputs) ──
  const [latestPrediction, setLatestPrediction] = useState<PredictResponse | null>(null)
  const [historyLoading, setHistoryLoading] = useState(false)

  // ── Submission result ──
  const [prediction, setPrediction] = useState<PredictResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const [submitted, setSubmitted] = useState(false)
  const [loanResult, setLoanResult] = useState<'eligible' | 'rejected' | null>(null)

  // ── Editable form fields ──
  const [farmerName, setFarmerName] = useState(farmerProfile?.name ?? '')
  const [phone, setPhone] = useState(farmerProfile?.phone ?? '')
  const [loanAmount, setLoanAmount] = useState('')

  // Sync name/phone when farmerProfile loads from DB
  useEffect(() => {
    if (farmerProfile?.name) setFarmerName(farmerProfile.name)
    if (farmerProfile?.phone) setPhone(farmerProfile.phone)
  }, [farmerProfile])

  const year = getCurrentYear()
  const selectedField = useMemo(() => fields.find(f => f.field_id === fieldId), [fields, fieldId])

  // ── Fetch latest prediction from DB on mount ──
  useEffect(() => {
    if (!fieldId) return
    let cancelled = false
    const fetchLatest = async () => {
      setHistoryLoading(true)
      try {
        const resp = await apiClient.getFieldHistory(fieldId)
        if (!cancelled && resp.history.length > 0) {
          setLatestPrediction(resp.history[0]) // newest first
        }
      } catch { /* no history yet */ } finally {
        if (!cancelled) setHistoryLoading(false)
      }
    }
    fetchLatest()
    return () => { cancelled = true }
  }, [fieldId])

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault()

    if (!fieldId) {
      pushToast('No field selected. Please register a field first.', 'error')
      return
    }
    if (!latestPrediction) {
      pushToast('Run a Crop Health prediction first before applying for a loan.', 'error')
      return
    }
    if (!farmerName.trim() || !phone.trim() || !loanAmount.trim()) {
      pushToast('Please fill all required fields.', 'error')
      return
    }
    const amount = Number(loanAmount)
    if (!Number.isFinite(amount) || amount <= 0) {
      pushToast('Enter a valid loan amount.', 'error')
      return
    }

    setLoading(true)
    try {
      // Re-run prediction with the same inputs from the latest crop health run (dry_run)
      const predicted = await apiClient.predict({
        field_id: fieldId,
        crop_type: latestPrediction.crop_type,
        npk_input: latestPrediction.irrigation_used * 150, // approximate NPK from stored data
        irrigation_ratio: latestPrediction.irrigation_used,
        year,
      }, true)

      setPrediction(predicted)
      setSubmitted(true)

      const healthScore = predicted.health.final_health_score
      if (healthScore >= HEALTH_BENCHMARK) {
        setLoanResult('eligible')
        pushToast(`✅ Loan approved! Health score: ${Math.round(healthScore)}`, 'success')
      } else {
        setLoanResult('rejected')
        pushToast(`❌ Health score ${Math.round(healthScore)} is below minimum ${HEALTH_BENCHMARK}.`, 'error')
      }
    } catch (error) {
      pushToast(getLocalizedApiError(error, content), 'error')
    } finally {
      setLoading(false)
    }
  }

  // ── No field registered yet ──
  if (!fieldId && fields.length === 0) {
    return (
      <div className="panel-card" style={{ padding: '40px', textAlign: 'center' }}>
        <p style={{ fontSize: '2rem', marginBottom: '16px' }}>🌾</p>
        <h3 style={{ marginBottom: '8px' }}>{p.noFieldsAvailable}</h3>
        <p style={{ color: 'var(--text-muted)' }}>Register a field in the <strong>My Farm</strong> section first.</p>
      </div>
    )
  }

  const healthScore = prediction?.health.final_health_score ?? 0
  const risk = getRiskLabel(prediction?.health.risk_level)

  const printReport = () => {
    const date = new Date().toLocaleDateString('en-IN', { day: '2-digit', month: 'long', year: 'numeric' })
    const ref = `KS-LOAN-${(farmerId ?? '').slice(0, 8).toUpperCase()}`
    const district = farmerProfile?.dist_name && farmerProfile?.state_name
      ? `${farmerProfile.dist_name}, ${farmerProfile.state_name}`
      : '—'

    const row = (label: string, value: string) =>
      `<tr><td>${label}</td><td><strong>${value}</strong></td></tr>`

    const html = `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <title>Loan Approval Certificate — Krishi-Sarthii</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: Georgia, 'Times New Roman', serif; font-size: 12pt; color: #111; background: #fff; padding: 0; }
    .brand { display: flex; justify-content: space-between; align-items: center; background: #1a5c2a; color: #fff; padding: 16px 32px; }
    .brand-left { display: flex; align-items: center; gap: 14px; }
    .brand-icon { font-size: 32pt; line-height: 1; }
    .brand-name { display: block; font-size: 18pt; font-weight: bold; letter-spacing: 0.5px; }
    .brand-tagline { display: block; font-size: 8pt; opacity: 0.82; font-style: italic; margin-top: 2px; }
    .brand-meta { text-align: right; font-size: 8pt; opacity: 0.85; line-height: 1.7; }
    .title-bar { display: flex; justify-content: space-between; align-items: center; background: #f0fdf4; border: 1px solid #d1fae5; border-top: none; border-radius: 0 0 6px 6px; padding: 14px 32px; margin-bottom: 28px; }
    .title-bar h1 { font-size: 18pt; color: #1a5c2a; }
    .title-bar p { font-size: 9pt; color: #555; margin-top: 3px; }
    .badge { background: #dcfce7; color: #14532d; border: 2px solid #16a34a; padding: 8px 18px; border-radius: 8px; font-size: 13pt; font-weight: bold; white-space: nowrap; }
    .content { padding: 0 32px 32px; }
    .section { margin-bottom: 24px; page-break-inside: avoid; }
    .section h2 { font-size: 12pt; color: #1a5c2a; border-bottom: 1px solid #ccc; padding-bottom: 4px; margin-bottom: 10px; }
    table { width: 100%; border-collapse: collapse; }
    td { padding: 7px 10px; border: 1px solid #ddd; font-size: 10.5pt; vertical-align: middle; }
    tr:nth-child(even) td { background: #f9fafb; }
    td:first-child { width: 40%; color: #444; font-weight: 500; }
    .footer { border-top: 1px solid #ccc; margin-top: 32px; padding-top: 12px; font-size: 8pt; color: #888; font-style: italic; line-height: 1.8; }
  </style>
</head>
<body>
  <div class="brand">
    <div class="brand-left">
      <span class="brand-icon">🌾</span>
      <div>
        <span class="brand-name">Krishi-Sarthii</span>
        <span class="brand-tagline">AI-Powered Farm Intelligence Platform</span>
      </div>
    </div>
    <div class="brand-meta">
      <span>Generated on ${date}</span><br/>
      <span>Ref: ${ref}</span>
    </div>
  </div>

  <div class="title-bar">
    <div>
      <h1>Loan Approval Certificate</h1>
      <p>Farm Credit Eligibility Report — AI Assessment</p>
    </div>
    <div class="badge">✅ APPROVED</div>
  </div>

  <div class="content">
    <div class="section">
      <h2>Applicant Details</h2>
      <table><tbody>
        ${row('Farmer Name', farmerName || '—')}
        ${row('Phone Number', phone || '—')}
        ${row('Email', farmerProfile?.email || '—')}
        ${row('State / District', district)}
        ${row('Farmer ID', farmerId || '—')}
      </tbody></table>
    </div>

    <div class="section">
      <h2>Field &amp; Loan Details</h2>
      <table><tbody>
        ${row('Field Name', selectedField?.field_name || '—')}
        ${row('Field ID', fieldId || '—')}
        ${row('Area', selectedField?.area_hectares ? selectedField.area_hectares + ' ha' : '—')}
        ${row('Crop Type', latestPrediction?.crop_type || '—')}
        ${row('Irrigation Used', latestPrediction?.irrigation_used ? latestPrediction.irrigation_used.toFixed(2) : '—')}
        ${row('Loan Amount Requested', '\u20b9' + Number(loanAmount).toLocaleString('en-IN'))}
        ${row('Assessment Year', String(year))}
      </tbody></table>
    </div>

    <div class="section">
      <h2>AI Credit Assessment</h2>
      <table><tbody>
        ${row('Overall Health Score', formatScore(prediction?.health.final_health_score))}
        ${row('Risk Level', risk.label)}
        ${row('Predicted Yield', Math.round(prediction?.predicted_yield || 0) + ' kg/ha')}
        ${row('Yield Score', formatScore(prediction?.health.yield_score))}
        ${row('Soil Score', formatScore(prediction?.health.soil_score))}
        ${row('Water Score', formatScore(prediction?.health.water_score))}
        ${row('Climate Score', formatScore(prediction?.health.climate_score))}
        ${row('NDVI Score', formatScore(prediction?.health.ndvi_score))}
      </tbody></table>
    </div>

    <div class="footer">
      <p>This report is auto-generated by Krishi-Sarthii AI and is for informational purposes only.</p>
      <p>For official bank loan processing, please present this document to your nearest branch along with your Farmer ID.</p>
    </div>
  </div>

  <script>window.onload = function() { window.print(); }<\/script>
</body>
</html>`

    const win = window.open('', '_blank', 'width=900,height=700')
    if (win) {
      win.document.write(html)
      win.document.close()
    }
  }

  return (
    <div style={{ maxWidth: '800px', margin: '0 auto', width: '100%' }}>
      {!submitted ? (
        <article className="panel-card" style={{ padding: '32px' }}>
          <div className="panel-card__head" style={{ justifyContent: 'center', marginBottom: '24px' }}>
            <h2 style={{ fontSize: '1.5rem', fontWeight: 600 }}>{p.formTitle}</h2>
          </div>
          <p style={{ textAlign: 'center', marginBottom: '32px', color: 'var(--text-muted)' }}>
            Your loan eligibility is assessed using your latest Crop Health prediction.
          </p>

          {/* ── Latest crop health snapshot (read-only) ── */}
          {historyLoading ? (
            <div style={{ background: 'var(--bg-body)', borderRadius: '10px', padding: '16px', marginBottom: '24px', textAlign: 'center', color: 'var(--text-muted)' }}>
              Loading your latest crop health data…
            </div>
          ) : latestPrediction ? (
            <div style={{
              background: 'var(--bg-body)',
              border: '1px solid var(--border-light)',
              borderRadius: '10px',
              padding: '16px 20px',
              marginBottom: '24px',
            }}>
              <p style={{ fontSize: '0.78rem', color: 'var(--text-muted)', marginBottom: '12px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.05em' }}>
                📋 Inputs from your last Crop Health analysis
              </p>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '12px' }}>
                {[
                  ['Crop', latestPrediction.crop_type],
                  ['Year', String(latestPrediction.year)],
                  ['Irrigation', latestPrediction.irrigation_used.toFixed(2)],
                  ['Predicted Yield', `${Math.round(latestPrediction.predicted_yield)} kg/ha`],
                  ['Health Score', formatScore(latestPrediction.health.final_health_score)],
                  ['Prediction Date', new Date(latestPrediction.calculated_at).toLocaleDateString('en-IN')],
                ].map(([label, val]) => (
                  <div key={label} style={{ background: 'var(--bg-card)', borderRadius: '8px', padding: '10px 12px' }}>
                    <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)', display: 'block' }}>{label}</span>
                    <strong style={{ fontSize: '0.9rem' }}>{val}</strong>
                  </div>
                ))}
              </div>
              <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginTop: '10px' }}>
                These values are locked. To use different inputs, run a new Crop Health prediction first.
              </p>
            </div>
          ) : (
            <div style={{
              background: '#fff7ed',
              border: '1px solid #fed7aa',
              borderRadius: '10px',
              padding: '16px 20px',
              marginBottom: '24px',
              textAlign: 'center',
              color: '#92400e',
            }}>
              <p style={{ fontWeight: 600, marginBottom: '6px' }}>⚠️ No Crop Health data found</p>
              <p style={{ fontSize: '0.85rem' }}>
                Please go to <strong>Crop Health</strong> and run a prediction first. Loan eligibility is based on your actual farm analysis.
              </p>
            </div>
          )}

          <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
            {/* Farmer name + phone — pre-filled from DB, editable */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px' }}>
              <label className="panel-myfarm-field">
                {p.farmerName}
                <input type="text" value={farmerName} onChange={(e) => setFarmerName(e.target.value)} required />
              </label>
              <label className="panel-myfarm-field">
                {p.farmerPhone}
                <input type="tel" value={phone} onChange={(e) => setPhone(e.target.value)} required />
              </label>
            </div>

            {/* Field info (read-only — auto-selected from DB) */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px' }}>
              <label className="panel-myfarm-field">
                {p.selectField}
                <input
                  type="text"
                  value={selectedField ? `${selectedField.field_name}${selectedField.area_hectares ? ` (${selectedField.area_hectares} ha)` : ''}` : fieldId || '—'}
                  readOnly
                  style={{ background: 'var(--bg-body)', cursor: 'default' }}
                />
              </label>
              <label className="panel-myfarm-field">
                {p.loanAmount}
                <input type="number" value={loanAmount} onChange={(e) => setLoanAmount(e.target.value)} placeholder="e.g. 50000" min="1" required />
              </label>
            </div>

            <div style={{ marginTop: '8px' }}>
              <button
                type="submit"
                className="panel-mapbox__button"
                disabled={loading || !latestPrediction}
                style={{ width: '100%', padding: '14px', fontSize: '1.05rem', borderRadius: '12px', fontWeight: 600, display: 'flex', justifyContent: 'center' }}
              >
                {loading ? p.analyzing : p.submitApplication}
              </button>
            </div>
          </form>
        </article>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '24px' }}>
          <article className="panel-card" style={{ padding: '32px' }}>
            <div style={{ textAlign: 'center', marginBottom: '24px' }}>
              <p style={{ fontSize: '1.1rem', color: loanResult === 'eligible' ? '#16a34a' : '#dc2626', fontWeight: 700, marginBottom: '8px' }}>
                {loanResult === 'eligible' ? p.loanApproved : loanResult === 'rejected' ? p.loanRejected : p.loanReview}
              </p>
              <p style={{ color: 'var(--text-muted)', fontSize: '0.9rem' }}>
                {loanResult === 'eligible'
                  ? p.loanApprovedDesc?.replace('{amount}', Number(loanAmount).toLocaleString('en-IN'))
                  : loanResult === 'rejected'
                    ? p.loanRejectedDesc?.replace('{amount}', Number(loanAmount).toLocaleString('en-IN'))
                    : p.loanReviewDesc?.replace('{amount}', Number(loanAmount).toLocaleString('en-IN'))
                }
              </p>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '16px', marginBottom: '28px' }}>
              {[
                [p.healthScore, `${Math.round(healthScore)}%`, risk.label],
                [p.predictedYield, `${Math.round(prediction?.predicted_yield || 0)} kg/ha`, ''],
                ['Loan Amount', `₹${Number(loanAmount).toLocaleString('en-IN')}`, ''],
              ].map(([label, val, sub]) => (
                <div key={label} style={{ background: 'var(--bg-body)', borderRadius: '10px', padding: '16px', textAlign: 'center' }}>
                  <p style={{ fontSize: '0.78rem', color: 'var(--text-muted)', marginBottom: '6px' }}>{label}</p>
                  <p style={{ fontSize: '1.5rem', fontWeight: 700 }}>{val}</p>
                  {sub && <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>{sub}</p>}
                </div>
              ))}
            </div>

            <div style={{ marginBottom: '24px' }}>
              <h4 style={{ marginBottom: '16px' }}>{p.scoreFactors} — {p.assessment}</h4>
              <p style={{ color: 'var(--text-muted)', fontSize: '0.85rem', marginBottom: '16px' }}>{p.assessmentDesc}</p>
              <ul style={{ listStyle: 'none', display: 'flex', flexDirection: 'column', gap: '8px' }}>
                {[
                  ['yieldScoreDesc', prediction?.health.yield_score],
                  ['soilScoreDesc', prediction?.health.soil_score],
                  ['waterScoreDesc', prediction?.health.water_score],
                  ['climateScoreDesc', prediction?.health.climate_score],
                  ['ndviScoreDesc', prediction?.health.ndvi_score],
                ].map(([key, score]) => (
                  <li key={key as string} style={{ padding: '12px', background: 'var(--bg-body)', borderRadius: '8px' }}>
                    <strong>{(p[key as keyof typeof p] as string)?.replace('{score}', formatScore(score as number | undefined))}</strong>
                  </li>
                ))}
              </ul>
            </div>

            <div style={{ display: 'flex', justifyContent: 'center', marginTop: '32px', gap: '16px' }}>
              <button
                type="button"
                className="panel-mapbox__button panel-mapbox__button--secondary"
                onClick={() => { setSubmitted(false); setPrediction(null); setLoanResult(null) }}
                style={{ padding: '10px 32px', borderRadius: '24px' }}
              >
                {p.startNew}
              </button>
              {loanResult === 'eligible' && (
                <button
                  type="button"
                  className="panel-mapbox__button"
                  onClick={printReport}
                  style={{ padding: '10px 32px', borderRadius: '24px' }}
                >
                  {p.downloadReport}
                </button>
              )}
            </div>
          </article>
        </div>
      )}
    </div>
  )
}

export default LoanEligibilityPanel
