import { useLanguage } from '../context/LanguageContext'

const MarqueeSection = () => {
  const { content } = useLanguage()

  return (
    <section className="marquee">
      <div className="marquee__inner">
        {content.marquee.companies.map((stateName: string) => (
          <span key={stateName} className="marquee__state">
            {stateName}
          </span>
        ))}
      </div>
    </section>
  )
}

export default MarqueeSection