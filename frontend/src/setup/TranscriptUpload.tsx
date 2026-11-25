import { useEffect, useId, useRef, useState } from 'react'
import { ApiError, parseTranscript } from '../api.ts'
import type { CompletedCourse } from '../types.ts'
import { Dropdown } from './Dropdown.tsx'
import {
  fileProblem,
  manualProblem,
  mergeCourses,
  TEMPLATE_CSV,
  termLabel,
  termOptions,
  toCourse,
  totalCredits,
  type ManualCourse,
} from './transcript.ts'
import './TranscriptUpload.css'

interface Props {
  courses: CompletedCourse[]
  onChange: (courses: CompletedCourse[]) => void
  /** the current year, for the list of semesters to pick from */
  thisYear: number
}

const EMPTY: ManualCourse = { code: '', credits: '', term: '', transferFrom: '' }

/** Completed courses: read them from a transcript file, check the list, fix it, or type them in. */
export function TranscriptUpload({ courses, onChange, thisYear }: Props) {
  const ids = { code: useId(), credits: useId(), from: useId() }
  const fileInput = useRef<HTMLInputElement>(null)
  const controller = useRef<AbortController | null>(null)
  const [reading, setReading] = useState(false)
  const [problem, setProblem] = useState<string | null>(null)
  const [note, setNote] = useState<string | null>(null)
  const [over, setOver] = useState(false)
  const [adding, setAdding] = useState(false)
  const [entry, setEntry] = useState<ManualCourse>(EMPTY)
  const [entryProblem, setEntryProblem] = useState<string | null>(null)
  const terms = termOptions(thisYear)

  useEffect(() => () => controller.current?.abort(), [])

  const read = async (file: File) => {
    setNote(null)
    const bad = fileProblem(file)
    if (bad) {
      setProblem(bad)
      return
    }
    setProblem(null)
    setReading(true)
    controller.current = new AbortController()
    try {
      const found = await parseTranscript(file, controller.current.signal)
      const { merged, added } = mergeCourses(courses, found)
      onChange(merged)
      setNote(
        found.length === 0
          ? 'No courses were found in that file. Check it, or add your courses by hand.'
          : `Found ${found.length} ${found.length === 1 ? 'course' : 'courses'}${added < found.length ? `, ${added} new` : ''}. Check the list below.`,
      )
    } catch (error) {
      if (error instanceof ApiError && error.kind === 'aborted') return
      setProblem(
        error instanceof ApiError && error.kind === 'invalid_request'
          ? `We could not read that file: ${error.message}`
          : error instanceof ApiError && error.kind === 'network'
            ? error.message
            : 'Something went wrong reading that file. You can add your courses by hand instead.',
      )
    } finally {
      setReading(false)
    }
  }

  const addByHand = () => {
    const bad = manualProblem(entry, courses)
    setEntryProblem(bad)
    if (bad) return
    onChange([...courses, toCourse(entry)])
    setEntry(EMPTY)
    setNote(null)
  }

  const downloadTemplate = () => {
    const url = URL.createObjectURL(new Blob([TEMPLATE_CSV], { type: 'text/csv' }))
    const link = document.createElement('a')
    link.href = url
    link.download = 'transcript-template.csv'
    link.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="tu">
      <div
        className={over ? 'tu-drop over' : 'tu-drop'}
        onDragOver={(e) => {
          e.preventDefault()
          setOver(true)
        }}
        onDragLeave={() => setOver(false)}
        onDrop={(e) => {
          e.preventDefault()
          setOver(false)
          const file = e.dataTransfer.files?.[0]
          if (file) void read(file)
        }}
      >
        <button type="button" className="tu-pick" disabled={reading} onClick={() => fileInput.current?.click()}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M12 16V4m0 0l-4 4m4-4l4 4M4 16v3a1 1 0 001 1h14a1 1 0 001-1v-3" />
          </svg>
          {reading ? 'Reading...' : 'Upload transcript'}
        </button>
        <span className="tu-or">or drop a .csv or .pdf here</span>
        <input
          ref={fileInput}
          type="file"
          accept=".csv,.pdf,text/csv,application/pdf"
          hidden
          aria-label="Transcript file"
          onChange={(e) => {
            const file = e.target.files?.[0]
            e.target.value = '' // so the same file can be chosen again
            if (file) void read(file)
          }}
        />
      </div>
      <p className="tu-hint">
        We read course codes, credits and terms. The file itself is not saved; only the courses in the list below are sent to the planner.{' '}
        <button type="button" className="link" onClick={downloadTemplate}>
          Download a CSV template
        </button>
      </p>
      {reading && (
        <p className="tu-note" role="status">
          Reading your file...
        </p>
      )}
      {problem && (
        <p className="err" role="alert">
          {problem}
        </p>
      )}
      {note && !problem && (
        <p className="tu-note" role="status">
          {note}
        </p>
      )}

      {courses.length > 0 && (
        <div className="tu-list">
          <div className="tu-head">
            <b>
              {courses.length} {courses.length === 1 ? 'course' : 'courses'}, {totalCredits(courses)} credits
            </b>
            <button type="button" className="link" onClick={() => onChange([])}>
              Clear all
            </button>
          </div>
          <ul aria-label="Completed courses">
            {courses.map((c) => (
              <li key={c.code}>
                <span className="tu-code">{c.code}</span>
                <span className="tu-cr">{c.credits} cr</span>
                <span className="tu-term">
                  {termLabel(c.term)}
                  {c.transfer_from ? ` (${c.transfer_from})` : ''}
                </span>
                <button type="button" className="tu-x" aria-label={`Remove ${c.code}`} onClick={() => onChange(courses.filter((x) => x.code !== c.code))}>
                  &times;
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      {adding ? (
        <div className="tu-add">
          <div className="tu-add-row">
            <div>
              <label htmlFor={ids.code}>Course code</label>
              <input id={ids.code} value={entry.code} placeholder="MATH111" autoComplete="off" onChange={(e) => setEntry({ ...entry, code: e.target.value })} />
            </div>
            <div>
              <label htmlFor={ids.credits}>Credits</label>
              <input id={ids.credits} value={entry.credits} inputMode="decimal" placeholder="4" autoComplete="off" onChange={(e) => setEntry({ ...entry, credits: e.target.value })} />
            </div>
            <div className="tu-when">
              <div className="tu-lbl">When</div>
              <Dropdown searchable label="When you took it" placeholder="Choose..." options={terms} value={entry.term} onChange={(term) => setEntry({ ...entry, term })} />
            </div>
          </div>
          {entry.term === 'transfer' && (
            <div className="tu-from">
              <label htmlFor={ids.from}>Sending school (optional)</label>
              <input id={ids.from} value={entry.transferFrom} autoComplete="off" onChange={(e) => setEntry({ ...entry, transferFrom: e.target.value })} />
            </div>
          )}
          {entryProblem && (
            <p className="err" role="alert">
              {entryProblem}
            </p>
          )}
          <div className="tu-add-actions">
            <button type="button" className="tu-pick" onClick={addByHand}>
              Add course
            </button>
            <button
              type="button"
              className="link"
              onClick={() => {
                setAdding(false)
                setEntryProblem(null)
              }}
            >
              Done
            </button>
          </div>
        </div>
      ) : (
        <button type="button" className="link tu-open" onClick={() => setAdding(true)}>
          + Add a course by hand
        </button>
      )}
    </div>
  )
}
