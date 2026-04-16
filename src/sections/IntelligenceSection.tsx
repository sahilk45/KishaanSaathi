import { useLanguage } from '../context/LanguageContext'

const intelligenceCardImages = [
  '/page3-block1 below picture.png',
  '/page3-block2 below picture.png',
]

const IntelligenceSection = () => {
  const { content } = useLanguage()

  return (
    <section className="intel">
      <div className="intel__inner">
        <h2 className="intel__heading">{content.intelligence.heading}</h2>
        <p className="intel__sub">{content.intelligence.subheading}</p>

        <div className="intel__cards">
          {content.intelligence.cards.map(
            (
              card: {
                icon: string
                title: string
                description: string
                imageAlt: string
              },
              index: number,
            ) => (
            <div key={card.title} className="intel__card">
              <span className="intel__tag">{card.icon}</span>
              <h3 className="intel__card-title">{card.title}</h3>
              <p className="intel__card-body">{card.description}</p>
              <div className="intel__card-img">
                <img
                  src={intelligenceCardImages[index] ?? intelligenceCardImages[0]}
                  alt={card.imageAlt}
                />
              </div>
            </div>
            ),
          )}
        </div>
      </div>
    </section>
  )
}

export default IntelligenceSection