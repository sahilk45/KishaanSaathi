import { useLanguage } from '../context/LanguageContext'

const EnterpriseSection = () => {
  const { content } = useLanguage()

  const workflowSteps = content.enterprise.featureCards
    .flatMap((featureCard: { title: string }) => featureCard.title.split(' · '))
    .map((stepTitle: string) => stepTitle.trim())
    .filter((stepTitle: string) => stepTitle.length > 0)
    .map((stepTitle: string, index: number) => {
      const stepMatch = stepTitle.match(/^(\d{2})\s*(.*)$/)

      return {
        id: `${index}-${stepTitle}`,
        number: stepMatch?.[1] ?? `${index + 1}`.padStart(2, '0'),
        title: stepMatch?.[2]?.trim() || stepTitle,
      }
    })

  return (
    <section className="enterprise">
      <div className="enterprise__inner">
        <p className="eyebrow">{content.enterprise.eyebrow}</p>

        <div className="enterprise__top">
          <div className="enterprise__top-left">
            <h2 className="enterprise__heading">
              {content.enterprise.headingLine1}
              <br />
              {content.enterprise.headingLine2}
            </h2>
            <p className="enterprise__sub">
              {content.enterprise.descriptionLines.map((line: string, index: number) => (
                <span key={`${index}-${line}`}>
                  {line}
                  {index < content.enterprise.descriptionLines.length - 1 && <br />}
                </span>
              ))}
            </p>
          </div>

          <button className="btn-enterprise">{content.enterprise.aiCta}</button>
        </div>

        <div className="enterprise__steps">
          {workflowSteps.map((workflowStep: { id: string; number: string; title: string }) => (
            <article key={workflowStep.id} className="enterprise__step-card">
              <div className="enterprise__step-header">
                <span className="enterprise__step-number">{workflowStep.number}</span>
                <img
                  src="/KrishiMitra.png"
                  alt={content.footer.logoAlt}
                  className="enterprise__icon"
                />
              </div>
              <h4>{workflowStep.title}</h4>
            </article>
          ))}
        </div>

        <div className="enterprise__story">
          <img src="/page5.png" alt={content.enterprise.storyImageAlt} />
        </div>
      </div>
    </section>
  )
}

export default EnterpriseSection