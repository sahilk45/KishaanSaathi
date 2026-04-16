import { Leaf } from 'lucide-react'
import { NavLink, Outlet } from 'react-router-dom'
import { useLanguage } from '../../context/LanguageContext'
import { panelGroups, panelItems } from './panelConfig'

const PanelLayoutPage = () => {
  const { content } = useLanguage()

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

                  return (
                    <NavLink
                      key={item.id}
                      to={`/panel/${item.route}`}
                      className={({ isActive }) =>
                        `panel-nav__item${isActive ? ' panel-nav__item--active' : ''}`
                      }
                    >
                      <Icon size={16} aria-hidden="true" />
                      <span>{item.label}</span>
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
