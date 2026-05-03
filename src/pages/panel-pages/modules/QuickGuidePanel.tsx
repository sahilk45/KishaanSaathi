import {
  UserPlus, MapPin, Leaf, ShoppingCart, BrainCircuit,
  FileText, CloudRain, Sliders, CreditCard, Settings,
} from 'lucide-react'
import { useLanguage } from '../../../context/LanguageContext'

const steps = [
  {
    key: 'step1',
    Icon: UserPlus,
    titleKey: 'step1Title',
    defaultTitle: 'Register Your Farmer Profile',
    defaultDesc: 'Go to My Farm → Farmer Profile. Enter your full name, phone number, state, and district. Click "Create farmer profile" to save your account in the database.',
  },
  {
    key: 'step2',
    Icon: MapPin,
    titleKey: 'step2Title',
    defaultTitle: 'Draw Your Farm Boundary',
    defaultDesc: 'In My Farm → Mapbox Canvas, click "Track current location" to jump to your land. Use the polygon drawing tool on the map to trace your field boundary, then click "Save boundary" to persist it.',
  },
  {
    key: 'step3',
    Icon: Leaf,
    titleKey: 'step3Title',
    defaultTitle: 'Run Your First Crop Health Prediction',
    defaultDesc: 'Navigate to Crop Health. Select your crop type (Kharif/Rabi), enter NPK and irrigation values, choose the year, and click "Predict & Save". Your health score, yield estimate, and loan decision are computed by our AI model and saved to the database.',
  },
  {
    key: 'step4',
    Icon: CloudRain,
    titleKey: 'step4Title',
    defaultTitle: 'Monitor Weather & Alerts',
    defaultDesc: 'Visit Weather & Alerts to see live temperature, humidity, soil moisture, and cloud cover from the latest satellite snapshot. Auto-generated alerts flag high cloud cover, heat stress, or low soil moisture for immediate action.',
  },
  {
    key: 'step5',
    Icon: ShoppingCart,
    titleKey: 'step5Title',
    defaultTitle: 'Check Mandi Market Prices',
    defaultDesc: 'Go to Market Insights. Your state and district are auto-filled. Select a crop commodity and click "Fetch APMC Prices" to see min, modal, and max prices across nearby mandis, along with a comparison chart.',
  },
  {
    key: 'step6',
    Icon: Sliders,
    titleKey: 'step6Title',
    defaultTitle: 'Simulate "What If" Scenarios',
    defaultDesc: 'Open the What-If Simulator and adjust crop type, NPK input, irrigation ratio, and year freely. Unlike Crop Health, these simulations are not saved to the database — they are for exploring scenarios before committing to a real prediction.',
  },
  {
    key: 'step7',
    Icon: CreditCard,
    titleKey: 'step7Title',
    defaultTitle: 'Apply for Loan Eligibility',
    defaultDesc: 'In Loan Eligibility, your latest crop health prediction is automatically loaded as read-only inputs. Enter your desired loan amount and click Submit. The AI assesses your farm score and gives an instant Approved / Review / Declined decision with a downloadable certificate.',
  },
  {
    key: 'step8',
    Icon: BrainCircuit,
    titleKey: 'step8Title',
    defaultTitle: 'Ask the AI Assistant',
    defaultDesc: 'Use the AI Assistant to ask anything about your farm — "What is my health score?", "Which crop is best this season?", "What is the wheat price in my district?". The assistant has full context of your field and past predictions.',
  },
  {
    key: 'step9',
    Icon: FileText,
    titleKey: 'step9Title',
    defaultTitle: 'View Your Dashboard Overview',
    defaultDesc: 'The Overview section gives you a live snapshot: health score with risk level, current weather, active alerts, and AI insights — all on one page. Each block is expandable. Check this daily for a quick farm status read.',
  },
  {
    key: 'step10',
    Icon: Settings,
    titleKey: 'step10Title',
    defaultTitle: 'Manage Settings',
    defaultDesc: 'In Settings, you can see your full farmer profile (name, phone, email, district) synced from the database. Switch the dashboard language between English, Hindi, and Punjabi at any time.',
  },
]

const QuickGuidePanel = () => {
  const { panel } = useLanguage()
  const p = panel.panel.quickGuide

  return (
    <div className="panel-cards panel-cards--stacked">
      <article className="panel-card" style={{ padding: '24px 24px 28px' }}>
        <div className="panel-card__head" style={{ marginBottom: 6 }}>
          <h3 style={{ fontSize: '1.1rem' }}>{p.title}</h3>
          <span className="panel-card__metric">{steps.length} Steps</span>
        </div>
        <p style={{ marginBottom: 24 }}>{p.subtitle}</p>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 0 }}>
          {steps.map(({ key, Icon, titleKey, defaultTitle, defaultDesc }, i) => (
            <div key={key} style={{ display: 'flex', gap: 16, paddingBottom: i < steps.length - 1 ? 20 : 0, marginBottom: i < steps.length - 1 ? 20 : 0, borderBottom: i < steps.length - 1 ? '1px solid var(--border-light)' : 'none' }}>
              {/* Step number + connector */}
              <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', flexShrink: 0 }}>
                <div style={{ width: 36, height: 36, borderRadius: '50%', background: '#f0fdf4', border: '2px solid #bbf7d0', color: '#16a34a', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <Icon size={16} />
                </div>
                {i < steps.length - 1 && <div style={{ width: 2, flex: 1, background: '#e5f0e8', marginTop: 6 }} />}
              </div>

              {/* Content */}
              <div style={{ flex: 1, paddingTop: 4 }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 5 }}>
                  <span style={{ fontSize: '0.7rem', fontWeight: 700, background: '#dcfce7', color: '#15803d', borderRadius: 99, padding: '2px 8px' }}>Step {i + 1}</span>
                  <strong style={{ fontSize: '0.92rem', color: 'var(--text-main)' }}>
                    {(p as Record<string, string>)[titleKey] ?? defaultTitle}
                  </strong>
                </div>
                <p style={{ fontSize: '0.84rem', color: 'var(--text-muted)', lineHeight: 1.65, margin: 0 }}>
                  {(p as Record<string, string>)[key] ?? defaultDesc}
                </p>
              </div>
            </div>
          ))}
        </div>
      </article>
    </div>
  )
}

export default QuickGuidePanel
