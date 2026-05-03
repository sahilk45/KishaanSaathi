import { useLanguage } from '../context/LanguageContext'

const ctaFeatureImages = ['/logo1.png', '/logo2.png']

const CtaSection = () => {
  const { content } = useLanguage()

  return (
    <section className="cta">
      <div className="cta__inner">
        <h2 className="cta__heading">
          {content.cta.headingLine1}
          <br />
          {content.cta.headingLine2}
        </h2>
        <p className="cta__sub">
          {content.cta.subLines[0]}
          <br />
          {content.cta.subLines[1]}
          <br />
          {content.cta.subLines[2]}
        </p>

        <div className="cta__buttons">
          <button className="cta__btn-fill">{content.cta.primaryButton}</button>
          <button className="cta__btn-outline">{content.cta.secondaryButton}</button>
        </div>
      </div>

      <div className="cta__features">
        {content.cta.featureCards.map(
          (
            featureCard: { title: string; description: string; linkText: string },
            index: number,
          ) => (
            <div key={featureCard.title} className="cta__feature">
              <img
                src={ctaFeatureImages[index] ?? ctaFeatureImages[0]}
                alt=""
                className="cta__feature-icon"
              />
              <h4>{featureCard.title}</h4>
              <p>{featureCard.description}</p>
              <a href="#" className="cta__link">
                {featureCard.linkText}
              </a>
            </div>
          ),
        )}
      </div>
    </section>
  )
}

export default CtaSection