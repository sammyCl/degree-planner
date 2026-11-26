import { useEffect, useId, useRef, useState } from 'react'
import { ApiError, readTranscript } from '../api.ts'
import type { CompletedCourse, UnmatchedCourse } from '../types.ts'
import { Dropdown } from './Dropdown.tsx'
import {
  CATALOG,
  catalogCourse,
  completedTitle,
  displayCode,
  fileKind,
  fileProblem,
  manualProblem,
  mergeCourses,
  nextPlaceholder,
  normalizeCode,
  sourceLabel,
  TEMPLATE_CSV,
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
  // the files themselves, by name, so a file can be read again once the student says which school it is from
  const [fileObjects, setFileObjects] = useState<ReadonlyMap<string, File>>(() => new Map())
  const [changingSchool, setChangingSchool] = useState<string | null>(null)
  const terms = termOptions(thisYear)

  useEffect(() => () => controller.current?.abort(), [])

  const read = async (file: File, school: string | null = null) => {
    setNote(null)
    const bad = fileProblem(file)
    if (bad) {
      setProblem(bad)
      return
    }
    setProblem(null)
    setReading(true)
    setReadingName(file.name)
    setChangingSchool(null)
    controller.current = new AbortController()
    try {
      const result = await readTranscript(file, school, controller.current.signal)
      setFileObjects((m) => new Map(m).set(file.name, file))
      // the same file read again replaces what it added before, and its chip
      const earlier = files.find((f) => f.name === file.name)
      const drop = new Set(earlier?.added ?? [])
      const base = courses.filter((c) => !drop.has(c.code))
      const { merged, added } = mergeCourses(base, result.courses)
      const others = files.filter((f) => f.name !== file.name)
      const found = result.courses.length + result.unmatched.length
      onChange(merged, [
        ...others,
        {
          name: file.name,
          kind: fileKind(file.name),
          found,
          added: merged.slice(base.length).map((c) => c.code),
          school: result.school,
          fromMines: result.from_mines,
          system: result.system,
          unmatched: result.unmatched,
          skipped: result.skipped,
          tesUrl: result.tes_url,
          knownSchools: result.known_schools,
        },
      ])
      setNote(
        found === 0
          ? 'No courses were found in that file. Check it, or add your courses by hand.'
          : `Found ${found} ${found === 1 ? 'course' : 'courses'}${added < result.courses.length ? `, ${added} new` : ''}.${result.unmatched.length ? ` ${result.unmatched.length} still need a Mines equivalent.` : ''} Check the list below.`,
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

  /** A course from another school becomes the Mines course the student chose (or is skipped, with `mines` null). */
  const resolve = (file: UploadedFile, picks: { course: UnmatchedCourse; mines: string | null }[]) => {
    const taken = new Set(courses.map((c) => c.code))
    const fresh: CompletedCourse[] = []
    for (const { course, mines } of picks) {
      if (!mines) continue
      let code = normalizeCode(mines)
      if (/^[A-Z]{2,5}\dXX$/.test(code)) code = nextPlaceholder(code, taken)
      if (taken.has(code)) continue
      taken.add(code)
      fresh.push({
        code,
        credits: course.credits,
        term: 'transfer',
        transfer_from: file.school ?? null,
        title: `${course.code} ${course.title}`.trim(),
        in_progress: course.in_progress,
      })
    }
    const done = new Set(picks.map((p) => p.course))
    onChange(
      [...courses, ...fresh],
      files.map((f) =>
        f === file ? { ...f, added: [...f.added, ...fresh.map((c) => c.code)], unmatched: (f.unmatched ?? []).filter((u) => !done.has(u)) } : f,
      ),
    )
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
                {f.kind === 'pdf' && (
                  <small className={f.school ? 'tu-school' : 'tu-school unknown'}>
                    {f.school ? `${f.fromMines ? 'Mines transcript' : `From ${f.school}`}` : 'School not recognised'}
                    {fileObjects.has(f.name) && (
                      <>
                        {' '}
                        &middot;{' '}
                        <button type="button" className="link" onClick={() => setChangingSchool(changingSchool === f.name ? null : f.name)}>
                          {f.school ? 'Not right?' : 'Choose the school'}
                        </button>
                      </>
                    )}
                  </small>
                )}
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
      {files.map((f) => {
        const file = fileObjects.get(f.name)
        const pickSchool = file && (changingSchool === f.name || (!f.school && f.kind === 'pdf'))
        const unmatched = f.unmatched ?? []
        if (!pickSchool && unmatched.length === 0 && !(f.skipped ?? []).length) return null
        return (
          <div className="tu-review" key={`review-${f.name}`}>
            {pickSchool && (
              <div className="tu-school-pick">
                <span>Which school is {f.name} from?</span>
                <Dropdown
                  searchable
                  label={`School for ${f.name}`}
                  placeholder="Choose the school..."
                  options={(f.knownSchools ?? []).map((name) => ({ value: name, label: name }))}
                  value={f.school ?? ''}
                  onChange={(school) => void read(file, school)}
                />
                <small>
                  Mines and the 15 Colorado community colleges have saved course lists. For another school, keep it as it is and
                  look each course up in TES below.
                </small>
              </div>
            )}
            {unmatched.length > 0 && (
              <UnmatchedList
                file={f}
                courses={unmatched}
                onResolve={(picks) => resolve(f, picks)}
              />
            )}
            {(f.skipped ?? []).length > 0 && (
              <details className="tu-skipped">
                <summary>
                  {f.skipped!.length} {f.skipped!.length === 1 ? 'row earns' : 'rows earn'} no Mines credit
                </summary>
                <ul>
                  {f.skipped!.map((line) => (
                    <li key={line}>{line}</li>
                  ))}
                </ul>
              </details>
            )}
          </div>
        )
      })}
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
                <span className="tu-code">{displayCode(c.code)}</span>
                <span className="tu-cr">{c.credits} cr</span>
                <span className="tu-what" title={completedTitle(c)}>
                  {completedTitle(c)}
                </span>
                <span className="tu-term">
                  {c.in_progress && <span className="tu-ip">In progress</span>}
                  {sourceLabel(c)}
                </span>
                <button type="button" className="tu-x" aria-label={`Remove ${displayCode(c.code)}${displayCode(c.code) !== c.code ? ` (${completedTitle(c)})` : ''}`} onClick={() => onChange(courses.filter((x) => x.code !== c.code), files)}>
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

/** Courses from another school with no Mines equivalent yet: the student picks one (after a TES look-up) or skips it. */
function UnmatchedList({ file, courses, onResolve }: { file: UploadedFile; courses: UnmatchedCourse[]; onResolve: (picks: { course: UnmatchedCourse; mines: string | null }[]) => void }) {
  const listId = useId()
  const [typed, setTyped] = useState<Record<string, string>>({})
  const suggested = courses.filter((c) => c.suggestion)
  return (
    <div className="tu-unmatched" role="group" aria-label={`Courses that need a Mines equivalent from ${file.name}`}>
      <div className="tu-unmatched-head">
        <b>
          {courses.length} {courses.length === 1 ? 'course needs' : 'courses need'} a Mines equivalent
        </b>
        {file.tesUrl && (
          <a className="tu-tes" href={file.tesUrl} target="_blank" rel="noreferrer noopener">
            Look them up in TES
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M7 17L17 7M9 7h8v8" />
            </svg>
          </a>
        )}
      </div>
      <p className="tu-unmatched-help">
        {file.system
          ? `${file.school} is a ${file.system} college. These courses are not on Mines' preapproved list; an academic course usually transfers as a free elective.`
          : `Mines has no saved list for ${file.school ?? 'this school'}. Search for the school in Mines' Transfer Evaluation System (TES), find each course, and enter the Mines course it became.`}{' '}
        TES results are unofficial; the registrar decides when your official transcript arrives.
      </p>
      <datalist id={listId}>
        <option value="FREE1XX">Free elective</option>
        <option value="HASS2XX">CAS/HASS mid-level elective</option>
        <option value="CSM2XX">Success &amp; Wellness</option>
      </datalist>
      <ul>
        {courses.map((c) => {
          const key = `${c.code}|${c.title}`
          const value = typed[key] ?? ''
          const known = value.trim() && (catalogCourse(value) || /^[A-Z]{2,5}\dXX$/i.test(value.replace(/\s+/g, '')))
          return (
            <li key={key}>
              <span className="tu-their">
                <b>{c.code}</b> {c.title} <small>{c.credits} cr{c.in_progress ? ', in progress' : ''}</small>
              </span>
              <input
                aria-label={`Mines course for ${c.code}`}
                placeholder="Mines course, e.g. MATH111"
                list={listId}
                value={value}
                onChange={(e) => setTyped({ ...typed, [key]: e.target.value })}
              />
              <button type="button" className="tu-pick small" disabled={!known} onClick={() => onResolve([{ course: c, mines: value }])}>
                Add
              </button>
              {c.suggestion && (
                <button type="button" className="link" onClick={() => onResolve([{ course: c, mines: c.suggestion }])}>
                  {c.suggestion === 'FREE1XX' ? 'Free elective' : c.suggestion}
                </button>
              )}
              <button type="button" className="tu-x" aria-label={`Skip ${c.code}`} title="No Mines credit for this course" onClick={() => onResolve([{ course: c, mines: null }])}>
                &times;
              </button>
            </li>
          )
        })}
      </ul>
      {suggested.length > 1 && (
        <button type="button" className="link" onClick={() => onResolve(suggested.map((c) => ({ course: c, mines: c.suggestion })))}>
          Count all {suggested.length} as free electives
        </button>
      )}
    </div>
  )
}
