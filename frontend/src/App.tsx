import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError, getHealth, submitSetup } from './api.ts'
import { BuildingScreen } from './building/BuildingScreen.tsx'
import { ProblemScreen } from './building/ProblemScreen.tsx'
import { ErrorBoundary } from './ErrorBoundary.tsx'
import { withoutEmptySummers } from './planner/graph.ts'
import { PlannerPage } from './planner/PlannerPage.tsx'
import { loadSession, saveSession } from './session.ts'
import { SetupPage } from './setup/SetupPage.tsx'
import type { SetupForm } from './setup/validate.ts'
import type { AgentRequest, AgentResponse } from './types.ts'
import './App.css'

type BackendStatus = 'checking' | 'up' | 'down'

type Screen =
  | { name: 'setup' }
  | { name: 'building'; request: AgentRequest }
  | { name: 'planner' }
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
        return { title: "Can't reach the server", message: error.message, canRetry: true }
      case 'agent_unavailable':
        return {
          title: 'The planning assistant is not available',
          message: `We couldn't start it, so there's no plan yet. Try again in a few minutes. Details: ${error.message}`,
          canRetry: true,
        }
      case 'invalid_request':
        return { title: 'Check your setup', message: `Go back to setup and fix this: ${error.message}`, canRetry: false }
      default:
        return { title: 'Something went wrong', message: error.message, canRetry: true }
    }
  }
  return { title: 'Something went wrong', message: 'No plan was built. Try again.', canRetry: true }
}

function App() {
  const [backend, setBackend] = useState<BackendStatus>('checking')
  const [saved] = useState(loadSession) // what was on screen before a reload
  const [screen, setScreen] = useState<Screen>(saved.screen === 'planner' ? { name: 'planner' } : { name: 'setup' })
  // What the student chose, kept so that coming back from the planner or an error does not lose it.
  const [form, setForm] = useState<SetupForm | undefined>(saved.form)
  // The latest plan, with the student's changes, kept so they can leave the planner and come back to it.
  const [response, setResponse] = useState<AgentResponse | undefined>(saved.response)
  useEffect(() => {
    saveSession({ screen: screen.name === 'planner' ? 'planner' : 'setup', form, response })
  }, [screen.name, form, response])
  // Each submit gets a number; a late answer to an older submit is ignored.
  const run = useRef(0)
  const controller = useRef<AbortController | null>(null)

  // asked again on every new screen, so the header does not keep saying "not running" after the backend is started
  useEffect(() => {
    let cancelled = false
    getHealth()
      .then(() => !cancelled && setBackend('up'))
      .catch(() => !cancelled && setBackend('down'))
    return () => {
      cancelled = true
    }
  }, [screen.name])

  // A file dropped beside the upload box would be opened by the browser, replacing the page and losing the setup.
  useEffect(() => {
    const keep = (e: DragEvent) => {
      if (!e.dataTransfer?.types?.includes('Files')) return
      // over the upload box, its own handlers have already claimed the drag
      if (!e.defaultPrevented) e.dataTransfer.dropEffect = 'none'
      e.preventDefault()
    }
    window.addEventListener('dragover', keep)
    window.addEventListener('drop', keep)
    return () => {
      window.removeEventListener('dragover', keep)
      window.removeEventListener('drop', keep)
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
          setResponse({ ...response, plan: withoutEmptySummers(response.plan) })
          setScreen({ name: 'planner' })
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
        {/* only worth the student's attention when something is wrong */}
        {backend === 'down' && (
          <p className="status status-down" role="status" data-testid="backend-status">
            Can&apos;t reach the server
          </p>
        )}
        <button className="icon-btn" type="button" aria-label="Toggle dark mode" onClick={toggleTheme}>
          <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M21 12.8A9 9 0 1111.2 3a7 7 0 009.8 9.8z" />
          </svg>
        </button>
      </header>

      <ErrorBoundary
        key={screen.name}
        onReset={() => {
          if (screen.name === 'planner') setResponse(undefined) // a plan that cannot be drawn is not offered again
          setScreen({ name: 'setup' })
        }}
      >
        {screen.name === 'setup' && (
          <SetupPage
            initial={form}
            onFormChange={setForm}
            onResume={response ? () => setScreen({ name: 'planner' }) : undefined}
            onSubmit={(request, submitted) => {
              setForm(submitted)
              build(request)
            }}
          />
        )}
        {screen.name === 'building' && <BuildingScreen request={screen.request} onCancel={cancel} />}
        {screen.name === 'planner' && response && (
          <PlannerPage
            plan={response.plan!}
            explanation={response.explanation}
            choices={response.choices}
            checks={response.checks}
            problems={response.status === 'cannot_work' ? response.problems : []}
            onChange={(plan) => setResponse((r) => r && { ...r, plan })}
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
      </ErrorBoundary>
    </>
  )
}

export default App
