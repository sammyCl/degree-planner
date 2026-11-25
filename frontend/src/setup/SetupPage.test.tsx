import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { SetupPage } from './SetupPage.tsx'

const NOV_2026 = new Date(2026, 10, 22) // defaults to Spring 2027

function setup() {
  const onSubmit = vi.fn()
  render(<SetupPage onSubmit={onSubmit} today={NOV_2026} />)
  return onSubmit
}

const program = () => screen.getByRole('combobox', { name: 'Program' }) as HTMLInputElement
const CS = /Computer Science \(General Track\)/

/** Open a dropdown and click an option, the way a student does. */
function pick(combo: HTMLElement, option: string | RegExp) {
  fireEvent.click(combo)
  fireEvent.mouseDown(screen.getByRole('option', { name: option }))
}
const semesters = () => screen.getByLabelText(/Number of semesters/) as HTMLInputElement

describe('SetupPage', () => {
  it('starts on a bachelor\'s with a sensible default term and semester count', () => {
    setup()
    expect(screen.getByRole('button', { name: "Bachelor's" })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByLabelText('Starting season')).toHaveValue('Spring')
    expect(screen.getByLabelText('Starting year')).toHaveValue('2027')
    expect(semesters()).toHaveValue(8)
    // 8 semesters from Spring 2027 without summers ends in Fall 2030
    expect(screen.getByText('Fall 2030')).toBeInTheDocument()
  })

  it('does not submit without a program and shows the error', () => {
    const onSubmit = setup()
    fireEvent.click(screen.getByRole('button', { name: /Build my plan/ }))
    expect(onSubmit).not.toHaveBeenCalled()
    expect(screen.getByRole('alert')).toHaveTextContent('Choose your program.')
    expect(program()).toHaveAttribute('aria-invalid', 'true')
  })

  it('lists programs for the chosen level and clears the choice when the level changes', () => {
    setup()
    fireEvent.click(program())
    expect(screen.getByRole('option', { name: CS })).toBeInTheDocument()
    fireEvent.mouseDown(screen.getByRole('option', { name: CS }))
    expect(program()).toHaveValue('Bachelor of Science in Computer Science (General Track)')
    fireEvent.click(screen.getByRole('button', { name: "Master's" }))
    expect(program()).toHaveValue('')
    fireEvent.click(program())
    expect(screen.queryByRole('option', { name: /Bachelor of Science/ })).not.toBeInTheDocument()
    expect(screen.getAllByRole('option').length).toBeGreaterThan(10)
    expect(semesters()).toHaveValue(4)
    // minors and ASIs are not offered to master's students
    expect(screen.queryByRole('combobox', { name: 'Search minors' })).not.toBeInTheDocument()
  })

  it('rejects a semester count outside the level\'s limit', () => {
    const onSubmit = setup()
    pick(program(), CS)
    fireEvent.change(semesters(), { target: { value: '19' } })
    fireEvent.click(screen.getByRole('button', { name: /Build my plan/ }))
    expect(onSubmit).not.toHaveBeenCalled()
    expect(screen.getByRole('alert')).toHaveTextContent('Choose between 1 and 18 semesters.')
  })

  it('filters the program list as you type and chooses with the keyboard', () => {
    setup()
    fireEvent.change(program(), { target: { value: 'mining' } })
    const names = screen.getAllByRole('option').map((o) => o.textContent)
    expect(names.length).toBeGreaterThan(0)
    expect(names.every((n) => n!.toLowerCase().includes('mining'))).toBe(true)
    fireEvent.keyDown(program(), { key: 'ArrowDown' })
    fireEvent.keyDown(program(), { key: 'Enter' })
    expect(program().value.toLowerCase()).toContain('mining')
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
  })

  it('changes the starting term with the season and year dropdowns', () => {
    setup()
    pick(screen.getByRole('combobox', { name: 'Starting season' }), 'Fall')
    pick(screen.getByRole('combobox', { name: 'Starting year' }), '2028')
    expect(screen.getByLabelText('Starting season')).toHaveValue('Fall')
    expect(screen.getByLabelText('Starting year')).toHaveValue('2028')
    expect(screen.getByText('Spring 2032')).toBeInTheDocument() // 8 semesters from Fall 2028
  })

  it('opens a dropdown from its arrow, not only from its text', () => {
    setup()
    const season = screen.getByRole('combobox', { name: 'Starting season' })
    const arrow = season.parentElement!.querySelector('.dd-chevron')!
    fireEvent.mouseDown(arrow)
    expect(screen.getByRole('listbox', { name: 'Starting season' })).toBeInTheDocument()
    fireEvent.mouseDown(arrow)
    expect(screen.queryByRole('listbox', { name: 'Starting season' })).not.toBeInTheDocument()
  })

  it('keeps the stepper inside the limits', () => {
    setup()
    fireEvent.change(semesters(), { target: { value: '18' } })
    fireEvent.click(screen.getByRole('button', { name: 'More semesters' }))
    expect(semesters()).toHaveValue(18)
    fireEvent.change(semesters(), { target: { value: '1' } })
    fireEvent.click(screen.getByRole('button', { name: 'Fewer semesters' }))
    expect(semesters()).toHaveValue(1)
  })

  it('adds and removes a minor with the search box', () => {
    setup()
    const box = screen.getByRole('combobox', { name: 'Search minors' })
    fireEvent.focus(box)
    fireEvent.change(box, { target: { value: 'Computer Science' } })
    const option = screen.getAllByRole('option').find((o) => o.textContent?.startsWith('Computer Science'))!
    fireEvent.mouseDown(option)
    const remove = screen.getByRole('button', { name: /^Remove Computer Science/ })
    expect(remove).toBeInTheDocument()
    fireEvent.click(remove)
    expect(screen.queryByRole('button', { name: /^Remove Computer Science/ })).not.toBeInTheDocument()
  })

  it('shows summer terms in the projected graduation when summers are included', () => {
    setup()
    fireEvent.change(semesters(), { target: { value: '3' } })
    fireEvent.click(screen.getByLabelText('Include summer terms'))
    // Spring 2027, Summer 2027, Fall 2027
    expect(screen.getByText('Fall 2027')).toBeInTheDocument()
  })

  it('submits the request in the backend format', () => {
    const onSubmit = setup()
    pick(program(), CS)
    fireEvent.click(screen.getByRole('button', { name: /Build my plan/ }))
    expect(onSubmit).toHaveBeenCalledTimes(1)
    expect(onSubmit.mock.calls[0][0]).toEqual({
      student: { degree_level: 'bachelor', programs: ['cs-bs-general-track'], catalog_year: '2026-2027', completed_courses: [] },
      semesters: 8,
      start_term: 'Spring 2027',
      include_summers: false,
      overrides: [],
    })
    // the second argument is the form itself, so the page can restore it later
    expect(onSubmit.mock.calls[0][1]).toMatchObject({ level: 'bachelor', programId: 'cs-bs-general-track', semesters: 8 })
  })

  it('starts from the earlier choices when given them', () => {
    const initial = { level: 'master' as const, programId: '', addOnIds: [], season: 'Fall' as const, year: 2028, semesters: 5, includeSummers: true }
    render(<SetupPage onSubmit={vi.fn()} initial={initial} today={NOV_2026} />)
    expect(screen.getByRole('button', { name: "Master's" })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByLabelText('Starting season')).toHaveValue('Fall')
    expect(screen.getByLabelText('Starting year')).toHaveValue('2028')
    expect(semesters()).toHaveValue(5)
    expect(screen.getByLabelText('Include summer terms')).toBeChecked()
  })
})
