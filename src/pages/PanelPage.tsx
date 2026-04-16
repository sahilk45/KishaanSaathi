import {
  BookOpen,
  Bot,
  CloudSun,
  Clock3,
  Landmark,
  Languages,
  LayoutDashboard,
  Leaf,
  LineChart,
  MapPinned,
  RefreshCw,
  Search,
  Settings,
  ShieldAlert,
  type LucideIcon,
} from 'lucide-react'
import { useState } from 'react'
import { useLanguage } from '../context/LanguageContext'

type PanelItemId =
  | 'overview'
  | 'myFarm'
  | 'quickGuide'
  | 'cropHealth'
  | 'weatherAlerts'
  | 'riskAnalysis'
  | 'marketInsights'
  | 'cropTimeline'
  | 'loanEligibility'
  | 'whatIfSimulator'
  | 'aiAssistant'
  | 'language'
  | 'settings'

type VisualKind =
  | 'kpi'
  | 'map'
  | 'line'
  | 'bar'
  | 'pie'
  | 'timeline'
  | 'report'
  | 'chat'
  | 'controls'
  | 'log'
  | 'heatmap'

type PanelBlock = {
  id: string
  title: string
  description: string
  visual: VisualKind
  metric?: string
}

type PanelItem = {
  id: PanelItemId
  label: string
  icon: LucideIcon
  subtitle: string
  blocks: PanelBlock[]
}

const panelGroups: PanelItemId[][] = [
  ['overview', 'myFarm', 'quickGuide'],
  ['cropHealth', 'weatherAlerts', 'riskAnalysis', 'marketInsights', 'cropTimeline'],
  ['loanEligibility', 'whatIfSimulator', 'aiAssistant', 'language', 'settings'],
]

const panelItems: Record<PanelItemId, PanelItem> = {
  overview: {
    id: 'overview',
    label: 'Overview',
    icon: LayoutDashboard,
    subtitle: 'Health score, weather signals, active alerts, and AI intelligence in one live snapshot.',
    blocks: [
      {
        id: 'health-score',
        title: 'Health Score',
        description: 'Composite crop vitality score based on NDVI, moisture, and historical field trend.',
        visual: 'kpi',
        metric: '78 / 100',
      },
      {
        id: 'weather-snapshot',
        title: 'Weather Snapshot',
        description: 'Short-term rainfall and temperature movement tuned to your saved farm coordinates.',
        visual: 'line',
      },
      {
        id: 'active-alerts',
        title: 'Active Alerts',
        description: 'Prioritized alerts queue for drought risk, heavy rain, and pest pressure.',
        visual: 'log',
      },
      {
        id: 'ai-insight',
        title: 'AI Insight',
        description: 'Contextual recommendation generated from farm status, weather pattern, and market signal.',
        visual: 'chat',
      },
    ],
  },
  myFarm: {
    id: 'myFarm',
    label: 'My Farm',
    icon: MapPinned,
    subtitle: 'Map workspace with boundary drawing, polygon editing, and NDVI overlay controls.',
    blocks: [
      {
        id: 'mapbox-canvas',
        title: 'Mapbox Canvas',
        description: 'Full map workspace for location pinning and live field inspection.',
        visual: 'map',
      },
      {
        id: 'polygon-tools',
        title: 'Polygon Drawing Tools',
        description: 'Boundary creation, edit handles, and area validation controls.',
        visual: 'controls',
      },
      {
        id: 'ndvi-overlay',
        title: 'NDVI Overlay',
        description: 'Layered vegetation heat visualization to isolate low-health patches.',
        visual: 'heatmap',
      },
    ],
  },
  quickGuide: {
    id: 'quickGuide',
    label: 'Quick Guide',
    icon: BookOpen,
    subtitle: 'Fast onboarding workflow to get farm tracking, alerts, and insights configured quickly.',
    blocks: [
      {
        id: 'setup-checklist',
        title: 'Setup Checklist',
        description: 'Essential setup milestones to activate field monitoring with minimal effort.',
        visual: 'log',
      },
      {
        id: 'first-scan-flow',
        title: 'First Scan Workflow',
        description: 'Recommended sequence for mapping, health scan, and alert calibration.',
        visual: 'timeline',
      },
    ],
  },
  cropHealth: {
    id: 'cropHealth',
    label: 'Crop Health',
    icon: Leaf,
    subtitle: 'NDVI mapping, health scoring, and trend interpretation for early intervention planning.',
    blocks: [
      {
        id: 'ndvi-map',
        title: 'NDVI Map',
        description: 'Vegetation index layer highlighting healthy and stressed zones in your field.',
        visual: 'map',
      },
      {
        id: 'health-score-breakdown',
        title: 'Health Score',
        description: 'Zone-wise and whole-farm score distribution with confidence levels.',
        visual: 'kpi',
        metric: 'High confidence',
      },
      {
        id: 'health-trend',
        title: 'Trend Graph',
        description: 'Week-over-week crop health trajectory for detection of yield-impacting decline.',
        visual: 'line',
      },
    ],
  },
  weatherAlerts: {
    id: 'weatherAlerts',
    label: 'Weather & Alerts',
    icon: CloudSun,
    subtitle: 'Localized forecast, severe condition detection, and event history for operational timing.',
    blocks: [
      {
        id: 'forecast',
        title: '7-Day Forecast',
        description: 'Rainfall, temperature, and humidity outlook tied to farm coordinates.',
        visual: 'line',
      },
      {
        id: 'alerts-log',
        title: 'Alerts Log',
        description: 'Chronological alert history with trigger reason and impact level.',
        visual: 'log',
      },
    ],
  },
  riskAnalysis: {
    id: 'riskAnalysis',
    label: 'Risk Analysis',
    icon: ShieldAlert,
    subtitle: 'Risk scoring engine with severity heat patterns and actionable mitigation direction.',
    blocks: [
      {
        id: 'risk-scores',
        title: 'Risk Scores',
        description: 'Drought, flood, pest, and disease probability with weighted confidence.',
        visual: 'bar',
      },
      {
        id: 'risk-heatmaps',
        title: 'Heatmaps',
        description: 'Spatial risk intensity map to prioritize high-exposure farm zones.',
        visual: 'heatmap',
      },
    ],
  },
  marketInsights: {
    id: 'marketInsights',
    label: 'Market Insights',
    icon: LineChart,
    subtitle: 'Mandi movement analysis with multi-chart comparison for smarter selling decisions.',
    blocks: [
      {
        id: 'price-line',
        title: 'Price Trend Line',
        description: 'Daily and weekly price trajectory for selected crop-market pair.',
        visual: 'line',
      },
      {
        id: 'yield-comparison',
        title: 'Yield Scenario Bars',
        description: 'Best, expected, and conservative output comparisons for planning.',
        visual: 'bar',
      },
      {
        id: 'revenue-distribution',
        title: 'Revenue Mix Pie',
        description: 'Share of projected returns by crop strategy and market timing.',
        visual: 'pie',
      },
    ],
  },
  cropTimeline: {
    id: 'cropTimeline',
    label: 'Crop Timeline',
    icon: Clock3,
    subtitle: 'Growth-stage timeline with upcoming milestones and operation reminders.',
    blocks: [
      {
        id: 'growth-stages',
        title: 'Growth Stage Timeline',
        description: 'From sowing to harvest with stage completion and due tasks.',
        visual: 'timeline',
      },
      {
        id: 'stage-logs',
        title: 'Milestone Log',
        description: 'Executed operations, pending tasks, and agronomy notes by stage.',
        visual: 'log',
      },
    ],
  },
  loanEligibility: {
    id: 'loanEligibility',
    label: 'Loan Eligibility',
    icon: Landmark,
    subtitle: 'Bank-style assessment with score factors, risk adjustments, and lending-ready report.',
    blocks: [
      {
        id: 'loan-score',
        title: 'Eligibility Score',
        description: 'Score based on crop health, land profile, and projected yield reliability.',
        visual: 'kpi',
        metric: 'Loan-ready',
      },
      {
        id: 'bank-report',
        title: 'Bank-style Report',
        description: 'Structured summary compatible with cooperative and local banking workflows.',
        visual: 'report',
      },
    ],
  },
  whatIfSimulator: {
    id: 'whatIfSimulator',
    label: 'What-If Simulator',
    icon: RefreshCw,
    subtitle: 'Scenario simulation for crop and irrigation strategy with live projected outputs.',
    blocks: [
      {
        id: 'scenario-controls',
        title: 'Crop + Slider Controls',
        description: 'Adjust crop type, irrigation, and input assumptions interactively.',
        visual: 'controls',
      },
      {
        id: 'live-output',
        title: 'Live Output Model',
        description: 'Real-time updates for yield, profitability, and risk exposure.',
        visual: 'bar',
      },
    ],
  },
  aiAssistant: {
    id: 'aiAssistant',
    label: 'AI Assistant',
    icon: Bot,
    subtitle: 'Conversational assistant with full farm context, recent signals, and recommendation memory.',
    blocks: [
      {
        id: 'farm-context-chat',
        title: 'Contextual Chat',
        description: 'Natural-language assistant aware of field health, weather, and market movement.',
        visual: 'chat',
      },
      {
        id: 'recommended-actions',
        title: 'Suggested Actions',
        description: 'Prioritized recommendations generated from your latest farm signals.',
        visual: 'log',
      },
    ],
  },
  language: {
    id: 'language',
    label: 'Language',
    icon: Languages,
    subtitle: 'Language preferences and terminology profile for localized advisory delivery.',
    blocks: [
      {
        id: 'language-choice',
        title: 'Language Selection',
        description: 'Switch between English, Hindi, and Punjabi for dashboard content.',
        visual: 'controls',
      },
      {
        id: 'terminology-profile',
        title: 'Terminology Profile',
        description: 'Choose simplified or technical wording style for recommendations.',
        visual: 'log',
      },
    ],
  },
  settings: {
    id: 'settings',
    label: 'Settings',
    icon: Settings,
    subtitle: 'Control notifications, preferences, and operational defaults for your workspace.',
    blocks: [
      {
        id: 'notification-settings',
        title: 'Notifications',
        description: 'Configure alert channels, frequency, and severity thresholds.',
        visual: 'controls',
      },
      {
        id: 'account-preferences',
        title: 'Account & Preferences',
        description: 'Manage profile defaults, region setup, and workspace policy options.',
        visual: 'report',
      },
    ],
  },
}

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

const PanelPage = () => {
  const { content } = useLanguage()
  const [activeItemId, setActiveItemId] = useState<PanelItemId>('overview')
  const activeItem = panelItems[activeItemId]

  return (
    <main className="panel-page" aria-label="Farm control panel">
      <div className="panel-layout">
        <aside className="panel-sidebar">
          <div className="panel-brand">
            <span className="panel-brand__logo" aria-hidden="true">
              <Leaf size={18} />
            </span>
            <div>
              <p className="panel-brand__title">{content.navbar.brandName}</p>
              <p className="panel-brand__subtitle">Farm Intelligence Panel</p>
            </div>
          </div>

          <nav className="panel-nav" aria-label="Panel modules">
            {panelGroups.map((group, groupIndex) => (
              <div className="panel-nav__group" key={`group-${groupIndex}`}>
                {group.map((itemId) => {
                  const item = panelItems[itemId]
                  const Icon = item.icon
                  const isActive = activeItemId === item.id

                  return (
                    <button
                      key={item.id}
                      type="button"
                      className={`panel-nav__item${isActive ? ' panel-nav__item--active' : ''}`}
                      onClick={() => setActiveItemId(item.id)}
                    >
                      <Icon size={16} aria-hidden="true" />
                      <span>{item.label}</span>
                    </button>
                  )
                })}

                {groupIndex < panelGroups.length - 1 ? (
                  <div className="panel-nav__divider" role="separator" aria-hidden="true" />
                ) : null}
              </div>
            ))}
          </nav>
        </aside>

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
      </div>
    </main>
  )
}

export default PanelPage