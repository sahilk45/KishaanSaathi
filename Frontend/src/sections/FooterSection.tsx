import { useLanguage } from '../context/LanguageContext'

const FooterSection = () => {
  const { content } = useLanguage()

  return (
    <footer className="footer">
      <div className="footer__inner">
        <div className="footer__top">
          <a href="#" className="footer__logo">
            <img src="/KrishiMitra.png" alt={content.footer.logoAlt} />
            <span className="brand-text">{content.footer.brandName}</span>
          </a>

          <div className="footer__social">
            <img
              src="/link2.png"
              alt={content.footer.socialAlts.linkedin}
              className="footer__social-icon"
            />
            <img
              src="/x-logo2.png"
              alt={content.footer.socialAlts.x}
              className="footer__social-icon"
            />
            <img
              src="/gh.png"
              alt={content.footer.socialAlts.github}
              className="footer__social-icon"
            />
          </div>
        </div>

        <div className="footer__columns">
          <div className="footer__col">
            <h5>{content.footer.columns.brand.title}</h5>
            <a href="#">{content.footer.columns.brand.description}</a>
            {content.footer.columns.brand.languages.map((language: string) => (
              <a key={language} href="#">
                {language}
              </a>
            ))}
          </div>

          <div className="footer__col">
            <h5>{content.footer.columns.product.title}</h5>
            {content.footer.columns.product.items.map((item: string) => (
              <a key={item} href="#">
                {item}
              </a>
            ))}
          </div>

          <div className="footer__col">
            <h5>{content.footer.columns.resources.title}</h5>
            {content.footer.columns.resources.items.map((item: string) => (
              <a key={item} href="#">
                {item}
              </a>
            ))}
          </div>

          <div className="footer__col">
            <h5>{content.footer.columns.company.title}</h5>
            {content.footer.columns.company.items.map((item: string) => (
              <a key={item} href="#">
                {item}
              </a>
            ))}
          </div>

          <div className="footer__col">
            <h5>{content.footer.columns.legal.title}</h5>
            {content.footer.columns.legal.items.map((item: string) => (
              <a key={item} href="#">
                {item}
              </a>
            ))}
          </div>
        </div>

        <div className="footer__bottom">
          <div className="footer__status">
            <span className="footer__status-dot"></span>
            {content.footer.statusLine}
          </div>
          <p className="footer__copy">{content.footer.copyright}</p>
          <div className="footer__theme">
            {content.footer.footerLanguages.map((language: string) => (
              <span key={language}>{language}</span>
            ))}
          </div>
        </div>
      </div>
    </footer>
  )
}

export default FooterSection