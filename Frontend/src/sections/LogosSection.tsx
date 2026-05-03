import { useLanguage } from '../context/LanguageContext'

const LogosSection = () => {
  const { content } = useLanguage()

  return (
    <section className="logos">
      <div className="logos__grid">
        {content.logos.companies.map((stateName: string) => (
          <span key={stateName} className="logos__state">
            {stateName}
          </span>
        ))}
      </div>
    </section>
  )
}

export default LogosSection