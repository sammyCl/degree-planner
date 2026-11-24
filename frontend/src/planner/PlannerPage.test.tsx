import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { samplePlan } from '../samplePlan.ts'
import { PlannerPage } from './PlannerPage.tsx'

function setup(onBack = vi.fn(), extra: { explanation?: string; problems?: string[] } = {}) {
  render(<PlannerPage plan={samplePlan} explanation="Plain explanation of the plan." onBack={onBack} {...extra} />)
  return onBack
}

const card = (code: string) => screen.getByRole('button', { name: new RegExp(`^${code} `) })

describe('PlannerPage', () => {
  it('shows every semester and every course of the plan', () => {
    setup()
    for (const s of samplePlan.semesters) {
      const column = screen.getByRole('region', { name: s.label })
      expect(within(column).getAllByRole('button')).toHaveLength(s.courses.length)
    }
    expect(screen.getByText('Principles of Programming Languages')).toBeInTheDocument()
  })

  it('shows the program, catalog year, notice and credit total', async () => {
    setup()
    expect(screen.getByText('Bachelor of Science in Computer Science (General Track)')).toBeInTheDocument()
    expect(screen.getByText('Catalog 2026-2027')).toBeInTheDocument()
    expect(screen.getByText('Plain explanation of the plan.')).toBeInTheDocument()
    expect(screen.getByText(/Bachelor's plan, 8 semesters, starting Fall 2026/)).toBeInTheDocument()
    // the number counts up over about a second
    await waitFor(() => expect(screen.getByTestId('credit-total')).toHaveTextContent('114 / 130'), { timeout: 4000 })
  })

  it('marks the flagged course and says why in its accessible name', () => {
    setup()
    const flagged = card('CSCI400')
    expect(flagged).toHaveClass('flagged')
    expect(flagged).toHaveAccessibleName(/Problem: CSCI400 requires CSCI306/)
    expect(card('CSCI306')).not.toHaveClass('flagged')
  })

  it('shows the error and warning counts from the plan', () => {
    setup()
    expect(screen.getByRole('button', { name: '2 errors' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '1 warning' })).toBeInTheDocument()
  })

  it('draws an arrow for each prerequisite edge', async () => {
    setup()
    const board = screen.getByTestId('board')
    // jsdom has no layout, so every card measures as 0x0, but each edge still gets a path
    await waitFor(() => expect(board.querySelectorAll('path.edge')).toHaveLength(samplePlan.prerequisite_edges.length))
  })

  it('highlights a course\'s whole chain on hover and dims the rest', () => {
    setup()
    const board = screen.getByTestId('board')
    fireEvent.mouseEnter(card('CSCI306'))
    expect(board).toHaveClass('chain-mode')
    expect(card('CSCI306')).toHaveClass('focus')
    expect(card('CSCI128')).toHaveClass('in-chain') // CSCI128 -> CSCI200 -> CSCI210 -> CSCI306
    expect(card('CSCI370')).toHaveClass('in-chain') // CSCI306 -> CSCI370
    expect(card('CSM101')).toHaveClass('dim')
    fireEvent.mouseLeave(card('CSCI306'))
    expect(board).not.toHaveClass('chain-mode')
  })

  it('opens the details for a course, with what it needs and unlocks and the problem', () => {
    setup()
    fireEvent.click(card('CSCI400'))
    const dialog = screen.getByRole('dialog', { name: 'CSCI400 details' })
    expect(within(dialog).getByText(/CSCI400 requires CSCI306 to be completed/)).toBeInTheDocument()
    expect(within(dialog).getByText(/CSCI306 · Fall 2028/)).toBeInTheDocument() // needs, same semester
    expect(within(dialog).getByText(/CSCI358 · Fall 2027/)).toBeInTheDocument()
    expect(within(dialog).getByText('Nothing in this plan')).toBeInTheDocument() // unlocks nothing
  })

  it('closes the details with Escape and the close button', () => {
    setup()
    fireEvent.click(card('CSCI210'))
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    fireEvent.keyDown(document, { key: 'Escape' })
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    fireEvent.click(card('CSCI210'))
    fireEvent.click(screen.getByRole('button', { name: 'Close' }))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('opens a course from the keyboard', () => {
    setup()
    fireEvent.keyDown(card('MATH213'), { key: 'Enter' })
    expect(screen.getByRole('dialog', { name: 'MATH213 details' })).toBeInTheDocument()
  })

  it('lists every flag and goes to the course when one is chosen', () => {
    setup()
    fireEvent.click(screen.getByRole('button', { name: '2 errors' }))
    const items = screen.getAllByRole('menuitem')
    expect(items).toHaveLength(samplePlan.flags.length)
    fireEvent.click(items.find((i) => /out of order/i.test(i.textContent ?? ''))!)
    expect(screen.queryByRole('menu')).not.toBeInTheDocument()
    expect(card('CSCI400')).toHaveClass('pulse')
  })

  it('marks an under-full-time semester', () => {
    setup()
    const last = screen.getByRole('region', { name: 'Spring 2030' })
    expect(last.querySelector('.meter')).toHaveClass('low')
    expect(screen.getByRole('region', { name: 'Fall 2026' }).querySelector('.meter')).toHaveClass('ok')
  })

  it('lists the problems when the assistant could not finish a valid plan', () => {
    setup(vi.fn(), { problems: ['CSCI400 cannot be placed after CSCI306.', 'Not enough credits.'] })
    const alert = screen.getByRole('alert')
    expect(alert).toHaveTextContent('could not finish a valid plan')
    expect(within(alert).getAllByRole('listitem')).toHaveLength(2)
  })

  it('collapses a long explanation without cutting its text, and expands it on request', () => {
    const long = 'word '.repeat(200).trim()
    setup(vi.fn(), { explanation: long })
    const text = screen.getByText(long) // the whole text is there; CSS clamps how much shows
    expect(text.closest('.note-text')).toHaveClass('clamped')
    fireEvent.click(screen.getByRole('button', { name: 'Show more' }))
    expect(text.closest('.note-text')).not.toHaveClass('clamped')
    fireEvent.click(screen.getByRole('button', { name: 'Show less' }))
    expect(screen.getByRole('button', { name: 'Show more' })).toBeInTheDocument()
  })

  it('shows the assistant\'s markdown as formatting, not as symbols', () => {
    setup(vi.fn(), { explanation: 'It has **130 of 130 credits**.\n- **MATH111** needs a note' })
    expect(screen.getByText('130 of 130 credits').tagName).toBe('STRONG')
    expect(screen.queryByText(/\*\*/)).not.toBeInTheDocument()
  })

  it('draws a warning in amber and an error in red', () => {
    const warned = { ...samplePlan, flags: [{ ...samplePlan.flags[0], severity: 'warning' as const, type: 'exception_claimed' as const }] }
    render(<PlannerPage plan={warned} onBack={vi.fn()} />)
    expect(card('CSCI400')).toHaveClass('warned')
    expect(card('CSCI400')).not.toHaveClass('flagged')
  })

  it('goes back to setup', () => {
    const onBack = setup()
    fireEvent.click(screen.getByRole('button', { name: 'Edit setup' }))
    expect(onBack).toHaveBeenCalledTimes(1)
  })
})
