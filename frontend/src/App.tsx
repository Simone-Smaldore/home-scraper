import { BrowserRouter, Route, Routes } from 'react-router'

import { SystemStatus } from './features/debug/SystemStatus'

export function App() {
  return (
    <BrowserRouter>
      <Routes>
        {/* Unlisted: the page exists to explain outages. */}
        <Route path="/_stato" element={<SystemStatus />} />
        <Route path="*" element={<Placeholder />} />
      </Routes>
    </BrowserRouter>
  )
}

/** Stands in for the dashboard until M4 brings the design. */
function Placeholder() {
  return (
    <div className="min-h-full bg-bg-app px-5 py-8">
      <div className="mx-auto w-full max-w-[520px] rounded-card border border-border-subtle bg-surface-card p-5">
        <h1 className="text-lg font-bold">Casa Radar</h1>
        <p className="mt-1 text-sm text-text-secondary">
          La dashboard arriva con M4. Lo stato del sistema è su /_stato.
        </p>
      </div>
    </div>
  )
}
