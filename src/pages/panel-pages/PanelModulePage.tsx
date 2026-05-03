import { Bot, MapPinned, Search } from 'lucide-react'
import { Navigate, useNavigate, useParams } from 'react-router-dom'
import { defaultPanelRoute, isPanelRoute, panelItemsByRoute } from './panelConfig'
import MyFarmWorkspace from './MyFarmWorkspace'
import OverviewPanel from './modules/OverviewPanel'
import CropHealthPanel from './modules/CropHealthPanel'
import WeatherAlertsPanel from './modules/WeatherAlertsPanel'
import MarketInsightsPanel from './modules/MarketInsightsPanel'
import LoanEligibilityPanel from './modules/LoanEligibilityPanel'
import WhatIfSimulatorPanel from './modules/WhatIfSimulatorPanel'
import AiAssistantPanel from './modules/AiAssistantPanel'
import { useFields } from '../../context/FieldContext'
import { useSession } from '../../context/SessionContext'

const PanelModulePage = () => {
  const { panelSlug } = useParams()
  const navigate = useNavigate()
  const { fields, selectedField, loading: fieldsLoading, selectField } = useFields()
  const { fieldId } = useSession()

  if (!panelSlug || !isPanelRoute(panelSlug)) {
    return <Navigate to={`/panel/${defaultPanelRoute}`} replace />
  }

  const activeItem = panelItemsByRoute[panelSlug]

  const renderPanelContent = () => {
    switch (activeItem.route) {
      case 'overview':
        return <OverviewPanel />
      case 'my-farm':
        return <MyFarmWorkspace item={activeItem} />
      case 'crop-health':
        return <CropHealthPanel />
      case 'weather-alerts':
        return <WeatherAlertsPanel />
      case 'market-insights':
        return <MarketInsightsPanel />
      case 'loan-eligibility':
        return <LoanEligibilityPanel />
      case 'what-if-simulator':
        return <WhatIfSimulatorPanel />
      case 'ai-assistant':
        return <AiAssistantPanel />
      default:
        return null
    }
  }

  const handleAskAi = () => {
    navigate('/panel/ai-assistant')
  }

  return (
    <section className="panel-main">
      <header className="panel-main__topbar">
        <div className="panel-main__tabs">
          <span style={{ fontWeight: 600, color: 'var(--text-main)', fontSize: '1.1rem' }}>Farm Intelligence Panel</span>
        </div>

        <div className="panel-main__actions">
          <label className="panel-search" htmlFor="panel-search-input">
            <Search size={16} aria-hidden="true" />
            <input id="panel-search-input" type="search" placeholder="Search or ask" />
          </label>
          <button type="button" className="panel-ask-btn" onClick={handleAskAi}>
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

          {renderPanelContent()}
        </section>

        <aside className="panel-right" aria-label="Secondary tools">
          {/* ── Field selector ──────────────────────────── */}
          <div className="panel-right__field-selector">
            <div className="panel-right__field-header">
              <MapPinned size={14} aria-hidden="true" />
              <p>Active Field</p>
            </div>

            {fieldsLoading ? (
              <div className="panel-skeleton" style={{ height: 32 }} />
            ) : fields.length === 0 ? (
              <p className="panel-right__field-empty">
                No fields registered.{' '}
                <button type="button" className="panel-inline-link" onClick={() => navigate('/panel/my-farm')}>
                  Register a field
                </button>
              </p>
            ) : (
              <>
                <select
                  className="panel-right__field-select"
                  value={fieldId}
                  onChange={(e) => selectField(e.target.value)}
                >
                  {fields.map((f) => (
                    <option key={f.field_id} value={f.field_id}>
                      {f.field_name} — {f.city_name || 'Unknown'}
                    </option>
                  ))}
                </select>

                {selectedField ? (
                  <div className="panel-right__field-info">
                    <div className="panel-right__field-row">
                      <span>City</span>
                      <strong>{selectedField.city_name || 'N/A'}</strong>
                    </div>
                    <div className="panel-right__field-row">
                      <span>State</span>
                      <strong>{selectedField.state_name || 'N/A'}</strong>
                    </div>
                    <div className="panel-right__field-row">
                      <span>Area</span>
                      <strong>{selectedField.area_hectares ? `${selectedField.area_hectares} ha` : 'N/A'}</strong>
                    </div>
                  </div>
                ) : null}
              </>
            )}
          </div>

          {/* ── On this page ────────────────────────────── */}
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
