import { useEffect, useState } from 'react'
import { getHealth } from './api.ts'
import './App.css'

type BackendStatus = 'checking' | 'up' | 'down'

function App() {
  const [backend, setBackend] = useState<BackendStatus>('checking')

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
    <main className="app">
      <h1>Degree Planner</h1>
      <p>Colorado School of Mines</p>
      <p className={`status status-${backend}`} data-testid="backend-status">
        Backend: {backend === 'checking' ? 'checking...' : backend === 'up' ? 'connected' : 'not running'}
      </p>
      {/* Setup page and planner page go here (see plans/FRONTEND-PLAN.md). */}
    </main>
  )
}

export default App
