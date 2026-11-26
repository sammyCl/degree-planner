import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { useState } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { CompletedCourse } from '../types.ts'
import type { UploadedFile } from './transcript.ts'
import { TranscriptUpload } from './TranscriptUpload.tsx'

afterEach(() => vi.unstubAllGlobals())

const reply = (status: number, body: unknown) => ({ ok: status >= 200 && status < 300, status, json: async () => body })
const found: CompletedCourse[] = [
  { code: 'MATH111', credits: 4, term: 'Fall 2025', transfer_from: null },
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

  it('sends the file to the backend and lists what it found, with transfer credit worded plainly', async () => {
    const fetchMock = vi.fn().mockResolvedValue(reply(200, found))
    vi.stubGlobal('fetch', fetchMock)
    setup()
    upload()
    expect(await screen.findByText('MATH111')).toBeInTheDocument()
    expect(fetchMock.mock.calls[0][0]).toBe('/api/transcripts/parse')
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
    expect(await screen.findByRole('alert')).toHaveTextContent('Could not reach the backend')
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(reply(200, [])))
    upload()
    expect(await screen.findByText(/No courses were found in that file/)).toBeInTheDocument()
  })

  it('adds a second file to the list without repeating a course already there', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(reply(200, found)))
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
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(reply(200, found)))
    const mine = { code: 'CSCI101', credits: 3, term: 'Fall 2025', transfer_from: null }
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

  it('downloads a CSV template in the format the backend reads', () => {
    const create = vi.fn().mockReturnValue('blob:x')
    vi.stubGlobal('URL', { createObjectURL: create, revokeObjectURL: vi.fn() })
    setup()
    fireEvent.click(screen.getByRole('button', { name: 'Download a CSV template' }))
    expect(create).toHaveBeenCalledTimes(1)
  })
})
