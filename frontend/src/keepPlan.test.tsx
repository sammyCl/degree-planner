import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import App from './App.tsx'
import { samplePlan } from './samplePlan.ts'
import { loadSession, saveSession } from './session.ts'
import { SetupPage } from './setup/SetupPage.tsx'
import type { SetupForm } from './setup/validate.ts'
import type { AgentResponse, Plan } from './types.ts'

const response: AgentResponse = { status: 'ok', plan: samplePlan, explanation: '', problems: [], usage: { input_tokens: 0, output_tokens: 0, steps: 0 } }
const ok = (body: unknown) => ({ ok: true, status: 200, json: async () => body }) as Response
const backend = () =>
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => ok(url.endsWith('/check') ? (JSON.parse(init!.body as string) as Plan) : { status: 'ok' })),
  )
const column = (label: string) => screen.getByRole('region', { name: label })

afterEach(() => vi.unstubAllGlobals())

describe('keeping the plan', () => {
  it('shows the plan again after a reload, with the changes made to it, also after Edit setup', async () => {
    backend()
    saveSession({ screen: 'planner', response })
    const first = render(<App />)
    const dataTransfer = { setData: vi.fn(), effectAllowed: '', dropEffect: '' }
    fireEvent.dragStart(screen.getByRole('button', { name: /^CSM101 / }), { dataTransfer })
    fireEvent.dragOver(column('Spring 2027'), { dataTransfer })
    fireEvent.drop(column('Spring 2027'), { dataTransfer })
    await waitFor(() => expect(loadSession().response!.plan!.semesters[1].courses.map((c) => c.code)).toContain('CSM101'))

    fireEvent.click(screen.getByRole('button', { name: 'Edit setup' }))
    fireEvent.click(screen.getByRole('button', { name: 'Back to my plan' }))
    expect(within(column('Spring 2027')).getByRole('button', { name: /^CSM101 / })).toBeInTheDocument()

    first.unmount()
    render(<App />) // a reload
    expect(within(column('Spring 2027')).getByRole('button', { name: /^CSM101 / })).toBeInTheDocument()
  })

  it('starts at setup, with no way back, when nothing usable was saved', () => {
    backend()
    sessionStorage.setItem('dp-session', JSON.stringify({ version: 1, screen: 'planner', response: { plan: { broken: true } }, form: 7 }))
    render(<App />)
    expect(screen.getByRole('button', { name: /Build my plan/ })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: 'Back to my plan' })).not.toBeInTheDocument()
    expect(loadSession().form?.level).toBe('bachelor')
  })

  it('warns once before leaving unmatched transfer courses out of the plan', () => {
    const onSubmit = vi.fn()
    const unmatched = { code: 'MATH 1401', title: 'Calculus', credits: 4, term: 'Fall 2025', in_progress: false, suggestion: null, reason: '' }
    const form: SetupForm = {
      level: 'bachelor', programId: 'cs-bs-general-track', addOnIds: [], season: 'Fall', year: 2027, semesters: 8, includeSummers: false,
      hasCompleted: true, completed: [], files: [{ name: 't.pdf', kind: 'pdf', found: 1, added: [], unmatched: [unmatched] }],
    }
    render(<SetupPage initial={form} onSubmit={onSubmit} />)
    const build = screen.getByRole('button', { name: /Build my plan/ })
    fireEvent.click(build)
    expect(onSubmit).not.toHaveBeenCalled()
    expect(screen.getByText(/1 course from another school is not in your plan yet/)).toBeInTheDocument()
    fireEvent.click(build)
    expect(onSubmit).toHaveBeenCalledTimes(1)
  })
})
