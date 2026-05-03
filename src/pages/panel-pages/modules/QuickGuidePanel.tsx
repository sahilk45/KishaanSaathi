import { useLanguage } from '../../../context/LanguageContext'

const QuickGuidePanel = () => {
  const { panel } = useLanguage()
  const p = panel.panel.quickGuide

  return (
    <div className="panel-cards">
      <article className="panel-card">
        <div className="panel-card__head">
          <h3>{p.title}</h3>
          <span className="panel-card__metric">Steps</span>
        </div>
        <p>{p.subtitle}</p>

        <ol className="panel-list" style={{ marginTop: '20px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <li>
            <strong>1. </strong>{p.step1}
          </li>
          <li>
            <strong>2. </strong>{p.step2}
          </li>
          <li>
            <strong>3. </strong>{p.step3}
          </li>
          <li>
            <strong>4. </strong>{p.step4}
          </li>
          <li>
            <strong>5. </strong>{p.step5}
          </li>
        </ol>
      </article>
    </div>
  )
}

export default QuickGuidePanel
