import { Link } from 'react-router-dom'
import { useLanguage } from '../context/LanguageContext'

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
          <Link to="/panel/overview" className="btn-primary">
            {content.navbar.getStarted}
          </Link>
        </div>
      </div>
    </header>
  )
}

export default NavbarSection