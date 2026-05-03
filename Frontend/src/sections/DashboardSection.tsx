import { useLanguage } from '../context/LanguageContext'

const DashboardSection = () => {
  const { content } = useLanguage()

  return (
    <div className="dashboard">
      <div className="dashboard__card">
        <img src="/hero-aboveBG.png" alt={content.dashboard.imageAlt} />
      </div>
    </div>
  )
}

export default DashboardSection