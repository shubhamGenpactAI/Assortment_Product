import { lazy, Suspense } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { Loader2 } from 'lucide-react'
import NavBar from './components/NavBar'
import { FilterProvider } from './context/FilterContext'

const WorkspacePage   = lazy(() => import('./pages/WorkspacePage'))
const NewSkuPage      = lazy(() => import('./pages/NewSkuPage'))
const DecisionHubPage = lazy(() => import('./pages/DecisionHubPage'))
const AgentHubPage    = lazy(() => import('./pages/AgentHubPage'))
const LoginPage       = lazy(() => import('./pages/LoginPage'))
const AssortmentDecisionPage = lazy(() => import('./pages/AssortmentDecisionPage'))

function PageLoader() {
  return (
    <div className="flex items-center justify-center h-64">
      <Loader2 size={28} className="text-[#4F46E5] animate-spin" />
    </div>
  )
}

export default function App() {
  return (
    <FilterProvider>
    <BrowserRouter>
      {/* Workspace page takes full viewport height without the standard footer */}
      <Routes>
        {/* Illustrative sign-in screen — no NavBar/footer, no real auth */}
        <Route
          path="/login"
          element={
            <Suspense fallback={<PageLoader />}>
              <LoginPage />
            </Suspense>
          }
        />
        <Route
          path="/workspace"
          element={
            <>
              <NavBar />
              <main className="pt-[96px]" style={{ height: '100vh', overflow: 'hidden' }}>
                <Suspense fallback={<PageLoader />}>
                  <WorkspacePage />
                </Suspense>
              </main>
            </>
          }
        />
        <Route
          path="*"
          element={
            <div className="min-h-screen bg-[#F4F6FA] font-sans">
              <NavBar />
              <main className="pt-[96px]">
                <Suspense fallback={<PageLoader />}>
                  <Routes>
                    <Route path="/"              element={<Navigate to="/login" replace />} />
                    <Route path="/decision-hub"  element={<DecisionHubPage />} />
                    <Route path="/new-sku"        element={<NewSkuPage />}     />
                    <Route path="/agent-hub"      element={<AgentHubPage />}   />
                    <Route path="/assortment-decisions" element={<AssortmentDecisionPage />} />
                  </Routes>
                </Suspense>
              </main>
              <footer className="text-center text-[11px] text-gray-400 py-4 mt-6 border-t border-gray-200">
                © Genpact · Retail Assortment Optimization · For internal use only
              </footer>
            </div>
          }
        />
      </Routes>
    </BrowserRouter>
    </FilterProvider>
  )
}
