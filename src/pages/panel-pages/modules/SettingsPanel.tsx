import { useLanguage } from '../../../context/LanguageContext'
import { useSession } from '../../../context/SessionContext'

const SettingsPanel = () => {
  const { panel, language, setLanguage } = useLanguage()
  const { farmerId, fieldId, farmerProfile } = useSession()
  const s = panel.panel.settings

  const LANGS = [
    { code: 'EN' as const, label: 'English' },
    { code: 'HI' as const, label: 'हिंदी' },
    { code: 'PA' as const, label: 'ਪੰਜਾਬੀ' },
  ]

  const na = s.notAvailable

  return (
    <div className="panel-cards panel-cards--stacked">
      {/* Account Info */}
      <article className="panel-card">
        <div className="panel-card__head">
          <h3>{s.accountInfo}</h3>
        </div>
        <p>{s.accountInfoDesc}</p>

        {/* Avatar + name header */}
        {farmerProfile?.picture && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginTop: 20, marginBottom: 4 }}>
            <img
              src={farmerProfile.picture}
              alt={farmerProfile.name ?? 'Farmer'}
              style={{ width: 56, height: 56, borderRadius: '50%', objectFit: 'cover', border: '2px solid var(--border-light)' }}
            />
            <div>
              <strong style={{ fontSize: '1.05rem' }}>{farmerProfile.name ?? na}</strong>
              {farmerProfile.email && (
                <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)', margin: 0 }}>{farmerProfile.email}</p>
              )}
            </div>
          </div>
        )}

        <div className="panel-myfarm-grid" style={{ marginTop: 16 }}>
          <label className="panel-myfarm-field">
            {s.farmerName}
            <input type="text" value={farmerProfile?.name || na} readOnly />
          </label>
          <label className="panel-myfarm-field">
            {s.phone}
            <input type="text" value={farmerProfile?.phone || na} readOnly />
          </label>
          <label className="panel-myfarm-field">
            {s.districtState}
            <input
              type="text"
              value={
                farmerProfile?.dist_name && farmerProfile?.state_name
                  ? `${farmerProfile.dist_name}, ${farmerProfile.state_name}`
                  : farmerProfile?.state_name || na
              }
              readOnly
            />
          </label>
          <label className="panel-myfarm-field">
            {s.farmerId}
            <input type="text" value={farmerId || na} readOnly />
          </label>
          <label className="panel-myfarm-field">
            Active Field ID
            <input type="text" value={fieldId || na} readOnly />
          </label>
        </div>
      </article>

      {/* Language */}
      <article className="panel-card">
        <div className="panel-card__head">
          <h3>{s.language}</h3>
        </div>
        <p>{s.languageDesc}</p>
        <div className="panel-toggle" style={{ marginTop: 16 }}>
          {LANGS.map(({ code, label }) => (
            <button
              key={code}
              type="button"
              className={language === code ? 'active' : ''}
              onClick={() => setLanguage(code)}
            >
              {label}
            </button>
          ))}
        </div>
      </article>

      {/* Preferences */}
      <article className="panel-card">
        <div className="panel-card__head">
          <h3>{s.preferences}</h3>
        </div>
        <p>{s.preferencesDesc}</p>
        <div className="panel-myfarm-grid" style={{ marginTop: 16 }}>
          <label className="panel-myfarm-field" style={{ flexDirection: 'row', alignItems: 'center', gap: 12 }}>
            <input type="checkbox" id="notif-toggle" style={{ width: 'auto' }} />
            Enable push notifications
          </label>
        </div>
      </article>
    </div>
  )
}

export default SettingsPanel
