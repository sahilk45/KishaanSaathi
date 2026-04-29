import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'

type DistrictItem = {
  state_name: string
  dist_name: string
}

type GoogleUser = {
  sub?: string
  email?: string
  name?: string
  picture?: string
  email_verified?: boolean
}

type FarmerRegisterResponse = {
  farmer_id: string
  name: string
  phone: string
  state_name: string
  dist_name: string
}

const FARMER_ID_STORAGE_KEY = 'ks_farmer_id'
const LEGACY_FARMER_ID_STORAGE_KEY = 'ks_last_farmer_id'
const FARMER_PROFILE_STORAGE_KEY = 'ks_farmer_profile'
const GOOGLE_USER_STORAGE_KEY = 'ks_google_user'

const apiBaseUrl = ((import.meta.env.VITE_API_BASE_URL as string | undefined) ?? 'http://127.0.0.1:8000').replace(
  /\/+$/,
  '',
)

const decodeBase64Url = (value: string) => {
  const padded = value.replace(/-/g, '+').replace(/_/g, '/')
  const padLength = padded.length % 4
  const normalized = padLength ? `${padded}${'='.repeat(4 - padLength)}` : padded
  try {
    return atob(normalized)
  } catch {
    return ''
  }
}

const decodeUserPayload = (value: string | null): GoogleUser | null => {
  if (!value) return null
  const raw = decodeBase64Url(value)
  if (!raw) return null
  try {
    return JSON.parse(raw) as GoogleUser
  } catch {
    return null
  }
}

const OAuthCallbackPage = () => {
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()

  const [googleUser, setGoogleUser] = useState<GoogleUser | null>(null)
  const [districts, setDistricts] = useState<DistrictItem[]>([])
  const [isLoadingDistricts, setIsLoadingDistricts] = useState(true)
  const [districtError, setDistrictError] = useState('')
  const [fullName, setFullName] = useState('')
  const [phone, setPhone] = useState('')
  const [stateName, setStateName] = useState('')
  const [districtName, setDistrictName] = useState('')
  const [submitStatus, setSubmitStatus] = useState<'idle' | 'submitting' | 'error'>('idle')
  const [submitMessage, setSubmitMessage] = useState('')

  useEffect(() => {
    const decoded = decodeUserPayload(searchParams.get('user'))
    if (!decoded) return

    setGoogleUser(decoded)
    setFullName(decoded.name ?? '')

    const queryFarmerId = searchParams.get('farmer_id') ?? ''
    if (queryFarmerId) {
      if (typeof window !== 'undefined') {
        window.localStorage.setItem(FARMER_ID_STORAGE_KEY, queryFarmerId)
        window.localStorage.setItem(LEGACY_FARMER_ID_STORAGE_KEY, queryFarmerId)
      }
      navigate('/panel/overview', { replace: true })
      return
    }

    if (typeof window !== 'undefined') {
      window.localStorage.setItem(GOOGLE_USER_STORAGE_KEY, JSON.stringify(decoded))
    }
  }, [navigate, searchParams])

  useEffect(() => {
    const fetchDistricts = async () => {
      setIsLoadingDistricts(true)
      setDistrictError('')
      try {
        const response = await fetch(`${apiBaseUrl}/districts`)
        if (!response.ok) {
          throw new Error(`Failed to load districts (${response.status})`)
        }
        const payload = (await response.json()) as DistrictItem[]
        setDistricts(payload)
      } catch (error) {
        setDistrictError(error instanceof Error ? error.message : 'Unable to load district list.')
      } finally {
        setIsLoadingDistricts(false)
      }
    }

    fetchDistricts()
  }, [])

  const states = useMemo(() => {
    const unique = new Set(districts.map((item) => item.state_name))
    return Array.from(unique).sort((a, b) => a.localeCompare(b))
  }, [districts])

  const districtsForState = useMemo(() => {
    return districts
      .filter((item) => item.state_name === stateName)
      .map((item) => item.dist_name)
      .sort((a, b) => a.localeCompare(b))
  }, [districts, stateName])

  const handleSubmit = async (event: React.FormEvent<HTMLFormElement>) => {
    event.preventDefault()

    if (!fullName.trim() || !phone.trim() || !stateName || !districtName) {
      setSubmitStatus('error')
      setSubmitMessage('Please fill all fields before continuing.')
      return
    }

    setSubmitStatus('submitting')
    setSubmitMessage('Registering farmer profile...')

    try {
      if (!googleUser?.sub) {
        throw new Error('Missing Google user info. Please log in again.')
      }

      const response = await fetch(`${apiBaseUrl}/farmers/register`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          google_sub: googleUser.sub,
          name: fullName.trim(),
          phone: phone.trim(),
          state_name: stateName,
          dist_name: districtName,
          email: googleUser.email ?? undefined,
          email_verified: googleUser.email_verified ?? undefined,
          picture: googleUser.picture ?? undefined,
        }),
      })

      if (!response.ok) {
        const payload = (await response.json().catch(() => null)) as { detail?: unknown } | null
        const detail = payload?.detail
        const message = typeof detail === 'string' && detail.trim() ? detail : `Registration failed (${response.status})`
        throw new Error(message)
      }

      const farmer = (await response.json()) as FarmerRegisterResponse
      if (typeof window !== 'undefined') {
        window.localStorage.setItem(FARMER_ID_STORAGE_KEY, farmer.farmer_id)
        window.localStorage.setItem(LEGACY_FARMER_ID_STORAGE_KEY, farmer.farmer_id)
        window.localStorage.setItem(FARMER_PROFILE_STORAGE_KEY, JSON.stringify(farmer))
      }

      navigate('/panel/overview', { replace: true })
    } catch (error) {
      setSubmitStatus('error')
      setSubmitMessage(error instanceof Error ? error.message : 'Registration failed.')
    }
  }

  if (!googleUser) {
    return (
      <section className="auth-fallback">
        <div className="auth-fallback__card">
          <h1>Login required</h1>
          <p>We couldn’t verify your Google login. Please try again.</p>
          <Link to="/" className="btn-primary">
            Back to home
          </Link>
        </div>
      </section>
    )
  }

  return (
    <section className="auth-overlay" aria-live="polite">
      <div className="auth-modal" role="dialog" aria-modal="true" aria-label="Register yourself">
        <header className="auth-modal__header">
          <div>
            <p className="auth-modal__eyebrow">Welcome</p>
            <h1>Register yourself</h1>
            <p className="auth-modal__subtitle">
              We’ll use this to generate your farmer profile and personalized dashboard.
            </p>
          </div>
          {googleUser.picture ? (
            <img className="auth-modal__avatar" src={googleUser.picture} alt={googleUser.name ?? 'User'} />
          ) : null}
        </header>

        <div className="auth-modal__user">
          <p>
            Signed in as <strong>{googleUser.name ?? 'Farmer'}</strong>
          </p>
          <span>{googleUser.email ?? ''}</span>
        </div>

        <form className="auth-modal__form" onSubmit={handleSubmit}>
          <label className="auth-modal__field">
            Full name
            <input
              type="text"
              value={fullName}
              onChange={(event) => setFullName(event.target.value)}
              placeholder="Ramesh Kumar"
              required
            />
          </label>
          <label className="auth-modal__field">
            Phone number
            <input
              type="tel"
              value={phone}
              onChange={(event) => setPhone(event.target.value)}
              placeholder="9876543210"
              required
            />
          </label>
          <label className="auth-modal__field">
            State
            <select value={stateName} onChange={(event) => {
              setStateName(event.target.value)
              setDistrictName('')
            }} required>
              <option value="">Select state</option>
              {states.map((state) => (
                <option key={state} value={state}>
                  {state}
                </option>
              ))}
            </select>
          </label>
          <label className="auth-modal__field">
            District
            <select
              value={districtName}
              onChange={(event) => setDistrictName(event.target.value)}
              required
              disabled={!stateName || isLoadingDistricts}
            >
              <option value="">Select district</option>
              {districtsForState.map((district) => (
                <option key={district} value={district}>
                  {district}
                </option>
              ))}
            </select>
          </label>

          {isLoadingDistricts ? (
            <p className="auth-modal__hint">Loading district list…</p>
          ) : null}
          {districtError ? <p className="auth-modal__error">{districtError}</p> : null}
          {submitMessage ? (
            <p className={submitStatus === 'error' ? 'auth-modal__error' : 'auth-modal__hint'}>{submitMessage}</p>
          ) : null}

          <div className="auth-modal__actions">
            <button type="submit" className="btn-primary" disabled={submitStatus === 'submitting'}>
              {submitStatus === 'submitting' ? 'Registering…' : 'Create farmer profile'}
            </button>
            <Link to="/" className="btn-ghost">
              Cancel
            </Link>
          </div>
        </form>
      </div>
    </section>
  )
}

export default OAuthCallbackPage
