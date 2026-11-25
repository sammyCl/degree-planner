import { act, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from './App.tsx'
import { samplePlan } from './samplePlan.ts'
import type { AgentResponse } from './types.ts'

afterEach(() => {
  vi.unstubAllGlobals()
})

const ok = (body: unknown) => ({ ok: true, status: 200, json: async () => body })
const fail = (status: number, body: unknown) => ({ ok: false, status, json: async () => body })
const usage = { input_tokens: 10, output_tokens: 5, steps: 2 }
const goodResponse: AgentResponse = { status: 'ok', plan: samplePlan, explanation: 'I placed CSCI courses early.', problems: [], usage }

/** Stub fetch: /health answers, submit-setup is handled by `submit` (which may return a promise to hold the request open). */
function stubBackend(submit: (init: RequestInit) => unknown) {
  const calls: RequestInit[] = []
  const fetchMock = vi.fn(async (url: string, init?: RequestInit) => {
    if (String(url).endsWith('/health')) return ok({ status: 'ok', database: 'ok' })
    calls.push(init ?? {})
    return submit(init ?? {})
  })
  vi.stubGlobal('fetch', fetchMock)
  return calls
}

function chooseProgramAndBuild() {
  fireEvent.click(screen.getByRole('combobox', { name: 'Program' }))
  fireEvent.mouseDown(screen.getByRole('option', { name: /Computer Science \(General Track\)/ }))
  fireEvent.click(screen.getByRole('button', { name: /Build my plan/ }))
}

describe('App', () => {
  it('shows the title and reports the backend as connected', async () => {
    stubBackend(() => ok(goodResponse))
    render(<App />)
    expect(screen.getByRole('heading', { name: 'Degree Planner' })).toBeInTheDocument()
    await waitFor(() => expect(screen.getByTestId('backend-status')).toHaveTextContent('connected'))
  })

  it('does not crash when the backend is down', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('network')))
    render(<App />)
    await waitFor(() => expect(screen.getByTestId('backend-status')).toHaveTextContent('not running'))
  })
})

describe('building a plan', () => {
  it('waits on a busy screen, then shows the plan and the assistant\'s explanation', async () => {
    let finish: (r: unknown) => void = () => {}
    const calls = stubBackend(() => new Promise((resolve) => (finish = resolve)))
    render(<App />)
    chooseProgramAndBuild()

    expect(screen.getByRole('heading', { name: 'Building your plan' })).toBeInTheDocument()
    expect(screen.getByRole('status')).toHaveTextContent(/choosing your courses/)
    expect(document.querySelectorAll('.fact-slide.on')).toHaveLength(1)
    expect(calls).toHaveLength(1)
    expect(JSON.parse(calls[0].body as string)).toMatchObject({
      student: { degree_level: 'bachelor', programs: ['cs-bs-general-track'] },
      semesters: 8,
    })

    await act(async () => finish(ok(goodResponse)))
    expect(screen.getByRole('region', { name: 'Fall 2026' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Show' })) // the About panel starts closed, under the board
    expect(screen.getByText('I placed CSCI courses early.')).toBeInTheDocument()
    expect(screen.queryByText(/could not finish a valid plan/)).not.toBeInTheDocument()
  })

  it('draws the last attempt and lists the problems when the assistant could not finish', async () => {
    stubBackend(() => ok({ ...goodResponse, status: 'cannot_work', problems: ['Credits are 16 short.'] }))
    render(<App />)
    chooseProgramAndBuild()
    expect(await screen.findByRole('region', { name: 'Fall 2026' })).toBeInTheDocument()
    expect(screen.getByRole('alert')).toHaveTextContent('Credits are 16 short.')
  })

  it('says so, with the reasons, when no plan came back at all', async () => {
    stubBackend(() => ok({ status: 'cannot_work', plan: null, explanation: 'That program is not loaded.', problems: ['No such program.'], usage }))
    render(<App />)
    chooseProgramAndBuild()
    expect(await screen.findByRole('heading', { name: 'The assistant could not build a plan' })).toBeInTheDocument()
    expect(screen.getByText('That program is not loaded.')).toBeInTheDocument()
    expect(screen.getByText('No such program.')).toBeInTheDocument()
  })

  it('explains when the assistant cannot run (503) and lets the student try again', async () => {
    let attempt = 0
    const calls = stubBackend(() => (++attempt === 1 ? fail(503, { detail: 'claude is not signed in' }) : ok(goodResponse)))
    render(<App />)
    chooseProgramAndBuild()
    expect(await screen.findByRole('heading', { name: 'The planning assistant is not available' })).toBeInTheDocument()
    expect(screen.getByText(/claude is not signed in/)).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Try again' }))
    expect(await screen.findByRole('region', { name: 'Fall 2026' })).toBeInTheDocument()
    expect(calls).toHaveLength(2)
  })

  it('explains an unreachable backend', async () => {
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      if (String(url).endsWith('/health')) return ok({ status: 'ok', database: 'ok' })
      throw new TypeError('Failed to fetch')
    }))
    render(<App />)
    chooseProgramAndBuild()
    expect(await screen.findByRole('heading', { name: 'Cannot reach the backend' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Try again' })).toBeInTheDocument()
  })

  it('shows what the backend rejected, with no retry, for a bad request (422)', async () => {
    stubBackend(() => fail(422, { detail: [{ loc: ['body', 'semesters'], msg: 'too many' }] }))
    render(<App />)
    chooseProgramAndBuild()
    expect(await screen.findByRole('heading', { name: 'The backend did not accept this setup' })).toBeInTheDocument()
    expect(screen.getByText('semesters: too many')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Try again' })).not.toBeInTheDocument()
  })

  it('cancels back to setup with the student\'s choices kept, and ignores a late answer', async () => {
    let finish: (r: unknown) => void = () => {}
    stubBackend(() => new Promise((resolve) => (finish = resolve)))
    render(<App />)
    chooseProgramAndBuild()
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(screen.getByRole('form', { name: 'Plan setup' })).toBeInTheDocument()
    expect(screen.getByRole('combobox', { name: 'Program' })).toHaveValue('Bachelor of Science in Computer Science (General Track)')

    await act(async () => finish(ok(goodResponse))) // the cancelled run answers after all
    expect(screen.getByRole('form', { name: 'Plan setup' })).toBeInTheDocument()
    expect(screen.queryByRole('region', { name: 'Fall 2026' })).not.toBeInTheDocument()
  })

  it('goes back from the planner to setup with the choices kept', async () => {
    stubBackend(() => ok(goodResponse))
    render(<App />)
    chooseProgramAndBuild()
    await screen.findByRole('region', { name: 'Fall 2026' })
    fireEvent.click(screen.getByRole('button', { name: 'Edit setup' }))
    expect(screen.getByRole('combobox', { name: 'Program' })).toHaveValue('Bachelor of Science in Computer Science (General Track)')
  })
})
