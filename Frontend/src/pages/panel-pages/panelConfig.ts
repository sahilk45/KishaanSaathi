import {
  BookOpen,
  Bot,
  CloudSun,
  Landmark,
  LayoutDashboard,
  Leaf,
  LineChart,
  MapPinned,
  RefreshCw,
  Settings,
  type LucideIcon,
} from 'lucide-react'

export type PanelItemId =
  | 'overview'
  | 'myFarm'
  | 'quickGuide'
  | 'cropHealth'
  | 'weatherAlerts'
  | 'marketInsights'
  | 'loanEligibility'
  | 'whatIfSimulator'
  | 'aiAssistant'
  | 'settings'

export type PanelRouteSlug =
  | 'overview'
  | 'my-farm'
  | 'quick-guide'
  | 'crop-health'
  | 'weather-alerts'
  | 'market-insights'
  | 'loan-eligibility'
  | 'what-if-simulator'
  | 'ai-assistant'
  | 'settings'

export type VisualKind =
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

export type PanelBlock = {
  id: string
  title: string
  description: string
  visual: VisualKind
  metric?: string
}

export type PanelItem = {
  id: PanelItemId
  route: PanelRouteSlug
  label: string
  icon: LucideIcon
  subtitle: string
  blocks: PanelBlock[]
}

export const defaultPanelRoute: PanelRouteSlug = 'overview'

export const panelGroups: PanelItemId[][] = [
  ['overview', 'myFarm', 'quickGuide'],
  ['cropHealth', 'weatherAlerts', 'marketInsights'],
  ['loanEligibility', 'whatIfSimulator', 'aiAssistant', 'settings'],
]

export const panelItems: Record<PanelItemId, PanelItem> = {
  overview: {
    id: 'overview',
    route: 'overview',
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
    route: 'my-farm',
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
    route: 'quick-guide',
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
    route: 'crop-health',
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
    route: 'weather-alerts',
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

  marketInsights: {
    id: 'marketInsights',
    route: 'market-insights',
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

  loanEligibility: {
    id: 'loanEligibility',
    route: 'loan-eligibility',
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
    route: 'what-if-simulator',
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
    route: 'ai-assistant',
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
  settings: {
    id: 'settings',
    route: 'settings',
    label: 'Settings',
    icon: Settings,
    subtitle: 'Account information, language preferences, and workspace configuration.',
    blocks: [
      {
        id: 'account-info',
        title: 'Account Information',
        description: 'Your registered farmer profile details.',
        visual: 'report',
      },
      {
        id: 'language-choice',
        title: 'Language',
        description: 'Switch between English, Hindi, and Punjabi.',
        visual: 'controls',
      },
    ],
  },
}

export const panelItemsByRoute = Object.values(panelItems).reduce<Record<PanelRouteSlug, PanelItem>>(
  (acc, item) => {
    acc[item.route] = item
    return acc
  },
  {} as Record<PanelRouteSlug, PanelItem>,
)

export const isPanelRoute = (value: string): value is PanelRouteSlug =>
  Object.prototype.hasOwnProperty.call(panelItemsByRoute, value)
