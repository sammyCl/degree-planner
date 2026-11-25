import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { PROGRAMS } from '../setup/validate.ts'
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
      expect(within(column).getAllByRole('button', { name: /credits/ })).toHaveLength(s.courses.length)
    }
    expect(screen.getByText('Principles of Programming Languages')).toBeInTheDocument()
  })

  it('shows the program, catalog year, notice and credit total', async () => {
    setup()
    expect(within(document.querySelector('.bar') as HTMLElement).getByText('Bachelor of Science in Computer Science (General Track)')).toBeInTheDocument()
    expect(screen.getByText('Catalog 2026-2027')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Show' }))
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

  it('lists only the errors when Errors is clicked, and goes to the course when one is chosen', () => {
    setup()
    fireEvent.click(screen.getByRole('button', { name: '2 errors' }))
    const items = screen.getAllByRole('menuitem')
    expect(items).toHaveLength(samplePlan.flags.filter((f) => f.severity === 'error').length)
    expect(items.some((i) => /credit/i.test(i.textContent ?? '') && /warning|short/i.test(i.textContent ?? ''))).toBe(false)
    fireEvent.click(items.find((i) => /out of order/i.test(i.textContent ?? ''))!)
    expect(screen.queryByRole('menu')).not.toBeInTheDocument()
    expect(card('CSCI400')).toHaveClass('pulse')
  })

  it('lists only the warnings, or only the to-confirm items, for the badge that was clicked', () => {
    const confirm = {
      flag_id: 'c1',
      type: 'exception_claimed' as const,
      severity: 'warning' as const,
      course_id: 'sem-2-csci200',
      message: 'CSCI200 relies on a claimed exception; confirm it still applies.',
      overridable: true,
      overridden: false,
    }
    render(<PlannerPage plan={{ ...samplePlan, flags: [...samplePlan.flags, confirm] }} onBack={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: '1 to confirm' }))
    expect(screen.getByRole('menu', { name: 'To confirm' })).toBeInTheDocument()
    expect(screen.getAllByRole('menuitem')).toHaveLength(1)
    expect(screen.getByRole('menuitem')).toHaveTextContent('claimed exception')
    fireEvent.click(screen.getByRole('button', { name: '1 warning' }))
    expect(screen.getByRole('menu', { name: 'Warnings' })).toBeInTheDocument()
    expect(screen.getAllByRole('menuitem')).toHaveLength(1)
    expect(screen.getByRole('menuitem')).not.toHaveTextContent('claimed exception')
    fireEvent.click(screen.getByRole('button', { name: '2 errors' }))
    expect(screen.getAllByRole('menuitem')).toHaveLength(2)
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
    expect(alert).toHaveTextContent('could not build a plan that passes every rule')
    expect(within(alert).getAllByRole('listitem')).toHaveLength(2)
  })

  it('shows what is met as a short checklist, with check marks and no course numbers', () => {
    setup()
    fireEvent.click(screen.getByRole('button', { name: 'Show' }))
    const panel = screen.getByRole('region', { name: 'About this plan' })
    const req = within(panel).getByRole('heading', { name: 'Degree requirements' }).closest('.about-card') as HTMLElement
    const row = (name: string) => within(req).getByText(name).closest('li') as HTMLElement
    expect(row('CS electives')).toHaveClass('met')
    expect(row('CS electives')).toHaveTextContent('18/18 credits')
    expect(row('Core courses')).toHaveClass('unmet')
    expect(row('Core courses')).toHaveTextContent('3 courses missing')
    expect(row('Free electives')).toHaveClass('met')
    expect(within(req).getByText('Prerequisites in order').closest('li')).toHaveClass('unmet')
    expect(req.textContent).not.toMatch(/[A-Z]{3,4}\d{3}/)
  })

  it('lists what to check by course title, and says so when there is nothing', () => {
    const flag = { flag_id: 'x', type: 'exception_claimed' as const, severity: 'warning' as const, course_id: 'sem-1-csci128', message: 'CSCI128 relies on a claimed exception (instructor consent); confirm it still applies.', overridable: true, overridden: false }
    const { unmount } = render(<PlannerPage plan={{ ...samplePlan, flags: [flag] }} onBack={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: 'Show' }))
    const card = screen.getByRole('heading', { name: 'Things to check' }).closest('.about-card') as HTMLElement
    expect(card).toHaveTextContent('Computer Science for STEM needs instructor consent; confirm it still applies')
    expect(card.textContent).not.toMatch(/CSCI128/)
    unmount()
    render(<PlannerPage plan={{ ...samplePlan, flags: [] }} onBack={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: 'Show' }))
    expect(screen.getByText('Nothing needs your attention.')).toBeInTheDocument()
  })

  it('shows the assistant\'s choices without its talk about tools, and hides the section when there are none', () => {
    const text = 'The plan meets every requirement. `check_plan` reports `requirements_met: true`.\n\n**Exceptions you need to decide.** Decide.\n- **MATH111** needs a note\n\nI put the electives in year two.'
    const { unmount } = render(<PlannerPage plan={samplePlan} explanation={text} onBack={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: 'Show' }))
    const card = screen.getByRole('heading', { name: 'Choices I made' }).closest('.about-card') as HTMLElement
    expect(card).toHaveTextContent('I put the electives in year two.')
    expect(card.textContent).not.toMatch(/check_plan|requirements_met|MATH111|Exceptions/)
    unmount()
    render(<PlannerPage plan={samplePlan} explanation="The plan meets every requirement." onBack={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: 'Show' }))
    expect(screen.queryByRole('heading', { name: 'Choices I made' })).not.toBeInTheDocument()
  })

  it('puts the About panel under the board, showing only a peek until the student opens it', () => {
    setup()
    const board = screen.getByTestId('board')
    const about = screen.getByRole('region', { name: 'About this plan' })
    expect(board.compareDocumentPosition(about) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy() // the board comes first
    const body = about.querySelector('.about-body') as HTMLElement
    expect(body).toHaveClass('peek') // the first lines are in the page but cut off, and cannot be tabbed into
    expect(body).toHaveAttribute('inert')
    fireEvent.click(screen.getByRole('button', { name: 'Show' }))
    expect(body).not.toHaveClass('peek')
    expect(body).not.toHaveAttribute('inert')
    fireEvent.click(screen.getByRole('button', { name: 'Hide' }))
    expect(body).toHaveClass('peek')
  })

  it('warns at the top when the plan uses an ASI from an older catalog, and says nothing otherwise', () => {
    const { unmount } = render(<PlannerPage plan={samplePlan} onBack={vi.fn()} />)
    expect(screen.queryByRole('note')).not.toBeInTheDocument()
    unmount()
    const asi = PROGRAMS.find((p) => p.level === 'asi')!
    render(<PlannerPage plan={{ ...samplePlan, student: { ...samplePlan.student, programs: [...samplePlan.student.programs, asi.id] } }} onBack={vi.fn()} />)
    const note = screen.getByRole('note')
    expect(note).toHaveTextContent('may not be up to date')
    expect(note).toHaveTextContent(`from the ${asi.catalog_year} catalog, not 2026-2027`)
  })

  it('keeps the "could not finish" alert above the board, where it is seen first', () => {
    setup(vi.fn(), { problems: ['Not enough credits.'] })
    const alert = screen.getByRole('alert')
    expect(alert.compareDocumentPosition(screen.getByTestId('board')) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
  })

  it('shows the assistant\'s markdown as formatting, not as symbols', () => {
    setup(vi.fn(), { explanation: 'It has **130 of 130 credits**.\n- **MATH111** needs a note' })
    fireEvent.click(screen.getByRole('button', { name: 'Show' }))
    expect(screen.getByText('130 of 130 credits').tagName).toBe('STRONG')
    expect(screen.queryByText(/\*\*/)).not.toBeInTheDocument()
  })

  it('draws an error in red, a warning in amber, and a claimed exception as a calm "to confirm"', () => {
    const withFlag = (type: 'exception_claimed' | 'credit_shortfall', severity: 'warning' | 'error') =>
      ({ ...samplePlan, flags: [{ ...samplePlan.flags[0], type, severity }] })
    const { unmount } = render(<PlannerPage plan={withFlag('exception_claimed', 'warning')} onBack={vi.fn()} />)
    expect(card('CSCI400')).toHaveClass('confirm')
    expect(card('CSCI400')).not.toHaveClass('warned')
    expect(card('CSCI400')).not.toHaveClass('flagged')
    expect(screen.getByRole('button', { name: '1 to confirm' })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /warning/ })).not.toBeInTheDocument()
    unmount()

    const second = render(<PlannerPage plan={withFlag('credit_shortfall', 'warning')} onBack={vi.fn()} />)
    expect(card('CSCI400')).toHaveClass('warned')
    expect(screen.getByRole('button', { name: '1 warning' })).toBeInTheDocument()
    second.unmount()

    render(<PlannerPage plan={withFlag('credit_shortfall', 'error')} onBack={vi.fn()} />)
    expect(card('CSCI400')).toHaveClass('flagged')
  })

  it('labels each course with what it counts as, and says Extra when it fills no group', () => {
    setup()
    const labelOf = (code: string) => card(code).querySelector('.card-tag')?.textContent
    expect(labelOf('CSCI200')).toBe('Core')
    expect(labelOf('PAGN101')).toBe('Extra')
    expect(screen.getAllByText('Free elective').length).toBeGreaterThan(0)
    expect(card('CSCI200')).toHaveAccessibleName(/, Core/)
  })

  it('shows no labels when the plan has no assignments', () => {
    render(<PlannerPage plan={{ ...samplePlan, counts_toward: undefined }} onBack={vi.fn()} />)
    expect(document.querySelector('.card-tag')).toBeNull()
  })

  it('goes back to setup', () => {
    const onBack = setup()
    fireEvent.click(screen.getByRole('button', { name: 'Edit setup' }))
    expect(onBack).toHaveBeenCalledTimes(1)
  })
})
