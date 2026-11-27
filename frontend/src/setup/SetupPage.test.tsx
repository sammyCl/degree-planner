import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { SetupPage } from './SetupPage.tsx'

const NOV_2026 = new Date(2026, 10, 22) // defaults to Fall 2027

function setup() {
  const onSubmit = vi.fn()
  render(<SetupPage onSubmit={onSubmit} today={NOV_2026} />)
  return onSubmit
}

const program = () => screen.getByRole('combobox', { name: 'Program' }) as HTMLInputElement
// a bachelor's with no summer course, so choosing it keeps the usual 8 semesters
const MECH = /^Bachelor of Science in Mechanical Engineering$/

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
    expect(screen.getByLabelText('Starting season')).toHaveValue('Fall')
    expect(screen.getByLabelText('Starting year')).toHaveValue('2027')
    expect(semesters()).toHaveValue(8)
    // 8 semesters from Fall 2027 without summers ends in Spring 2031
    expect(screen.getByText('Spring 2031')).toBeInTheDocument()
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
    expect(screen.getByRole('option', { name: MECH })).toBeInTheDocument()
    fireEvent.mouseDown(screen.getByRole('option', { name: MECH }))
    expect(program()).toHaveValue('Bachelor of Science in Mechanical Engineering')
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
    pick(program(), MECH)
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

  it('keeps ASIs in their own picker, apart from minors, with each one marked with its older catalog year', () => {
    setup()
    expect(screen.queryByRole('note')).not.toBeInTheDocument() // the catalog warning is on the planner page
    const box = screen.getByRole('combobox', { name: 'Search ASIs' })
    fireEvent.focus(box)
    const options = screen.getAllByRole('option')
    expect(options.every((o) => o.textContent?.includes('2025-2026'))).toBe(true) // each shows its year
    fireEvent.mouseDown(options[0])
    expect(screen.getAllByRole('button', { name: /^Remove / })).toHaveLength(1)
    // the minors box does not list ASIs
    fireEvent.blur(box)
    const minors = screen.getByRole('combobox', { name: 'Search minors' })
    fireEvent.focus(minors)
    expect(screen.getAllByRole('option').some((o) => o.textContent?.includes('2025-2026'))).toBe(false)
  })

  it('hides completed courses until the student says they have some', () => {
    setup()
    expect(screen.queryByRole('button', { name: 'Upload transcript' })).not.toBeInTheDocument()
    fireEvent.click(screen.getByLabelText(/I have already completed some courses/))
    expect(screen.getByRole('button', { name: 'Upload transcript' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: '+ Add a course by hand' })).toBeInTheDocument()
  })

  it('sends the courses the student listed as completed courses, and shows them in the summary', () => {
    const onSubmit = setup()
    pick(program(), MECH)
    fireEvent.click(screen.getByLabelText(/I have already completed some courses/))
    fireEvent.click(screen.getByRole('button', { name: '+ Add a course by hand' }))
    fireEvent.change(screen.getByLabelText('Course code'), { target: { value: 'MATH111' } })
    fireEvent.change(screen.getByLabelText('Credits'), { target: { value: '4' } })
    fireEvent.click(screen.getByRole('combobox', { name: 'When you took it' }))
    fireEvent.mouseDown(screen.getByRole('option', { name: 'Transfer credit' }))
    fireEvent.click(screen.getByRole('button', { name: 'Add course' }))
    expect(screen.getByLabelText('Your plan at a glance')).toHaveTextContent('1 course, 4 cr')
    fireEvent.click(screen.getByRole('button', { name: /Build my plan/ }))
    expect(onSubmit.mock.calls[0][0].student.completed_courses).toEqual([
      { code: 'MATH111', credits: 4, term: 'transfer', transfer_from: null },
    ])
  })

  it('sends no completed courses once the box is unticked, but keeps the list in case it is ticked again', () => {
    const onSubmit = setup()
    pick(program(), MECH)
    fireEvent.click(screen.getByLabelText(/I have already completed some courses/))
    fireEvent.click(screen.getByRole('button', { name: '+ Add a course by hand' }))
    fireEvent.change(screen.getByLabelText('Course code'), { target: { value: 'MATH111' } })
    fireEvent.click(screen.getByRole('combobox', { name: 'When you took it' }))
    fireEvent.mouseDown(screen.getByRole('option', { name: 'Transfer credit' }))
    fireEvent.click(screen.getByRole('button', { name: 'Add course' }))
    fireEvent.click(screen.getByLabelText(/I have already completed some courses/))
    expect(screen.getByLabelText('Your plan at a glance')).not.toHaveTextContent('1 course')
    fireEvent.click(screen.getByRole('button', { name: /Build my plan/ }))
    expect(onSubmit.mock.calls[0][0].student.completed_courses).toEqual([])
    fireEvent.click(screen.getByLabelText(/I have already completed some courses/))
    expect(screen.getByRole('list', { name: 'Completed courses' })).toHaveTextContent('MATH111')
  })

  it('shows summer terms in the projected graduation when summers are included', () => {
    setup()
    fireEvent.change(semesters(), { target: { value: '3' } })
    fireEvent.click(screen.getByLabelText('Include summer terms'))
    // Fall 2027, Spring 2028, Summer 2028
    expect(screen.getByText('Summer 2028')).toBeInTheDocument()
  })

  it('submits the request in the backend format', () => {
    const onSubmit = setup()
    pick(program(), MECH)
    fireEvent.click(screen.getByRole('button', { name: /Build my plan/ }))
    expect(onSubmit).toHaveBeenCalledTimes(1)
    expect(onSubmit.mock.calls[0][0]).toEqual({
      student: { degree_level: 'bachelor', programs: ['mechanical-engineering-bs'], catalog_year: '2026-2027', completed_courses: [] },
      semesters: 8,
      start_term: 'Fall 2027',
      include_summers: false,
      overrides: [],
    })
    // the second argument is the form itself, so the page can restore it later
    expect(onSubmit.mock.calls[0][1]).toMatchObject({ level: 'bachelor', programId: 'mechanical-engineering-bs', semesters: 8 })
  })

  it('switches summer terms on for a degree with a summer field session, and back off for another', () => {
    const onSubmit = setup()
    pick(program(), /Petroleum Engineering/)
    expect(screen.getByLabelText('Include summer terms')).toBeChecked()
    expect(semesters()).toHaveValue(11)
    expect(screen.getByRole('note')).toHaveTextContent('takes PEGN315, PEGN316 in summer')
    pick(program(), MECH)
    expect(screen.getByLabelText('Include summer terms')).not.toBeChecked()
    expect(semesters()).toHaveValue(8)
    expect(screen.queryByText(/in summer\./)).not.toBeInTheDocument()
    pick(program(), /Engineering Physics/)
    fireEvent.click(screen.getByRole('button', { name: /Build my plan/ }))
    expect(onSubmit.mock.calls[0][0]).toMatchObject({ include_summers: true, semesters: 11 })
  })

  it('does the same for Computer Science, and for a combined degree plans five years', () => {
    const onSubmit = setup()
    pick(program(), /Computer Science/)
    expect(screen.getByRole('note')).toHaveTextContent('takes CSCI370 in summer')
    expect(semesters()).toHaveValue(11)
    fireEvent.click(screen.getByRole('button', { name: 'Combined BS+MS' }))
    pick(program(), /Computer Science/)
    expect(semesters()).toHaveValue(14)
    fireEvent.click(screen.getByRole('button', { name: /Build my plan/ }))
    expect(onSubmit.mock.calls[0][0]).toMatchObject({ include_summers: true, semesters: 14 })
  })

  it('warns when summer terms are taken away from such a degree, and can put them back', () => {
    setup()
    pick(program(), /Petroleum Engineering/)
    fireEvent.click(screen.getByLabelText('Include summer terms'))
    expect(screen.getByRole('alert')).toHaveTextContent('not fit')
    fireEvent.click(screen.getByRole('button', { name: 'Include summers and plan 11 semesters' }))
    expect(screen.getByLabelText('Include summer terms')).toBeChecked()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('lists a major with tracks once, saying how many there are', () => {
    setup()
    fireEvent.click(program())
    const options = screen.getAllByRole('option').map((o) => o.textContent)
    expect(options.filter((o) => o!.includes('Computer Science'))).toEqual(['Bachelor of Science in Computer Science7 tracks'])
    expect(options).toContain('Bachelor of Science in Mechanical Engineering')
  })

  it('plans the general track by default, names the others, and lets the student pick one', () => {
    const onSubmit = setup()
    pick(program(), /Computer Science/)
    expect(program()).toHaveValue('Bachelor of Science in Computer Science')
    expect(screen.getByText(/Planning the General Track\. Other tracks: .*CS \+ Robotics and Intelligent Systems.*CS \+ Space/)).toBeInTheDocument()
    expect(screen.queryByRole('combobox', { name: 'Track' })).not.toBeInTheDocument()
    fireEvent.click(screen.getByLabelText('I am on a specific track'))
    pick(screen.getByRole('combobox', { name: 'Track' }), 'CS + Space')
    fireEvent.click(screen.getByRole('button', { name: /Build my plan/ }))
    expect(onSubmit.mock.calls[0][0].student.programs).toEqual(['cs-bs-space'])
    // unticking goes back to the general track
    fireEvent.click(screen.getByLabelText('I am on a specific track'))
    fireEvent.click(screen.getByRole('button', { name: /Build my plan/ }))
    expect(onSubmit.mock.calls[1][0].student.programs).toEqual(['cs-bs-general-track'])
  })

  it('asks for a track when a major has no general one', () => {
    const onSubmit = setup()
    pick(program(), /Applied Mathematics and Statistics/)
    expect(screen.queryByLabelText('I am on a specific track')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /Build my plan/ }))
    expect(onSubmit).not.toHaveBeenCalled()
    expect(screen.getByRole('alert')).toHaveTextContent('Choose your track.')
    pick(screen.getByRole('combobox', { name: 'Track' }), 'Data Science')
    fireEvent.click(screen.getByRole('button', { name: /Build my plan/ }))
    expect(onSubmit.mock.calls[0][0].student.programs).toEqual(['ams-bs-ds'])
  })

  it('finds a major by the name of one of its tracks', () => {
    setup()
    fireEvent.change(program(), { target: { value: 'robotics' } })
    expect(screen.getAllByRole('option').map((o) => o.textContent)).toContain('Bachelor of Science in Computer Science7 tracks')
  })

  it('shows the chosen track again when the student comes back', () => {
    const initial = { level: 'bachelor' as const, programId: 'cs-bs-space', addOnIds: [], season: 'Fall' as const, year: 2027, semesters: 11, includeSummers: true, hasCompleted: false, completed: [], files: [] }
    render(<SetupPage onSubmit={vi.fn()} initial={initial} today={NOV_2026} />)
    expect(program()).toHaveValue('Bachelor of Science in Computer Science')
    expect(screen.getByLabelText('I am on a specific track')).toBeChecked()
    expect(screen.getByRole('combobox', { name: 'Track' })).toHaveValue('CS + Space')
  })

  it('starts from the earlier choices when given them', () => {
    const initial = { level: 'master' as const, programId: '', addOnIds: [], season: 'Fall' as const, year: 2028, semesters: 5, includeSummers: true, hasCompleted: false, completed: [], files: [] }
    render(<SetupPage onSubmit={vi.fn()} initial={initial} today={NOV_2026} />)
    expect(screen.getByRole('button', { name: "Master's" })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByLabelText('Starting season')).toHaveValue('Fall')
    expect(screen.getByLabelText('Starting year')).toHaveValue('2028')
    expect(semesters()).toHaveValue(5)
    expect(screen.getByLabelText('Include summer terms')).toBeChecked()
  })
})
