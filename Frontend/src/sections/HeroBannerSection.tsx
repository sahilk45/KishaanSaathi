import { useLanguage } from '../context/LanguageContext'

const HeroBannerSection = () => {
  const { content } = useLanguage()

  return (
    <section className="hero">
      <div className="hero__content">
        <h1 className="hero__title">
          {content.hero.titleLine1}
          <br />
          {content.hero.titleLine2}
        </h1>

        <p className="hero__subtitle">
          {content.hero.lead}
          <br />
          {content.hero.description}
          <br />
          {content.hero.availability}
          <br />
          {content.hero.stats}
        </p>

        <div className="hero__form">
          <input type="email" placeholder={content.hero.inputPlaceholder} />
          <button type="button">{content.hero.demoCta}</button>
        </div>
      </div>

      <div className="hero__gradient"></div>
    </section>
  )
}

export default HeroBannerSection