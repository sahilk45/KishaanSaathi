import { Link } from 'react-router-dom'

const MarketInsightsPanel = () => {
  return (
    <div className="panel-cards">
      <article className="panel-card">
        <div className="panel-card__head">
          <h3>Market Insights</h3>
          <span className="panel-card__metric">Coming soon</span>
        </div>
        <p>APMC price proxy endpoint is not yet exposed by the backend.</p>
        <Link to="/apmc" className="panel-inline-callout__link">Open APMC Explorer</Link>
      </article>
    </div>
  )
}

export default MarketInsightsPanel
