import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { useState } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { CompletedCourse, TranscriptReading } from '../types.ts'
import type { UploadedFile } from './transcript.ts'
import { TranscriptUpload } from './TranscriptUpload.tsx'

afterEach(() => vi.unstubAllGlobals())

const reply = (status: number, body: unknown) => ({ ok: status >= 200 && status < 300, status, json: async () => body })
/** What POST /transcripts/read answers: a Mines transcript with these courses, unless `extra` says otherwise. */
const reading = (courses: CompletedCourse[], extra: Partial<TranscriptReading> = {}): TranscriptReading => ({
  school: 'Colorado School of Mines',
  from_mines: true,
  system: null,
  courses,
  unmatched: [],
  skipped: [],
  tes_url: 'https://tes.collegesource.com/publicview/x',
  known_schools: ['Colorado School of Mines', 'Front Range Community College'],
  ...extra,
})
const found: CompletedCourse[] = [
  { code: 'MATH111', credits: 4, term: 'Fall 2024', transfer_from: null },
  { code: 'PHGN100', credits: 4, term: 'transfer', transfer_from: 'Front Range CC' },
]

/** The component with its own state, and the latest list so a test can read what the form would send. */
function setup(initial: CompletedCourse[] = []) {
  const latest = { current: initial }
  function Host() {
    const [courses, setCourses] = useState(initial)
    const [files, setFiles] = useState<UploadedFile[]>([])
    latest.current = courses
    return (
      <TranscriptUpload
        courses={courses}
        files={files}
        onChange={(next, nextFiles) => {
          setCourses(next)
          setFiles(nextFiles)
        }}
        thisYear={2026}
      />
    )
  }
  render(<Host />)
  return latest
}

const upload = (name = 'transcript.csv', size = 400) => {
  const file = new File(['x'.repeat(size)], name, { type: 'text/csv' })
  fireEvent.change(screen.getByLabelText('Transcript file'), { target: { files: [file] } })
}
const list = () => within(screen.getByRole('list', { name: 'Completed courses' }))

describe('TranscriptUpload', () => {
  it('shows nothing but the upload area until there are courses', () => {
    setup()
    expect(screen.getByRole('button', { name: 'Upload transcript' })).toBeInTheDocument()
    expect(screen.queryByRole('list', { name: 'Completed courses' })).not.toBeInTheDocument()
    expect(screen.getByText(/file itself is not saved/)).toBeInTheDocument()
  })

  it('can stop a read, and adds nothing', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn((_url: string, init: RequestInit) =>
        new Promise((_resolve, reject) => init.signal!.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError'))))),
    )
    const latest = setup()
    upload()
    fireEvent.click(screen.getByRole('button', { name: 'Stop reading' }))
    expect(await screen.findByText(/Stopped reading transcript.csv. Nothing was added./)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Upload transcript' })).toBeEnabled()
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
    expect(latest.current).toEqual([])
  })

  it('sends the file to the backend and lists what it found, with transfer credit worded plainly', async () => {
    const fetchMock = vi.fn().mockResolvedValue(reply(200, reading(found)))
    vi.stubGlobal('fetch', fetchMock)
    setup()
    upload()
    expect(await screen.findByText('MATH111')).toBeInTheDocument()
    expect(fetchMock.mock.calls[0][0]).toBe('/api/transcripts/read')
    expect(list().getByText('Transfer credit (Front Range CC)')).toBeInTheDocument()
    expect(screen.getByText('2 courses, 8 credits')).toBeInTheDocument()
    expect(screen.getByText(/Found 2 courses/)).toBeInTheDocument()
  })

  it('does not send a file of the wrong type or a huge one, and says why', () => {
    const fetchMock = vi.fn()
    vi.stubGlobal('fetch', fetchMock)
    setup()
    upload('notes.docx')
    expect(screen.getByRole('alert')).toHaveTextContent('Upload a .csv or .pdf file.')
    upload('big.pdf', 6 * 1024 * 1024)
    expect(screen.getByRole('alert')).toHaveTextContent('over 5 MB')
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('shows the backend\'s reason when it cannot read the file, and keeps the list as it was', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(reply(400, { detail: "row 2: credits 'x' is not a number" })))
    const latest = setup([found[0]])
    upload()
    expect(await screen.findByRole('alert')).toHaveTextContent("We could not read that file: row 2: credits 'x' is not a number")
    expect(latest.current).toEqual([found[0]])
  })

  it('says so when the backend cannot be reached, and when no courses were found', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('Failed to fetch')))
    setup()
    upload()
    expect(await screen.findByRole('alert')).toHaveTextContent("Can't reach the server")
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(reply(200, reading([]))))
    upload()
    expect(await screen.findByText(/No courses were found in that file/)).toBeInTheDocument()
  })

  it('adds a second file to the list without repeating a course already there', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(reply(200, reading(found))))
    const latest = setup([found[0]])
    upload()
    await waitFor(() => expect(latest.current).toHaveLength(2))
    expect(screen.getByText(/Found 2 courses, 1 new/)).toBeInTheDocument()
  })

  it('lets the student remove a course or clear the whole list', () => {
    const latest = setup(found)
    fireEvent.click(screen.getByRole('button', { name: 'Remove MATH111' }))
    expect(latest.current.map((c) => c.code)).toEqual(['PHGN100'])
    fireEvent.click(screen.getByRole('button', { name: 'Clear all' }))
    expect(latest.current).toEqual([])
  })

  it('adds a course typed by hand, and explains a mistake before adding', () => {
    const latest = setup()
    fireEvent.click(screen.getByRole('button', { name: '+ Add a course by hand' }))
    fireEvent.change(screen.getByLabelText('Course code'), { target: { value: 'csci 128' } })
    fireEvent.change(screen.getByLabelText('Credits'), { target: { value: '3' } })
    fireEvent.click(screen.getByRole('button', { name: 'Add course' }))
    expect(screen.getByRole('alert')).toHaveTextContent('Choose when you took it.')
    expect(latest.current).toEqual([])

    fireEvent.click(screen.getByRole('combobox', { name: 'When you took it' }))
    fireEvent.mouseDown(screen.getByRole('option', { name: 'Spring 2026' }))
    fireEvent.click(screen.getByRole('button', { name: 'Add course' }))
    expect(latest.current).toEqual([{ code: 'CSCI128', credits: 3, term: 'Spring 2026', transfer_from: null }])
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('shows the uploaded file by name with a PDF icon, and removing it removes only the courses it added', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(reply(200, reading(found))))
    const mine = { code: 'CSCI101', credits: 3, term: 'Fall 2024', transfer_from: null }
    const latest = setup([mine])
    upload('my-transcript.pdf')
    const files = within(await screen.findByRole('list', { name: 'Uploaded files' }))
    expect(files.getByText('my-transcript.pdf')).toBeInTheDocument()
    expect(files.getByText('PDF')).toBeInTheDocument()
    expect(files.getByText(/2 courses found/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Remove my-transcript.pdf' }))
    expect(latest.current).toEqual([mine])
    expect(screen.queryByRole('list', { name: 'Uploaded files' })).not.toBeInTheDocument()
  })

  it('fills in the title and credits of a catalog course typed by hand', () => {
    setup()
    fireEvent.click(screen.getByRole('button', { name: '+ Add a course by hand' }))
    fireEvent.change(screen.getByLabelText('Course code'), { target: { value: 'math111' } })
    expect(screen.getByLabelText('Credits')).toHaveValue('4')
    expect(screen.getByText(/Calculus/, { selector: '.tu-title' })).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Course code'), { target: { value: 'ENGL101' } })
    expect(screen.getByLabelText('Credits')).toHaveValue('') // the catalog's credits go when the code stops matching
    expect(screen.getByText(/Not in the Mines catalog/)).toBeInTheDocument()
  })

  it('shows the school, in-progress courses, placeholder credit by its title, and rows with no credit', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        reply(
          200,
          reading(
            [
              { code: 'FREE1XX-1', credits: 3, term: 'transfer', transfer_from: 'IB credit', title: 'Free Elective-Art History' },
              { code: 'CSCI261', credits: 3, term: 'Fall 2024', transfer_from: null, title: 'PROGRAMMING CONCEPTS', in_progress: true },
            ],
            { skipped: ['PHGN 200 PHYSICS II: grade F, no credit'] },
          ),
        ),
      ),
    )
    setup()
    upload('t.pdf')
    expect(await screen.findByText(/Mines transcript/)).toBeInTheDocument()
    const rows = list()
    expect(rows.getByText('FREE 1XX')).toBeInTheDocument()
    expect(rows.getByText('Free Elective-Art History')).toBeInTheDocument()
    expect(rows.getByText('IB credit')).toBeInTheDocument()
    expect(rows.getByText('In progress')).toBeInTheDocument()
    expect(screen.getByText('1 row earns no Mines credit')).toBeInTheDocument()
  })

  it('asks which school when it cannot tell, and reads the file again for that school', async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(reply(200, reading([], { school: null, from_mines: false, unmatched: [] })))
      .mockResolvedValueOnce(reply(200, reading([{ code: 'MATH111', credits: 5, term: 'transfer', transfer_from: 'Front Range Community College' }], { school: 'Front Range Community College', from_mines: false })))
    vi.stubGlobal('fetch', fetchMock)
    const latest = setup()
    upload('other.pdf')
    expect(await screen.findByText(/School not recognised/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('combobox', { name: 'School for other.pdf' }))
    fireEvent.mouseDown(screen.getByRole('option', { name: 'Front Range Community College' }))
    await waitFor(() => expect(latest.current.map((c) => c.code)).toEqual(['MATH111']))
    const body = fetchMock.mock.calls[1][1].body as FormData
    expect(body.get('school')).toBe('Front Range Community College')
  })

  it('lets the student give each unmatched course its Mines equivalent, take the pre-filled suggestion, or skip it', async () => {
    const u = (code: string, suggestion: string | null) => ({ code, title: `Course ${code}`, credits: 3, term: 'transfer', in_progress: false, suggestion, reason: 'Look it up in TES', suggested_by: suggestion ? ('rule' as const) : null })
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        reply(200, reading([], { school: 'Example State University', from_mines: false, unmatched: [u('MATH 1401', null), u('ENG 1021', 'FREE1XX'), u('ART 1000', null)] })),
      ),
    )
    const latest = setup()
    upload('esu.pdf')
    const group = await screen.findByRole('group', { name: /need a Mines equivalent/ })
    expect(within(group).getByRole('link', { name: /Look them up in TES/ })).toHaveAttribute('href', 'https://tes.collegesource.com/publicview/x')
    expect(within(group).getByLabelText('Mines course for ENG 1021')).toHaveValue('FREE1XX') // pre-filled
    const adds = within(group).getAllByRole('button', { name: 'Add' })
    expect(adds[0]).toBeDisabled() // MATH 1401 has no suggestion and nothing typed yet
    fireEvent.change(within(group).getByLabelText('Mines course for MATH 1401'), { target: { value: 'math111' } })
    fireEvent.click(adds[0])
    fireEvent.click(within(group).getAllByRole('button', { name: 'Add' })[0]) // ENG 1021, now first
    fireEvent.click(within(group).getByRole('button', { name: 'Skip ART 1000' }))
    expect(latest.current).toEqual([
      { code: 'MATH111', credits: 3, term: 'transfer', transfer_from: 'Example State University', title: 'MATH 1401 Course MATH 1401', in_progress: false },
      { code: 'FREE1XX-1', credits: 3, term: 'transfer', transfer_from: 'Example State University', title: 'ENG 1021 Course ENG 1021', in_progress: false },
    ])
    expect(screen.queryByRole('group', { name: /need a Mines equivalent/ })).not.toBeInTheDocument()
  })

  it('shows each suggestion with how sure it is and why, and accepts them all at once', async () => {
    const s = (code: string, title: string, suggestion: string | null, extra = {}) => ({ code, title, credits: 4, term: 'transfer', in_progress: false, suggestion, reason: 'TES', suggested_by: suggestion ? ('claude' as const) : null, ...extra })
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        reply(
          200,
          reading([], {
            school: 'University of Colorado Denver',
            from_mines: false,
            unmatched: [
              s('MATH 1401', 'Calculus I', 'MATH111', { suggestion_title: 'Calculus for Scientists and Engineers I', confidence: 'high', suggestion_reason: 'Both are first-semester calculus.' }),
              s('CSCI 1410', 'Fundamentals of Computing', 'CSCI128', { suggestion_title: 'Computer Science for STEM', confidence: 'medium' }),
              s('ART 1000', 'Drawing', null),
            ],
          }),
        ),
      ),
    )
    const latest = setup()
    upload('cud.pdf')
    const group = await screen.findByRole('group', { name: /need a Mines equivalent/ })
    expect(group).toHaveTextContent('Strong match')
    expect(group).toHaveTextContent('Suggested: MATH111 Calculus for Scientists and Engineers I. Both are first-semester calculus.')
    expect(group).toHaveTextContent('Likely match')
    expect(group).toHaveTextContent('Suggestions are guesses: check them in TES')
    fireEvent.click(within(group).getByRole('button', { name: 'Accept all 2 suggestions' }))
    expect(latest.current.map((c) => c.code)).toEqual(['MATH111', 'CSCI128'])
    // the one with no suggestion is still there to look up
    expect(within(screen.getByRole('group', { name: /need a Mines equivalent/ })).getByText('ART 1000')).toBeInTheDocument()
  })

  it('adds a Mines lecture and its lab together, with the credits split by the catalog', async () => {
    const pair = { code: 'CHEM 3411 + CHEM 3418', title: 'Organic Chemistry I (with Organic Chemistry Lab I)', credits: 5, term: 'transfer', in_progress: false, suggestion: 'CHGN221+CHGN223', reason: 'TES', suggested_by: 'claude' as const, suggestion_title: 'Organic Chemistry I with Organic Chemistry I Laboratory', confidence: 'high' as const }
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(reply(200, reading([], { school: 'Example State University', from_mines: false, unmatched: [pair] }))))
    const latest = setup()
    upload('esu.pdf')
    const group = await screen.findByRole('group', { name: /need a Mines equivalent/ })
    expect(group).toHaveTextContent('Suggested: CHGN221 + CHGN223')
    fireEvent.click(within(group).getByRole('button', { name: 'Add' }))
    // CHGN221 is 3 credits and CHGN223 is 1 in the catalog, so the 5 transfer credits split 3.75 and 1.25
    expect(latest.current.map((c) => [c.code, c.credits])).toEqual([['CHGN221', 3.75], ['CHGN223', 1.25]])
  })

  it('renumbers placeholder credit from a second transcript instead of dropping it', async () => {
    const free = (n: number, title: string): CompletedCourse => ({ code: `FREE1XX-${n}`, credits: 3, term: 'transfer', transfer_from: 'IB credit', title })
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(reply(200, reading([free(1, 'Art History')]))))
    const latest = setup([free(1, 'Music')])
    upload('second.pdf')
    await waitFor(() => expect(latest.current.map((c) => c.code)).toEqual(['FREE1XX-1', 'FREE1XX-2']))
  })

  it('says when Claude read a transcript, and tells the student before they upload', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(reply(200, reading([], { school: 'Example State University', from_mines: false, read_by: 'claude', unmatched: [] }))),
    )
    setup()
    expect(screen.getByText(/read by Claude \(Anthropic's AI\) after\s+your name, student ID, birth date/)).toBeInTheDocument()
    upload('esu.pdf')
    expect(await screen.findByText(/read by Claude/, { selector: '.tu-claude' })).toBeInTheDocument()
  })

  it('shows the reader\'s notice, for example for a scanned PDF', async () => {
    const notice = 'This PDF has no text in it (it looks like a scanned image), so it could not be read.'
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(reply(200, reading([], { school: null, from_mines: false, notice }))))
    setup()
    upload('scan.pdf')
    expect(await screen.findByRole('note')).toHaveTextContent('looks like a scanned image')
  })

  it('shows the file being read, with what is happening, until the answer comes', async () => {
    let answer: (value: unknown) => void = () => {}
    vi.stubGlobal('fetch', vi.fn().mockReturnValue(new Promise((resolve) => (answer = resolve))))
    setup()
    upload('slow.pdf')
    const chip = screen.getByText('slow.pdf').closest('li')!
    expect(chip).toHaveAttribute('aria-busy', 'true')
    expect(within(chip).getByRole('status')).toHaveTextContent('Opening your file...')
    expect(screen.getByRole('button', { name: 'Reading your transcript...' })).toBeDisabled()
    answer(reply(200, reading([found[0]])))
    expect(await screen.findByText(/Uploaded/)).toBeInTheDocument()
    expect(screen.queryByText('Opening your file...')).not.toBeInTheDocument()
  })

  it('downloads a CSV template in the format the backend reads', () => {
    const create = vi.fn().mockReturnValue('blob:x')
    vi.stubGlobal('URL', { createObjectURL: create, revokeObjectURL: vi.fn() })
    setup()
    fireEvent.click(screen.getByRole('button', { name: 'Download a CSV template' }))
    expect(create).toHaveBeenCalledTimes(1)
  })
})
