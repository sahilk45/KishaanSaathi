import { useLanguage } from '../../../context/LanguageContext'
import { useSession } from '../../../context/SessionContext'

const SettingsPanel = () => {
  const { panel, language, setLanguage } = useLanguage()
  const { farmerId, fieldId } = useSession()
  const s = panel.panel.settings

  const LANGS = [
    { code: 'EN' as const, label: 'English' },
    { code: 'HI' as const, label: 'हिंदी' },
    { code: 'PA' as const, label: 'ਪੰਜਾਬੀ' },
  ]

  return (
    <div className="panel-cards">
      {/* Account Info */}
      <article className="panel-card">
        <div className="panel-card__head">
          <h3>{s.accountInfo}</h3>
        </div>
        <p>{s.accountInfoDesc}</p>
        <div className="panel-myfarm-grid" style={{ marginTop: 16 }}>
          <label className="panel-myfarm-field">
            {s.farmerId}
            <input type="text" value={farmerId || s.notAvailable} readOnly />
          </label>
          <label className="panel-myfarm-field">
            Active Field ID
            <input type="text" value={fieldId || s.notAvailable} readOnly />
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

      {/* Preferences placeholder */}
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
