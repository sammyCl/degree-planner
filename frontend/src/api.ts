// All backend calls go through /api. In development Vite proxies /api to the FastAPI server
// (see vite.config.ts), so the browser never needs the backend's address or CORS settings.
import type { AgentRequest, AgentResponse, CompletedCourse, Plan } from './types.ts'

export async function getHealth(): Promise<{ status: string; database: string }> {
  const response = await fetch('/api/health')
  if (!response.ok) {
    throw new Error(`Backend returned ${response.status}`)
  }
  return response.json()
}

export type ApiErrorKind =
  /** the backend could not be reached at all */
  | 'network'
  /** the agent could not run on the server (HTTP 503): not installed or not signed in */
  | 'agent_unavailable'
  /** the backend rejected the request (HTTP 400 or 422) */
  | 'invalid_request'
  /** anything else the server did wrong */
  | 'server'
  /** the student cancelled */
  | 'aborted'

export class ApiError extends Error {
  kind: ApiErrorKind
  status?: number
  constructor(kind: ApiErrorKind, message: string, status?: number) {
    super(message)
    this.name = 'ApiError'
    this.kind = kind
    this.status = status
  }
}

/** FastAPI sends errors as {"detail": "text"} or {"detail": [{"loc": [...], "msg": "text"}, ...]}. */
async function readDetail(response: Response): Promise<string> {
  try {
    const body = await response.json()
    const detail = body?.detail
    if (typeof detail === 'string') return detail
    if (Array.isArray(detail)) {
      return detail
        .map((d: { loc?: unknown[]; msg?: string }) => [d.loc?.slice(1).join('.'), d.msg].filter(Boolean).join(': '))
        .join('; ')
    }
  } catch {
    // not JSON; fall through
  }
  return `The backend returned ${response.status}.`
}

/** POST JSON and read the answer, turning every way it can fail into an ApiError the page can explain. */
function postJson<T>(url: string, body: unknown, signal?: AbortSignal): Promise<T> {
  return post(url, { headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }, signal)
}

async function post<T>(url: string, init: { headers?: Record<string, string>; body: BodyInit }, signal?: AbortSignal): Promise<T> {
  let response: Response
  try {
    response = await fetch(url, { method: 'POST', ...init, signal })
  } catch (error) {
    if (signal?.aborted || (error instanceof DOMException && error.name === 'AbortError')) {
      throw new ApiError('aborted', 'Cancelled.')
    }
    throw new ApiError('network', 'Could not reach the backend. Check that it is running.')
  }
  if (response.ok) {
    return response.json()
  }
  const detail = await readDetail(response)
  if (response.status === 503) throw new ApiError('agent_unavailable', detail, 503)
  if (response.status === 400 || response.status === 422) throw new ApiError('invalid_request', detail, response.status)
  throw new ApiError('server', detail, response.status)
}

/**
 * Ask the backend to build a plan for the setup form. The agent can take minutes (the backend stops it after ten),
 * so there is no timeout here; the caller passes a signal so the student can stop waiting.
 */
export function submitSetup(request: AgentRequest, signal?: AbortSignal): Promise<AgentResponse> {
  return postJson('/api/plans/submit-setup', request, signal)
}

/** Re-run the validator on a plan after the student changed it (docs/plan-format.md, "What drag-and-drop does"). */
export function checkPlan(plan: Plan, signal?: AbortSignal): Promise<Plan> {
  return postJson('/api/plans/check', plan, signal)
}

/**
 * Read an uploaded transcript (.csv or .pdf) into completed courses. The backend does not keep the file; the student
 * reviews and corrects the courses on the setup page before anything is sent to the planner.
 */
export function parseTranscript(file: File, signal?: AbortSignal): Promise<CompletedCourse[]> {
  const body = new FormData()
  body.append('file', file)
  return post('/api/transcripts/parse', { body }, signal)
}
