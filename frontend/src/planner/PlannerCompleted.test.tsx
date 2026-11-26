import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { samplePlan } from '../samplePlan.ts'
import type { CompletedCourse, Plan } from '../types.ts'
import { PlannerPage } from './PlannerPage.tsx'

afterEach(() => vi.unstubAllGlobals())

const withCompleted = (completed_courses: CompletedCourse[]): Plan => ({ ...samplePlan, student: { ...samplePlan.student, completed_courses } })
const c = (code: string, credits: number, term: string): CompletedCourse => ({ code, credits, term, transfer_from: null })

/** The validator's answer for the completed courses alone: every one is Core, and the core group is part done. */
function stubCompletedCheck() {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (_url: string, init: RequestInit) => {
      const plan = JSON.parse(init.body as string) as Plan
      const ids = plan.semesters.flatMap((s) => s.courses.map((x) => x.course_id))
      const answer: Plan = {
        ...plan,
        counts_toward: Object.fromEntries(ids.map((id) => [id, [{ program_id: 'cs-bs-general-track', group_id: 'required', label: 'Required core' }]])),
        requirement_status: [
          { program_id: 'cs-bs-general-track', group_id: 'required', label: 'Required core', kind: 'all', met: false, credits_required: null, credits_earned: 8, missing_count: 20 },
        ],
      }
      return { ok: true, status: 200, json: async () => answer }
    }),
  )
}

describe('completed courses on the planner page', () => {
  it('shows a few completed courses on the board, marked completed and labelled, without folding them', async () => {
    stubCompletedCheck()
    render(<PlannerPage plan={withCompleted([c('MATH111', 4, 'transfer'), c('CHGN121', 4, 'aplcredit')])} onBack={vi.fn()} />)
    const group = screen.getByRole('group', { name: /Completed courses: 2 courses, 8 cr/ })
    expect(within(group).getByRole('region', { name: 'Transfer credit, completed' })).toBeInTheDocument()
    expect(within(group).getByRole('region', { name: 'AP credit, completed' })).toBeInTheDocument()
    expect(within(group).getAllByText('Completed', { selector: '.card-done' })).toHaveLength(2)
    expect(screen.queryByRole('button', { name: /Hide completed courses/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Show completed courses/ })).not.toBeInTheDocument()
    await waitFor(() => expect(within(group).getAllByText('Core', { selector: '.card-tag' })).toHaveLength(2))
  })

  it('folds more than a semester of completed courses into a card that opens and closes', () => {
    stubCompletedCheck()
    const many = [c('MATH111', 4, 'Fall 2025'), c('CHGN121', 4, 'Fall 2025'), c('CSCI128', 3, 'Fall 2025'), c('MATH112', 4, 'Spring 2026'), c('PHGN100', 4, 'Spring 2026'), c('CSCI101', 3, 'Spring 2026')]
    render(<PlannerPage plan={withCompleted(many)} onBack={vi.fn()} />)
    expect(screen.queryByRole('group', { name: /Completed courses/ })).not.toBeInTheDocument()
    // folded: a card read left to right, with the total and each term
    const folded = screen.getByRole('region', { name: 'Completed courses: 6 courses, 22 cr' })
    expect(folded).toHaveTextContent('22 credits')
    expect(within(folded).getByText('Fall 2025')).toBeInTheDocument()
    expect(within(folded).getAllByText('11 cr')).toHaveLength(2) // Fall 2025 and Spring 2026
    fireEvent.click(screen.getByRole('button', { name: /Show completed courses \(6 courses, 22 cr\)/ }))
    const group = screen.getByRole('group', { name: /Completed courses/ })
    expect(within(group).getAllByRole('region').map((r) => r.getAttribute('aria-label'))).toEqual(['Fall 2025, completed', 'Spring 2026, completed'])
    expect(within(group).getAllByText('Completed', { selector: '.card-done' })).toHaveLength(6)
    fireEvent.click(screen.getByRole('button', { name: 'Hide completed courses' }))
    expect(screen.getByRole('button', { name: /Show completed courses/ })).toBeInTheDocument()
    // the planned semesters are there either way
    expect(screen.getByRole('region', { name: 'Fall 2026' })).toBeInTheDocument()
  })

  it('shows the credits remaining under the total, and what is already met in About this plan', async () => {
    stubCompletedCheck()
    render(<PlannerPage plan={withCompleted([c('MATH111', 4, 'transfer')])} onBack={vi.fn()} />)
    const planned = samplePlan.semesters.flatMap((s) => s.courses).reduce((n, x) => n + x.credits, 0)
    expect(screen.getByTestId('credit-remaining')).toHaveTextContent(`${planned} remaining · 4 completed`)
    fireEvent.click(screen.getByRole('button', { name: 'Show' }))
    const card = screen.getByText('Already completed').closest('.about-card') as HTMLElement
    expect(card).toHaveTextContent(/4 of \d+ credits from 1 course \(1 transfer, AP or IB\)/)
    await waitFor(() => expect(within(card).getByText('Core courses')).toBeInTheDocument())
    expect(within(card).getByText('8 credits done')).toBeInTheDocument()
  })

  it('marks in-progress courses as in progress, not completed, and shows placeholder credit readably', () => {
    stubCompletedCheck()
    render(
      <PlannerPage
        plan={withCompleted([
          { code: 'FREE1XX-1', credits: 3, term: 'transfer', transfer_from: 'Example State University', title: 'Free Elective: Example Course' },
          { code: 'CSCI261', credits: 3, term: 'Fall 2025', transfer_from: null, in_progress: true },
        ])}
        onBack={vi.fn()}
      />,
    )
    const group = screen.getByRole('group', { name: /Completed courses/ })
    const ip = within(group).getByRole('region', { name: 'Fall 2025, in progress' })
    expect(within(ip).getByText('In progress', { selector: '.card-done' })).toBeInTheDocument()
    const transfer = within(group).getByRole('region', { name: 'Transfer credit from Example State University, completed' })
    expect(within(transfer).getByText('FREE 1XX')).toBeInTheDocument()
    expect(within(transfer).getByText('Free Elective: Example Course')).toBeInTheDocument()
  })

  it('continues a long completed column in the next one, 8 courses at most each', () => {
    stubCompletedCheck()
    const many = Array.from({ length: 19 }, (_, k) => ({ code: `FREE1XX-${k + 1}`, credits: 3, term: 'transfer', transfer_from: 'Example State University' }))
    render(<PlannerPage plan={withCompleted(many)} onBack={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: /Show completed courses/ }))
    const group = screen.getByRole('group', { name: /Completed courses/ })
    const regions = within(group).getAllByRole('region')
    expect(regions.map((r) => r.getAttribute('aria-label'))).toEqual([
      'Transfer credit from Example State University, completed',
      'Transfer credit from Example State University, completed, continued (2)',
      'Transfer credit from Example State University, completed, continued (3)',
    ])
    expect(regions.map((r) => r.querySelectorAll('.card').length)).toEqual([8, 8, 3])
    expect(within(regions[0]).getByText('57 cr')).toBeInTheDocument() // the total stays on the first column
  })

  it('shows no completed area and no remaining line when nothing is completed', () => {
    stubCompletedCheck()
    render(<PlannerPage plan={withCompleted([])} onBack={vi.fn()} />)
    expect(screen.queryByRole('group', { name: /Completed courses/ })).not.toBeInTheDocument()
    expect(screen.queryByTestId('credit-remaining')).not.toBeInTheDocument()
    expect(fetch).not.toHaveBeenCalled()
  })
})
