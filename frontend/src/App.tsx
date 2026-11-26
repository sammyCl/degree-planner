import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError, getHealth, submitSetup } from './api.ts'
import { BuildingScreen } from './building/BuildingScreen.tsx'
import { ProblemScreen } from './building/ProblemScreen.tsx'
import { PlannerPage } from './planner/PlannerPage.tsx'
import { SetupPage } from './setup/SetupPage.tsx'
import type { SetupForm } from './setup/validate.ts'
import type { AgentRequest, AgentResponse } from './types.ts'
import './App.css'

type BackendStatus = 'checking' | 'up' | 'down'

type Screen =
  | { name: 'setup' }
  | { name: 'building'; request: AgentRequest }
  | { name: 'planner'; response: AgentResponse }
  | { name: 'problem'; request: AgentRequest; title: string; message: string; problems: string[]; canRetry: boolean }

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

/** The words shown to the student for each way the call can fail. */
function describeError(error: unknown): { title: string; message: string; canRetry: boolean } {
  if (error instanceof ApiError) {
    switch (error.kind) {
      case 'network':
        return { title: 'Cannot reach the backend', message: error.message, canRetry: true }
      case 'agent_unavailable':
        return {
          title: 'The planning assistant is not available',
          message: `The backend could not start the assistant, so no plan was built. ${error.message}`,
          canRetry: true,
        }
      case 'invalid_request':
        return { title: 'The backend did not accept this setup', message: error.message, canRetry: false }
      default:
        return { title: 'Something went wrong on the backend', message: error.message, canRetry: true }
    }
  }
  return { title: 'Something went wrong', message: 'An unexpected error stopped the plan from being built.', canRetry: true }
}

function App() {
  const [backend, setBackend] = useState<BackendStatus>('checking')
  const [screen, setScreen] = useState<Screen>({ name: 'setup' })
  // What the student chose, kept so that coming back from the planner or an error does not lose it.
  const [form, setForm] = useState<SetupForm | undefined>()
  // Each submit gets a number; a late answer to an older submit is ignored.
  const run = useRef(0)
  const controller = useRef<AbortController | null>(null)

  useEffect(() => {
    let cancelled = false
    getHealth()
      .then(() => !cancelled && setBackend('up'))
      .catch(() => !cancelled && setBackend('down'))
    return () => {
      cancelled = true
    }
  }, [])

  const build = useCallback((request: AgentRequest) => {
    const mine = ++run.current
    controller.current?.abort()
    const abort = new AbortController()
    controller.current = abort
    setScreen({ name: 'building', request })
    submitSetup(request, abort.signal)
      .then((response) => {
        if (run.current !== mine) return
        if (response.plan === null) {
          setScreen({
            name: 'problem',
            request,
            title: 'The assistant could not build a plan',
            message: response.explanation,
            problems: response.problems,
            canRetry: true,
          })
        } else {
          setScreen({ name: 'planner', response })
        }
      })
      .catch((error) => {
        if (run.current !== mine || (error instanceof ApiError && error.kind === 'aborted')) return
        setScreen({ name: 'problem', request, problems: [], ...describeError(error) })
      })
  }, [])

  const cancel = () => {
    run.current++ // anything still in flight is now stale
    controller.current?.abort()
    setScreen({ name: 'setup' })
  }

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

      {screen.name === 'setup' && (
        <SetupPage
          initial={form}
          onSubmit={(request, submitted) => {
            setForm(submitted)
            build(request)
          }}
        />
      )}
      {screen.name === 'building' && <BuildingScreen request={screen.request} onCancel={cancel} />}
      {screen.name === 'planner' && (
        <PlannerPage
          plan={screen.response.plan!}
          explanation={screen.response.explanation}
          choices={screen.response.choices}
          checks={screen.response.checks}
          problems={screen.response.status === 'cannot_work' ? screen.response.problems : []}
          onBack={() => setScreen({ name: 'setup' })}
        />
      )}
      {screen.name === 'problem' && (
        <ProblemScreen
          title={screen.title}
          message={screen.message}
          problems={screen.problems}
          onRetry={screen.canRetry ? () => build(screen.request) : undefined}
          onBack={() => setScreen({ name: 'setup' })}
        />
      )}
    </>
  )
}

export default App
