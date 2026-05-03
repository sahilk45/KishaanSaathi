import { Navigate, NavLink, Outlet } from 'react-router-dom'
import { useLanguage } from '../../context/LanguageContext'
import { panelGroups, panelItems } from './panelConfig'

const FARMER_ID_STORAGE_KEY = 'ks_farmer_id'

const PanelLayoutPage = () => {
  const { content, panel } = useLanguage()
  const p = panel.panel
  const farmerId = typeof window !== 'undefined' ? window.localStorage.getItem(FARMER_ID_STORAGE_KEY) : null

  if (!farmerId) {
    return <Navigate to="/" replace />
  }

  return (
    <main className="panel-page" aria-label="Farm control panel">
      <div className="panel-layout">
        <aside className="panel-sidebar">
          <div className="panel-brand">
            <img
              src="/KrishiMitra.png"
              alt="KishanSaathi logo"
              style={{ width: 34, height: 34, borderRadius: 8, objectFit: 'cover', flexShrink: 0 }}
            />
            <p className="panel-brand__title">{content.navbar?.brandName || 'KishanSaathi'}</p>
          </div>

          <nav className="panel-nav" aria-label="Panel modules">
            {panelGroups.map((group, groupIndex) => (
              <div className="panel-nav__group" key={`group-${groupIndex}`}>
                {group.map((itemId) => {
                  const item = panelItems[itemId]
                  const Icon = item.icon

                  return (
                    <NavLink
                      key={item.id}
                      to={`/panel/${item.route}`}
                      className={({ isActive }) =>
                        `panel-nav__item${isActive ? ' panel-nav__item--active' : ''}`
                      }
                    >
                      <Icon size={16} aria-hidden="true" />
                      <span>{p.sidebar[item.id as keyof typeof p.sidebar] || item.label}</span>
                    </NavLink>
                  )
                })}

                {groupIndex < panelGroups.length - 1 ? (
                  <div className="panel-nav__divider" role="separator" aria-hidden="true" />
                ) : null}
              </div>
            ))}
          </nav>
        </aside>

        <Outlet />
      </div>
    </main>
  )
}

export default PanelLayoutPage
