import { useLanguage } from '../context/LanguageContext'

const storyCardImages = ['/story-1.png', '/story-2.png', '/story-3.png']

const StoriesSection = () => {
  const { content } = useLanguage()

  return (
    <section className="stories">
      <div className="stories__inner">
        <h2 className="stories__heading">{content.stories.heading}</h2>
        <p className="stories__sub">
          {content.stories.subheadingLines[0]}
          <br />
          {content.stories.subheadingLines[1]}
        </p>
      </div>

      <div className="stories__grid">
        {content.stories.cards.map(
          (
            card: { imageAlt: string; description: string; highlight: string },
            index: number,
          ) => (
            <article key={card.highlight} className="stories__card">
              <div className="stories__media">
                <img
                  src={storyCardImages[index] ?? storyCardImages[0]}
                  alt={card.imageAlt}
                />
              </div>
              <div className="stories__card-body">
                <span className="stories__badge">{card.highlight}</span>
                <p>{card.description}</p>
              </div>
            </article>
          ),
        )}
      </div>
    </section>
  )
}

export default StoriesSection