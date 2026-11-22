import { useEffect, useState } from 'react'
import { getHealth } from './api.ts'
import { SetupPage } from './setup/SetupPage.tsx'
import type { AgentRequest } from './types.ts'
import './App.css'

type BackendStatus = 'checking' | 'up' | 'down'

function toggleTheme() {
  const root = document.documentElement
  const dark = root.dataset.theme ? root.dataset.theme === 'dark' : matchMedia('(prefers-color-scheme: dark)').matches
  root.dataset.theme = dark ? 'light' : 'dark'
  try {
    localStorage.setItem('dp-theme', root.dataset.theme)
  } catch {
    // Private windows and blocked storage: the theme just does not persist.
  }
}

try {
  const saved = localStorage.getItem('dp-theme')
  if (saved) document.documentElement.dataset.theme = saved
} catch {
  // Storage is not available; keep the system theme.
}

function App() {
  const [backend, setBackend] = useState<BackendStatus>('checking')
  // Until the Planner page exists, a submitted setup shows the request it would send to the backend.
  const [request, setRequest] = useState<AgentRequest | null>(null)

  useEffect(() => {
    let cancelled = false
    getHealth()
      .then(() => !cancelled && setBackend('up'))
      .catch(() => !cancelled && setBackend('down'))
    return () => {
      cancelled = true
    }
  }, [])

  return (
    <>
      <header className="top">
        <div className="brand">
          <div className="logo" aria-hidden="true">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M3 20l6-14 4 8 3-5 5 11z" />
            </svg>
          </div>
          <div>
            <h1>Degree Planner</h1>
            <small>Colorado School of Mines</small>
          </div>
        </div>
        <p className={`status status-${backend}`} data-testid="backend-status">
          Backend: {backend === 'checking' ? 'checking...' : backend === 'up' ? 'connected' : 'not running'}
        </p>
        <button className="icon-btn" type="button" aria-label="Toggle dark mode" onClick={toggleTheme}>
          <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M21 12.8A9 9 0 1111.2 3a7 7 0 009.8 9.8z" />
          </svg>
        </button>
      </header>

      {request ? (
        <main className="stub">
          <h2>Setup received</h2>
          <p>The Planner page is the next task. This is the request the setup page will send to the backend:</p>
          <pre data-testid="request-json">{JSON.stringify(request, null, 2)}</pre>
          <button type="button" className="btn" onClick={() => setRequest(null)}>
            Back to setup
          </button>
        </main>
      ) : (
        <SetupPage onSubmit={setRequest} />
      )}
    </>
  )
}

export default App
