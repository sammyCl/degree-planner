// All backend calls go through /api. In development Vite proxies /api to the FastAPI server
// (see vite.config.ts), so the browser never needs the backend's address or CORS settings.
import type { AgentRequest, AgentResponse, CompletedCourse, Plan, TranscriptReading } from './types.ts'

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
async function readDetail(response: Response): Promise<string | null> {
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
    return null // not JSON, so it did not come from our backend's error handling
  }
  return `The backend returned ${response.status}.`
}

const UNREACHABLE = 'Could not reach the backend. Check that it is running.'
const unreadable = () => new ApiError('server', 'The backend sent an answer this page could not read.')

type Fields = Record<string, unknown>
const isObject = (value: unknown): value is Fields => typeof value === 'object' && value !== null && !Array.isArray(value)
const isListOfObjects = (value: unknown): value is Fields[] => Array.isArray(value) && value.every(isObject)
const isCourseList = (value: unknown): boolean =>
  isListOfObjects(value) && value.every((c) => typeof c.code === 'string' && typeof c.credits === 'number')
const textList = (value: unknown): string[] => (Array.isArray(value) ? value.filter((v): v is string => typeof v === 'string') : [])

/** Checks only what the planner page cannot draw without; the optional parts of a plan stay optional. */
function readPlan(value: unknown): Plan {
  const ok =
    isObject(value) &&
    isObject(value.student) &&
    Array.isArray(value.student.programs) &&
    isCourseList(value.student.completed_courses) &&
    isListOfObjects(value.semesters) &&
    value.semesters.every((s) => typeof s.label === 'string' && isCourseList(s.courses)) &&
    isListOfObjects(value.prerequisite_edges) &&
    isListOfObjects(value.flags) &&
    isObject(value.summary) &&
    typeof value.summary.total_credits === 'number' &&
    typeof value.summary.total_credits_required === 'number'
  if (!ok) throw unreadable()
  return value as unknown as Plan
}

function readAgentResponse(value: unknown): AgentResponse {
  if (!isObject(value) || value.plan === undefined) throw unreadable()
  return {
    ...(value as unknown as AgentResponse),
    plan: value.plan === null ? null : readPlan(value.plan),
    explanation: typeof value.explanation === 'string' ? value.explanation : '',
    // older answers have no choices or checks; they are left out rather than invented
    ...(value.choices !== undefined && { choices: textList(value.choices) }),
    ...(value.checks !== undefined && { checks: textList(value.checks) }),
    problems: textList(value.problems),
  }
}

/** POST JSON and read the answer, turning every way it can fail into an ApiError the page can explain. */
function postJson(url: string, body: unknown, signal?: AbortSignal): Promise<unknown> {
  return post(url, { headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }, signal)
}

async function post(url: string, init: { headers?: Record<string, string>; body: BodyInit }, signal?: AbortSignal): Promise<unknown> {
  const aborted = (error: unknown) => signal?.aborted || (error instanceof DOMException && error.name === 'AbortError')
  let response: Response
  try {
    response = await fetch(url, { method: 'POST', ...init, signal })
  } catch (error) {
    if (aborted(error)) throw new ApiError('aborted', 'Cancelled.')
    throw new ApiError('network', UNREACHABLE)
  }
  if (response.ok) {
    try {
      return await response.json()
    } catch (error) {
      if (aborted(error)) throw new ApiError('aborted', 'Cancelled.')
      throw unreadable()
    }
  }
  const detail = await readDetail(response)
  // The development server (and any proxy) answers like this, with no JSON, when the backend is not there.
  if (detail === null && (response.status === 502 || response.status === 504)) throw new ApiError('network', UNREACHABLE, response.status)
  const message = detail ?? `The backend returned ${response.status}.`
  if (response.status === 503) throw new ApiError('agent_unavailable', message, 503)
  if (response.status === 400 || response.status === 422) throw new ApiError('invalid_request', message, response.status)
  throw new ApiError('server', message, response.status)
}

/** How long to wait before giving up. Checking a plan is quick; reading an unfamiliar transcript asks Claude. */
const CHECK_TIMEOUT_MS = 30_000
const TRANSCRIPT_TIMEOUT_MS = 300_000

/** Run a request that is aborted, with its own message, if it takes longer than `ms`. */
async function withTimeout<T>(ms: number, signal: AbortSignal | undefined, request: (signal: AbortSignal) => Promise<T>): Promise<T> {
  const abort = new AbortController()
  let late = false
  const cancel = () => abort.abort()
  if (signal?.aborted) cancel()
  signal?.addEventListener('abort', cancel)
  const timer = setTimeout(() => {
    late = true
    cancel()
  }, ms)
  try {
    return await request(abort.signal)
  } catch (error) {
    if (late) throw new ApiError('server', 'The backend took too long to answer.')
    throw error
  } finally {
    clearTimeout(timer)
    signal?.removeEventListener('abort', cancel)
  }
}

/**
 * Ask the backend to build a plan for the setup form. The agent can take minutes (the backend stops it after ten),
 * so there is no timeout here; the caller passes a signal so the student can stop waiting.
 */
export async function submitSetup(request: AgentRequest, signal?: AbortSignal): Promise<AgentResponse> {
  return readAgentResponse(await postJson('/api/plans/submit-setup', request, signal))
}

/** Re-run the validator on a plan after the student changed it (docs/plan-format.md, "What drag-and-drop does"). */
export function checkPlan(plan: Plan, signal?: AbortSignal): Promise<Plan> {
  return withTimeout(CHECK_TIMEOUT_MS, signal, async (s) => readPlan(await postJson('/api/plans/check', plan, s)))
}

/**
 * Read an uploaded transcript (.csv or .pdf): the school it is from, its courses as Mines courses, and any course from
 * another school that still needs a Mines equivalent. `school` names the school when the student corrects it. The
 * backend does not keep the file; the student reviews the list before anything is sent to the planner.
 */
export function readTranscript(file: File, school: string | null, signal?: AbortSignal): Promise<TranscriptReading> {
  const body = new FormData()
  body.append('file', file)
  if (school) body.append('school', school)
  return withTimeout(TRANSCRIPT_TIMEOUT_MS, signal, async (s) => {
    const reading = await post('/api/transcripts/read', { body }, s)
    if (!isObject(reading) || !isCourseList(reading.courses) || !isListOfObjects(reading.unmatched)) throw unreadable()
    return reading as unknown as TranscriptReading
  })
}

/** The older call: only the courses, read as Mines courses. Kept for the CSV template path and its tests. */
export function parseTranscript(file: File, signal?: AbortSignal): Promise<CompletedCourse[]> {
  const body = new FormData()
  body.append('file', file)
  return post('/api/transcripts/parse', { body }, signal) as Promise<CompletedCourse[]>
}
