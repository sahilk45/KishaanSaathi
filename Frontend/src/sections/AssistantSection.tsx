import { useLanguage } from '../context/LanguageContext'

const AssistantSection = () => {
  const { content } = useLanguage()

  return (
    <section className="assistant">
      <div className="assistant__card">
        <p className="eyebrow">{content.assistant.eyebrow}</p>
        <h2 className="assistant__heading">{content.assistant.heading}</h2>
        <p className="assistant__sub">
          {content.assistant.paragraphs[0]}
          <br />
          <br />
          {content.assistant.paragraphs[1]}
        </p>
        <div className="assistant__mockup">
          <img src="/page4.png" alt={content.assistant.imageAlt} />
        </div>
      </div>
    </section>
  )
}

export default AssistantSection