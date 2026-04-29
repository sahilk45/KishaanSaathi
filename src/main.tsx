import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import './index.css'
import { LanguageProvider } from './context/LanguageContext'
import HomePage from './pages/HomePage'
import ApmcPage from './pages/ApmcPage'
import PanelLayoutPage from './pages/panel-pages/PanelLayoutPage'
import PanelModulePage from './pages/panel-pages/PanelModulePage'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <LanguageProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/apmc" element={<ApmcPage />} />
          <Route path="/panel" element={<PanelLayoutPage />}>
            <Route index element={<Navigate to="overview" replace />} />
            <Route path=":panelSlug" element={<PanelModulePage />} />
          </Route>
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </LanguageProvider>
  </StrictMode>,
)
