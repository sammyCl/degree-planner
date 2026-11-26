import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { samplePlan } from '../samplePlan.ts'
import type { Plan } from '../types.ts'
import { PlannerPage } from './PlannerPage.tsx'

afterEach(() => vi.unstubAllGlobals())

const card = (code: string) => screen.getByRole('button', { name: new RegExp(`^${code} `) })
const column = (label: string) => screen.getByRole('region', { name: label })
/** the semester columns, in order (the About panel is also a region) */
const semesterLabels = () => [...document.querySelectorAll('section.sem:not(.done)')].map((s) => s.getAttribute('aria-label'))
const codesIn = (label: string) => within(column(label)).queryAllByRole('button', { name: /credits/ }).map((b) => b.textContent?.match(/^[A-Z]{3,4}\d{3}/)?.[0])

/** The page's own check of the completed courses alone (completed.ts), not a check of the student's edit. */
const isCompletedOnly = (plan: Plan) => plan.semesters.length > 0 && plan.semesters.every((s) => s.semester_id.startsWith('done-'))

/**
 * A backend that answers every /plans/check with the plan it was sent, plus whatever `change` does to it. `sent` and
 * `fetchMock` record only the checks of the student's edits.
 */
function stubCheck(change: (plan: Plan) => Plan = (p) => p) {
  const sent: Plan[] = []
  const edits = vi.fn()
  const fetchMock = vi.fn(async (url: string, init: RequestInit) => {
    const plan = JSON.parse(init.body as string) as Plan
    if (isCompletedOnly(plan)) return { ok: true, status: 200, json: async () => plan }
    edits(url, init)
    sent.push(plan)
    return { ok: true, status: 200, json: async () => change(plan) }
  })
  vi.stubGlobal('fetch', fetchMock)
  return { sent, fetchMock: edits }
}

const dataTransfer = () => ({ setData: vi.fn(), effectAllowed: '', dropEffect: '' })

function drag(code: string, toLabel: string) {
  const dt = dataTransfer()
  fireEvent.dragStart(card(code), { dataTransfer: dt })
  fireEvent.dragOver(column(toLabel), { dataTransfer: dt })
  fireEvent.drop(column(toLabel), { dataTransfer: dt })
}

describe('moving a course', () => {
  it('shows the move at once and sends the new plan to the backend to be checked', async () => {
    const { sent, fetchMock } = stubCheck()
    render(<PlannerPage plan={samplePlan} onBack={vi.fn()} />)
    expect(codesIn('Fall 2026')).toContain('CSM101')

    drag('CSM101', 'Spring 2027')

    expect(codesIn('Fall 2026')).not.toContain('CSM101')
    expect(codesIn('Spring 2027')).toContain('CSM101')
    expect(screen.getByRole('status')).toHaveTextContent('Checking your change')
    await waitFor(() => expect(screen.queryByText('Checking your change...')).not.toBeInTheDocument())
    expect(fetchMock.mock.calls[0][0]).toBe('/api/plans/check')
    const moved = sent[0].semesters[1].courses.map((c) => c.course_id)
    expect(moved).toContain('sem-1-csm101') // the course keeps its id; only its place changed
  })

  it('replaces the plan with what the backend returns, so its flags are the ones shown', async () => {
    stubCheck((plan) => ({
      ...plan,
      flags: [
        ...plan.flags,
        { flag_id: 'new', type: 'broken_prerequisite', severity: 'error', course_id: 'sem-2-csci200', message: 'CSCI200 is out of order.', overridable: false, overridden: false },
      ],
    }))
    render(<PlannerPage plan={samplePlan} onBack={vi.fn()} />)
    expect(screen.getByRole('button', { name: '2 errors' })).toBeInTheDocument()

    drag('CSM101', 'Spring 2027')

    expect(await screen.findByRole('button', { name: '3 errors' })).toBeInTheDocument()
    expect(card('CSCI200')).toHaveClass('flagged')
  })

  it('undoes the move and says so when the backend cannot be reached', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))
    render(<PlannerPage plan={samplePlan} onBack={vi.fn()} />)

    drag('CSM101', 'Spring 2027')

    expect(await screen.findByRole('alert')).toHaveTextContent('Could not reach the backend, so your change was undone.')
    expect(codesIn('Fall 2026')).toContain('CSM101')
    expect(codesIn('Spring 2027')).not.toContain('CSM101')
    fireEvent.click(screen.getByRole('button', { name: 'Dismiss' }))
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('undoes the move when the backend rejects it', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 422, json: async () => ({ detail: 'bad plan' }) }))
    render(<PlannerPage plan={samplePlan} onBack={vi.fn()} />)
    drag('CSM101', 'Spring 2027')
    expect(await screen.findByRole('alert')).toHaveTextContent('could not re-check the plan, so your change was undone. bad plan')
    expect(codesIn('Fall 2026')).toContain('CSM101')
  })

  it('ignores a drop onto the semester the course is already in', () => {
    const { fetchMock } = stubCheck()
    render(<PlannerPage plan={samplePlan} onBack={vi.fn()} />)
    drag('CSM101', 'Fall 2026')
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('lets a planned course be dragged but not a completed one', () => {
    const plan: Plan = {
      ...samplePlan,
      semesters: samplePlan.semesters.map((s, i) =>
        i === 0 ? { ...s, courses: s.courses.map((c) => (c.code === 'CSM101' ? { ...c, status: 'completed' as const } : c)) } : s,
      ),
    }
    render(<PlannerPage plan={plan} onBack={vi.fn()} />)
    expect(card('CSCI128')).toHaveAttribute('draggable', 'true')
    expect(card('CSM101')).toHaveAttribute('draggable', 'false')
  })

  it('moves a course from its details with the Move-to list, no dragging needed', async () => {
    const { sent } = stubCheck()
    render(<PlannerPage plan={samplePlan} onBack={vi.fn()} />)
    fireEvent.click(card('CSM101'))
    const dialog = screen.getByRole('dialog', { name: 'CSM101 details' })
    const move = within(dialog).getByRole('button', { name: 'Move' })
    expect(move).toBeDisabled() // it is already in Fall 2026
    fireEvent.click(within(dialog).getByRole('combobox', { name: 'Move to semester' }))
    fireEvent.mouseDown(screen.getByRole('option', { name: 'Fall 2027' }))
    fireEvent.click(within(dialog).getByRole('button', { name: 'Move' }))

    expect(codesIn('Fall 2027')).toContain('CSM101')
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    await waitFor(() => expect(sent).toHaveLength(1))
  })

  it('stays open when the clicked menu option is removed from the page while the click is handled', () => {
    // in a browser React drops the chosen option before the popover's outside-click check runs
    render(<PlannerPage plan={samplePlan} onBack={vi.fn()} />)
    fireEvent.click(card('CSM101'))
    const dialog = screen.getByRole('dialog', { name: 'CSM101 details' })
    const option = document.createElement('div')
    dialog.appendChild(option)
    dialog.addEventListener('mousedown', () => option.remove())
    act(() => {
      option.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }))
    })
    expect(screen.getByRole('dialog', { name: 'CSM101 details' })).toBeInTheDocument()
  })

  it('offers no Move-to for a completed course', () => {
    const plan: Plan = {
      ...samplePlan,
      semesters: samplePlan.semesters.map((s, i) =>
        i === 0 ? { ...s, courses: s.courses.map((c) => (c.code === 'CSM101' ? { ...c, status: 'completed' as const } : c)) } : s,
      ),
    }
    render(<PlannerPage plan={plan} onBack={vi.fn()} />)
    fireEvent.click(card('CSM101'))
    expect(within(screen.getByRole('dialog')).queryByRole('combobox', { name: 'Move to semester' })).not.toBeInTheDocument()
  })

  it('keeps the newest edit when two checks overlap', async () => {
    const answers: Array<(r: unknown) => void> = []
    vi.stubGlobal('fetch', vi.fn((_u: string, init: RequestInit) => new Promise((resolve) => {
      const plan = JSON.parse(init.body as string)
      answers.push(() => resolve({ ok: true, status: 200, json: async () => plan }))
    })))
    render(<PlannerPage plan={samplePlan} onBack={vi.fn()} />)
    drag('CSM101', 'Spring 2027')
    drag('PAGN101', 'Fall 2026') // a second edit while the first check is still running
    await act(async () => answers[1](null)) // the newer answer arrives first
    await act(async () => answers[0](null)) // then the older one, which must be ignored
    expect(codesIn('Spring 2027')).toContain('CSM101')
    expect(codesIn('Fall 2026')).toContain('PAGN101')
  })
})

describe('adding a semester', () => {
  it('adds a Summer after a Spring and lets courses be dragged into it', async () => {
    const { sent } = stubCheck()
    render(<PlannerPage plan={samplePlan} onBack={vi.fn()} />)
    expect(screen.queryByRole('region', { name: 'Summer 2027' })).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Add Summer 2027 after Spring 2027' }))

    const summer = column('Summer 2027')
    expect(within(summer).getByText('Drag courses here')).toBeInTheDocument()
    const labels = semesterLabels()
    expect(labels.slice(0, 4)).toEqual(['Fall 2026', 'Spring 2027', 'Summer 2027', 'Fall 2027']) // in calendar order
    await waitFor(() => expect(sent).toHaveLength(1))
    expect(sent[0].semesters.map((s) => s.label).slice(0, 4)).toEqual(['Fall 2026', 'Spring 2027', 'Summer 2027', 'Fall 2027'])

    drag('CSM101', 'Summer 2027')
    expect(codesIn('Summer 2027')).toEqual(['CSM101'])
    expect(within(column('Summer 2027')).queryByText('Drag courses here')).not.toBeInTheDocument()
  })

  it('stops offering a second Summer once one is added after that Spring', () => {
    stubCheck()
    render(<PlannerPage plan={samplePlan} onBack={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: 'Add Summer 2027 after Spring 2027' }))
    expect(screen.queryByRole('button', { name: 'Add Summer 2027 after Spring 2027' })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Add Summer 2028 after Spring 2028' })).toBeInTheDocument()
  })

  it('adds the next regular semester at the end', async () => {
    stubCheck()
    render(<PlannerPage plan={samplePlan} onBack={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: 'Add Fall 2030 at the end' }))
    const labels = semesterLabels()
    expect(labels[labels.length - 1]).toBe('Fall 2030')
    await waitFor(() => expect(screen.queryByText('Checking your change...')).not.toBeInTheDocument())
    expect(screen.getByRole('button', { name: 'Add Spring 2031 at the end' })).toBeInTheDocument() // and so on
  })

  it('removes an added semester while it is empty, but not once it has a course', () => {
    stubCheck()
    render(<PlannerPage plan={samplePlan} onBack={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: 'Add Summer 2027 after Spring 2027' }))
    fireEvent.click(screen.getByRole('button', { name: 'Remove Summer 2027' }))
    expect(screen.queryByRole('region', { name: 'Summer 2027' })).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Add Summer 2027 after Spring 2027' }))
    drag('CSM101', 'Summer 2027')
    expect(screen.queryByRole('button', { name: 'Remove Summer 2027' })).not.toBeInTheDocument()
    // the plan's own semesters are never removable
    expect(screen.queryByRole('button', { name: 'Remove Fall 2026' })).not.toBeInTheDocument()
  })

  it('undoes an added semester if the backend cannot check it', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))
    render(<PlannerPage plan={samplePlan} onBack={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: 'Add Summer 2027 after Spring 2027' }))
    expect(await screen.findByRole('alert')).toBeInTheDocument()
    expect(screen.queryByRole('region', { name: 'Summer 2027' })).not.toBeInTheDocument()
  })
})

describe('undo and redo', () => {
  it('shows no undo or redo until the plan is edited', () => {
    render(<PlannerPage plan={samplePlan} onBack={vi.fn()} />)
    expect(screen.queryByRole('button', { name: /Undo/ })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Redo/ })).not.toBeInTheDocument()
  })

  it('undoes and redoes a move, asking the backend to check each plan', async () => {
    const { sent } = stubCheck()
    render(<PlannerPage plan={samplePlan} onBack={vi.fn()} />)
    drag('CSM101', 'Spring 2027')
    await waitFor(() => expect(sent).toHaveLength(1))
    expect(screen.getByRole('button', { name: /Redo/ })).toBeDisabled()

    fireEvent.click(screen.getByRole('button', { name: /Undo/ }))
    expect(codesIn('Fall 2026')).toContain('CSM101')
    expect(screen.getByRole('button', { name: /Undo/ })).toBeDisabled()
    await waitFor(() => expect(sent).toHaveLength(2))

    fireEvent.click(screen.getByRole('button', { name: /Redo/ }))
    expect(codesIn('Spring 2027')).toContain('CSM101')
    await waitFor(() => expect(sent).toHaveLength(3))
  })

  it('also undoes adding a semester, and the keyboard shortcut works', async () => {
    stubCheck()
    render(<PlannerPage plan={samplePlan} onBack={vi.fn()} />)
    const before = semesterLabels().length
    fireEvent.click(screen.getByRole('button', { name: /^Add .* at the end$/ }))
    expect(semesterLabels()).toHaveLength(before + 1)
    fireEvent.keyDown(document.body, { key: 'z', ctrlKey: true })
    await waitFor(() => expect(semesterLabels()).toHaveLength(before))
    fireEvent.keyDown(document.body, { key: 'z', ctrlKey: true, shiftKey: true })
    await waitFor(() => expect(semesterLabels()).toHaveLength(before + 1))
  })

  it('forgets the redo list when a new change is made after an undo', async () => {
    stubCheck()
    render(<PlannerPage plan={samplePlan} onBack={vi.fn()} />)
    drag('CSM101', 'Spring 2027')
    fireEvent.click(await screen.findByRole('button', { name: /Undo/ }))
    expect(screen.getByRole('button', { name: /Redo/ })).toBeEnabled()
    drag('CSM101', 'Spring 2027')
    expect(screen.getByRole('button', { name: /Redo/ })).toBeDisabled()
  })
})
