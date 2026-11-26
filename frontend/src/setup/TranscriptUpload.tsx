import { useEffect, useId, useRef, useState } from 'react'
import { ApiError, parseTranscript } from '../api.ts'
import type { CompletedCourse } from '../types.ts'
import { Dropdown } from './Dropdown.tsx'
import {
  CATALOG,
  catalogCourse,
  fileKind,
  fileProblem,
  manualProblem,
  mergeCourses,
  TEMPLATE_CSV,
  termLabel,
  termOptions,
  toCourse,
  totalCredits,
  type ManualCourse,
  type UploadedFile,
} from './transcript.ts'
import './TranscriptUpload.css'

interface Props {
  courses: CompletedCourse[]
  /** the transcript files read so far (shown by name); kept by the form so they survive a trip to the planner */
  files?: UploadedFile[]
  onChange: (courses: CompletedCourse[], files: UploadedFile[]) => void
  /** the current year, for the list of semesters to pick from */
  thisYear: number
}

const EMPTY: ManualCourse = { code: '', credits: '', term: '', transferFrom: '' }

/** Completed courses: read them from a transcript file, check the list, fix it, or type them in. */
export function TranscriptUpload({ courses, files = [], onChange, thisYear }: Props) {
  const ids = { code: useId(), credits: useId(), from: useId(), codes: useId() }
  const fileInput = useRef<HTMLInputElement>(null)
  const controller = useRef<AbortController | null>(null)
  const [reading, setReading] = useState(false)
  const [problem, setProblem] = useState<string | null>(null)
  const [note, setNote] = useState<string | null>(null)
  const [over, setOver] = useState(false)
  const [adding, setAdding] = useState(false)
  const [entry, setEntry] = useState<ManualCourse>(EMPTY)
  const [entryProblem, setEntryProblem] = useState<string | null>(null)
  // credits filled in from the catalog, until the student types their own
  const [autoCredits, setAutoCredits] = useState(false)
  const [readingName, setReadingName] = useState<string | null>(null)
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
    setReadingName(file.name)
    controller.current = new AbortController()
    try {
      const found = await parseTranscript(file, controller.current.signal)
      const { merged, added } = mergeCourses(courses, found)
      const codes = merged.slice(courses.length).map((c) => c.code)
      // the same file read again replaces its chip instead of adding a second one
      const others = files.filter((f) => f.name !== file.name)
      onChange(merged, [...others, { name: file.name, kind: fileKind(file.name), found: found.length, added: codes }])
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
      setReadingName(null)
    }
  }

  const addByHand = () => {
    const bad = manualProblem(entry, courses)
    setEntryProblem(bad)
    if (bad) return
    onChange([...courses, toCourse(entry)], files)
    setEntry(EMPTY)
    setAutoCredits(false)
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
      {(files.length > 0 || readingName) && (
        <ul className="tu-files" aria-label="Uploaded files">
          {files.map((f) => (
            <li key={f.name} className="tu-file">
              <FileIcon kind={f.kind} />
              <span className="tu-file-text">
                <b title={f.name}>{f.name}</b>
                <small>
                  Uploaded &middot; {f.found} {f.found === 1 ? 'course' : 'courses'} found
                </small>
              </span>
              <button
                type="button"
                className="tu-x"
                aria-label={`Remove ${f.name}`}
                title="Remove this file and the courses it added"
                onClick={() => {
                  const drop = new Set(f.added)
                  onChange(
                    courses.filter((c) => !drop.has(c.code)),
                    files.filter((x) => x !== f),
                  )
                  setNote(null)
                }}
              >
                &times;
              </button>
            </li>
          ))}
          {readingName && !files.some((f) => f.name === readingName) && (
            <li className="tu-file reading">
              <FileIcon kind={fileKind(readingName)} />
              <span className="tu-file-text">
                <b title={readingName}>{readingName}</b>
                <small>Reading...</small>
              </span>
            </li>
          )}
        </ul>
      )}
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
            <button type="button" className="link" onClick={() => onChange([], [])}>
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
                <button type="button" className="tu-x" aria-label={`Remove ${c.code}`} onClick={() => onChange(courses.filter((x) => x.code !== c.code), files)}>
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
              <input
                id={ids.code}
                value={entry.code}
                placeholder="MATH111"
                autoComplete="off"
                list={ids.codes}
                aria-describedby={entry.code.trim() ? `${ids.code}-title` : undefined}
                onChange={(e) => {
                  const code = e.target.value
                  const hit = catalogCourse(code)
                  const fill = hit && (entry.credits.trim() === '' || autoCredits)
                  setEntry({ ...entry, code, credits: fill ? String(hit.credits) : autoCredits ? '' : entry.credits })
                  setAutoCredits(!!fill) // credits the catalog filled in are cleared again if the code stops matching
                }}
              />
              <datalist id={ids.codes}>
                {codeOptions(entry.code).map(([code, title]) => (
                  <option key={code} value={code}>
                    {title}
                  </option>
                ))}
              </datalist>
            </div>
            <div>
              <label htmlFor={ids.credits}>Credits</label>
              <input
                id={ids.credits}
                value={entry.credits}
                inputMode="decimal"
                placeholder="4"
                autoComplete="off"
                onChange={(e) => {
                  setEntry({ ...entry, credits: e.target.value })
                  setAutoCredits(false)
                }}
              />
            </div>
            <div className="tu-when">
              <div className="tu-lbl">When</div>
              <Dropdown searchable label="When you took it" placeholder="Choose..." options={terms} value={entry.term} onChange={(term) => setEntry({ ...entry, term })} />
            </div>
          </div>
          {entry.code.trim() && (
            <p className="tu-title" id={`${ids.code}-title`}>
              {catalogCourse(entry.code)?.title ?? 'Not in the Mines catalog. That is fine for transfer credit; check the code otherwise.'}
            </p>
          )}
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
                setAutoCredits(false)
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

/** Up to 40 catalog courses whose code starts with what the student typed, for the code field's suggestions. */
function codeOptions(typed: string): [string, string][] {
  const prefix = typed.replace(/\s+/g, '').toUpperCase()
  if (prefix.length < 2) return []
  const out: [string, string][] = []
  for (const [code, [title]] of Object.entries(CATALOG)) {
    if (code.startsWith(prefix)) out.push([code, title])
    if (out.length >= 40) break
  }
  return out
}

/** A small document icon with the file's kind on it: red for a PDF, green for a CSV. */
function FileIcon({ kind }: { kind: 'pdf' | 'csv' }) {
  return (
    <svg className={`tu-icon ${kind}`} width="30" height="36" viewBox="0 0 30 36" aria-hidden="true">
      <path className="tu-icon-page" d="M3 2h16l8 8v22a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2z" />
      <path className="tu-icon-fold" d="M19 2v6a2 2 0 0 0 2 2h6" />
      <rect className="tu-icon-band" x="0" y="17" width="24" height="11" rx="2" />
      <text x="12" y="25.5" textAnchor="middle">
        {kind.toUpperCase()}
      </text>
    </svg>
  )
}
