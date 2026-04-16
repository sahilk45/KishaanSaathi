import { Bot, Search } from 'lucide-react'
import { Navigate, useParams } from 'react-router-dom'
import { defaultPanelRoute, isPanelRoute, panelItemsByRoute, type VisualKind } from './panelConfig'
import MyFarmWorkspace from './MyFarmWorkspace'

const renderVisual = (kind: VisualKind, metric?: string) => {
  switch (kind) {
    case 'kpi':
      return (
        <div className="panel-visual panel-visual--kpi">
          <p>{metric ?? 'Live score'}</p>
          <span>Updated 2 min ago</span>
        </div>
      )
    case 'map':
      return (
        <div className="panel-visual panel-visual--map">
          <div className="panel-map-grid" />
          <div className="panel-map-chip">Polygon Active</div>
        </div>
      )
    case 'line':
      return (
        <div className="panel-visual panel-visual--line">
          <span style={{ height: '35%' }} />
          <span style={{ height: '50%' }} />
          <span style={{ height: '42%' }} />
          <span style={{ height: '68%' }} />
          <span style={{ height: '62%' }} />
          <span style={{ height: '80%' }} />
        </div>
      )
    case 'bar':
      return (
        <div className="panel-visual panel-visual--bar">
          <span style={{ height: '45%' }} />
          <span style={{ height: '72%' }} />
          <span style={{ height: '58%' }} />
          <span style={{ height: '84%' }} />
        </div>
      )
    case 'pie':
      return (
        <div className="panel-visual panel-visual--pie">
          <div className="panel-pie" />
        </div>
      )
    case 'timeline':
      return (
        <div className="panel-visual panel-visual--timeline">
          <div />
          <div />
          <div />
          <div />
        </div>
      )
    case 'report':
      return (
        <div className="panel-visual panel-visual--report">
          <span />
          <span />
          <span />
        </div>
      )
    case 'chat':
      return (
        <div className="panel-visual panel-visual--chat">
          <p>Field stress detected in south-east zone.</p>
          <p>Recommend irrigation in 12-18 hours.</p>
        </div>
      )
    case 'controls':
      return (
        <div className="panel-visual panel-visual--controls">
          <button type="button">Primary</button>
          <button type="button">Secondary</button>
          <div className="panel-slider-track">
            <span />
          </div>
        </div>
      )
    case 'heatmap':
      return (
        <div className="panel-visual panel-visual--heatmap">
          <span />
          <span />
          <span />
          <span />
          <span />
          <span />
        </div>
      )
    case 'log':
    default:
      return (
        <div className="panel-visual panel-visual--log">
          <p>08:45 — Rainfall threshold crossed</p>
          <p>09:10 — Yield model refreshed</p>
          <p>09:32 — AI advisory queued</p>
        </div>
      )
  }
}

const PanelModulePage = () => {
  const { panelSlug } = useParams()

  if (!panelSlug || !isPanelRoute(panelSlug)) {
    return <Navigate to={`/panel/${defaultPanelRoute}`} replace />
  }

  const activeItem = panelItemsByRoute[panelSlug]

  return (
    <section className="panel-main">
      <header className="panel-main__topbar">
        <div className="panel-main__tabs">
          <button type="button" className="panel-tab panel-tab--active">
            Guides
          </button>
          <button type="button" className="panel-tab">
            API Reference
          </button>
          <button type="button" className="panel-tab">
            Changelog
          </button>
        </div>

        <div className="panel-main__actions">
          <label className="panel-search" htmlFor="panel-search-input">
            <Search size={16} aria-hidden="true" />
            <input id="panel-search-input" type="search" placeholder="Search or ask" />
          </label>
          <button type="button" className="panel-ask-btn">
            <Bot size={16} aria-hidden="true" />
            Ask AI
          </button>
        </div>
      </header>

      <div className="panel-main__body">
        <section className="panel-content">
          <p className="panel-content__kicker">Control Console</p>
          <h1>{activeItem.label}</h1>
          <p className="panel-content__summary">{activeItem.subtitle}</p>

          {activeItem.route === 'my-farm' ? (
            <MyFarmWorkspace item={activeItem} />
          ) : (
            <div className="panel-cards">
              {activeItem.blocks.map((block) => (
                <article key={block.id} id={block.id} className="panel-card">
                  <div className="panel-card__head">
                    <h3>{block.title}</h3>
                    {block.metric ? <span className="panel-card__metric">{block.metric}</span> : null}
                  </div>
                  <p>{block.description}</p>
                  {renderVisual(block.visual, block.metric)}
                </article>
              ))}
            </div>
          )}
        </section>

        <aside className="panel-right" aria-label="Secondary tools">
          <button type="button" className="panel-right__ask-card">
            <Bot size={16} aria-hidden="true" />
            Ask AI
            <span>Get contextual help for this module</span>
          </button>

          <div className="panel-right__toc">
            <p>On this page</p>
            <ul>
              {activeItem.blocks.map((block) => (
                <li key={`toc-${block.id}`}>
                  <a href={`#${block.id}`}>{block.title}</a>
                </li>
              ))}
            </ul>
          </div>
        </aside>
      </div>
    </section>
  )
}

export default PanelModulePage
