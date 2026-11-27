import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError, parseTranscript, submitSetup } from './api.ts'
import type { AgentRequest } from './types.ts'

const request: AgentRequest = {
  student: { degree_level: 'bachelor', programs: ['cs-bs-general-track'], catalog_year: '2026-2027', completed_courses: [] },
  semesters: 8,
  start_term: 'Fall 2026',
  include_summers: false,
  overrides: [],
}

const reply = (status: number, body: unknown) => ({ ok: status >= 200 && status < 300, status, json: async () => body })

afterEach(() => vi.unstubAllGlobals())

describe('submitSetup', () => {
  it('posts the request as JSON to the backend and returns the response', async () => {
    const body = { status: 'ok', plan: null, explanation: 'x', problems: [], usage: { input_tokens: 1, output_tokens: 1, steps: 1 } }
    const fetchMock = vi.fn().mockResolvedValue(reply(200, body))
    vi.stubGlobal('fetch', fetchMock)
    await expect(submitSetup(request)).resolves.toEqual(body)
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/plans/submit-setup')
    expect(init.method).toBe('POST')
    expect(JSON.parse(init.body)).toEqual(request)
  })

  it('reports an unreachable backend', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))
    await expect(submitSetup(request)).rejects.toMatchObject({ kind: 'network' })
  })

  it('reports an agent that could not run (503) with the backend\'s reason', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(reply(503, { detail: 'claude is not signed in' })))
    await expect(submitSetup(request)).rejects.toMatchObject({ kind: 'agent_unavailable', message: 'claude is not signed in', status: 503 })
  })

  it('reads FastAPI validation errors (422) into one sentence', async () => {
    const detail = [{ loc: ['body', 'semesters'], msg: 'Input should be less than or equal to 18' }]
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(reply(422, { detail })))
    const error = await submitSetup(request).catch((e) => e)
    expect(error).toBeInstanceOf(ApiError)
    expect(error.kind).toBe('invalid_request')
    expect(error.message).toBe('semesters: Input should be less than or equal to 18')
  })

  it('treats other failures as server errors, even when the body is not JSON', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 500, json: async () => Promise.reject(new Error('not json')) }))
    await expect(submitSetup(request)).rejects.toMatchObject({ kind: 'server', status: 500, message: 'Something went wrong (error 500). Try again.' })
  })

  it('reports a cancelled request', async () => {
    const controller = new AbortController()
    vi.stubGlobal('fetch', vi.fn().mockImplementation(() => Promise.reject(new DOMException('aborted', 'AbortError'))))
    controller.abort()
    await expect(submitSetup(request, controller.signal)).rejects.toMatchObject({ kind: 'aborted' })
  })
})

describe('parseTranscript', () => {
  const file = new File(['code,credits,term\nMATH111,4.0,Fall 2025'], 'transcript.csv', { type: 'text/csv' })

  it('sends the file as a multipart upload and returns the completed courses', async () => {
    const courses = [{ code: 'MATH111', credits: 4, term: 'Fall 2025', transfer_from: null }]
    const fetchMock = vi.fn().mockResolvedValue(reply(200, courses))
    vi.stubGlobal('fetch', fetchMock)
    await expect(parseTranscript(file)).resolves.toEqual(courses)
    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/transcripts/parse')
    expect(init.method).toBe('POST')
    expect(init.body).toBeInstanceOf(FormData)
    expect((init.body as FormData).get('file')).toBeInstanceOf(File)
    expect(init.headers).toBeUndefined() // the browser sets the multipart boundary itself
  })

  it('passes on the backend\'s reason when a file cannot be read', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(reply(400, { detail: 'row 2: credits \'x\' is not a number' })))
    await expect(parseTranscript(file)).rejects.toMatchObject({ kind: 'invalid_request', message: "row 2: credits 'x' is not a number" })
  })

  it('reports an unreachable backend', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))
    await expect(parseTranscript(file)).rejects.toMatchObject({ kind: 'network' })
  })
})
