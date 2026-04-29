import { useLanguage } from '../context/LanguageContext'

const apiBaseUrl = ((import.meta.env.VITE_API_BASE_URL as string | undefined) ?? 'http://127.0.0.1:8000').replace(
  /\/+$/,
  '',
)

const oauthLoginUrl =
  (import.meta.env.VITE_OAUTH_LOGIN_URL as string | undefined) ?? `${apiBaseUrl}/auth/google/login`

const NavbarSection = () => {
  const { content, languageLabel, cycleLanguage } = useLanguage()

  return (
    <header className="navbar">
      <div className="navbar__inner">
        <a href="#" className="navbar__logo">
          <img src="/KrishiMitra.png" alt={content.navbar.logoAlt} />
          <span className="brand-text">{content.navbar.brandName}</span>
        </a>

        <nav className="navbar__nav">
          <a href="#">{content.navbar.nav.features}</a>
          <a href="#">{content.navbar.nav.howItWorks}</a>
          <a href="#">{content.navbar.nav.forBanks}</a>
          <a href="#">{content.navbar.nav.pricing}</a>
        </nav>

        <div className="navbar__cta">
          <button type="button" className="btn-ghost" onClick={cycleLanguage}>
            {languageLabel}
          </button>
          <button
            type="button"
            className="btn-primary"
            onClick={() => {
              window.location.href = oauthLoginUrl
            }}
          >
            {content.navbar.getStarted}
          </button>
        </div>
      </div>
    </header>
  )
}

export default NavbarSection