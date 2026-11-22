import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { SetupPage } from './SetupPage.tsx'

const NOV_2026 = new Date(2026, 10, 22) // defaults to Spring 2027

function setup() {
  const onSubmit = vi.fn()
  render(<SetupPage onSubmit={onSubmit} today={NOV_2026} />)
  return onSubmit
}

const program = () => screen.getByLabelText('Program') as HTMLSelectElement
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
    expect(within(program()).getByRole('option', { name: /Computer Science \(General Track\)/ })).toBeInTheDocument()
    fireEvent.change(program(), { target: { value: 'cs-bs-general-track' } })
    fireEvent.click(screen.getByRole('button', { name: "Master's" }))
    expect(program()).toHaveValue('')
    expect(within(program()).queryByRole('option', { name: /Bachelor of Science/ })).not.toBeInTheDocument()
    expect(semesters()).toHaveValue(4)
    // minors and ASIs are not offered to master's students
    expect(screen.queryByRole('combobox', { name: 'Search minors and ASIs' })).not.toBeInTheDocument()
  })

  it('rejects a semester count outside the level\'s limit', () => {
    const onSubmit = setup()
    fireEvent.change(program(), { target: { value: 'cs-bs-general-track' } })
    fireEvent.change(semesters(), { target: { value: '19' } })
    fireEvent.click(screen.getByRole('button', { name: /Build my plan/ }))
    expect(onSubmit).not.toHaveBeenCalled()
    expect(screen.getByRole('alert')).toHaveTextContent('Choose between 1 and 18 semesters.')
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
    const box = screen.getByRole('combobox', { name: 'Search minors and ASIs' })
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
    fireEvent.change(program(), { target: { value: 'cs-bs-general-track' } })
    fireEvent.click(screen.getByRole('button', { name: /Build my plan/ }))
    expect(onSubmit).toHaveBeenCalledTimes(1)
    expect(onSubmit).toHaveBeenCalledWith({
      student: { degree_level: 'bachelor', programs: ['cs-bs-general-track'], catalog_year: '2026-2027', completed_courses: [] },
      semesters: 8,
      start_term: 'Spring 2027',
      include_summers: false,
      overrides: [],
    })
  })
})
