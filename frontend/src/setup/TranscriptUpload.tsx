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
  /** told when a file starts and stops being read, so the form can wait for it */
  onReadingChange?: (reading: boolean) => void
}

const EMPTY: ManualCourse = { code: '', credits: '', term: '', transferFrom: '' }

/** Completed courses: read them from a transcript file, check the list, fix it, or type them in. */
export function TranscriptUpload({ courses, files = [], onChange, thisYear, onReadingChange }: Props) {
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
  // a read takes seconds, and the student may change the list meanwhile: its answer is added to the latest one
  const latest = useRef({ courses, files, onReadingChange })
  useEffect(() => {
    latest.current = { courses, files, onReadingChange }
  })

  useEffect(
    () => () => {
      controller.current?.abort()
      latest.current.onReadingChange?.(false)
    },
    [],
  )

  const read = async (file: File, school: string | null = null, ignored: string[] = []) => {
    setNote(null)
    if (readingName) {
      setProblem(`Still reading ${readingName}. Add the next file when it is done.`)
      return
    }
    const bad = fileProblem(file)
    if (bad) {
      setProblem(bad)
      return
    }
    setProblem(null)
    setReading(true)
    setReadingName(file.name)
    onReadingChange?.(true)
    setChangingSchool(null)
    controller.current = new AbortController()
    try {
      const result = await readTranscript(file, school, controller.current.signal)
      const { courses, files } = latest.current
      setProblem(null) // such as "still reading", which is no longer true
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
          readByClaude: result.read_by === 'claude',
          notice: result.notice ?? null,
        },
      ])
      const said =
        found === 0
          ? 'No courses were found in that file. Check it, or add your courses by hand.'
          : `Found ${found} ${found === 1 ? 'course' : 'courses'}${added < result.courses.length ? `, ${added} new` : ''}.${result.unmatched.length ? ` ${result.unmatched.length} still need a Mines equivalent.` : ''} Check the list below.`
      setNote(ignored.length ? `${said} One file at a time: add ${ignored.join(', ')} next.` : said)
    } catch (error) {
      if (error instanceof ApiError && error.kind === 'aborted') {
        setNote(`Stopped reading ${file.name}. Nothing was added.`)
        return
      }
      setProblem(
        error instanceof ApiError && error.kind === 'invalid_request'
          ? `We could not read that file: ${error.message}`
          : error instanceof ApiError && error.kind === 'network'
            ? error.message
            : `Something went wrong reading that file.${error instanceof ApiError ? ` ${error.message}` : ''} You can add your courses by hand instead.`,
      )
    } finally {
      setReading(false)
      setReadingName(null)
      latest.current.onReadingChange?.(false)
    }
  }

  /** A course from another school becomes the Mines course the student chose (or is skipped, with `mines` null). */
  const resolve = (file: UploadedFile, picks: { course: UnmatchedCourse; mines: string | null }[]) => {
    const taken = new Set(courses.map((c) => c.code))
    const fresh: CompletedCourse[] = []
    // a course that adds nothing because its Mines course is already listed stays, so the student can change it
    const kept = new Set<UnmatchedCourse>()
    const repeats: string[] = []
    for (const { course, mines } of picks) {
      if (!mines) continue
      const before = fresh.length
      // "CHGN221+CHGN223" is a Mines lecture and its lab: both are added, the credits split by the catalog's credits
      const parts = mines.split('+').map((part) => normalizeCode(part)).filter(Boolean)
      const catalogCredits = parts.map((part) => catalogCourse(part)?.credits ?? 0)
      const total = catalogCredits.reduce((a, b) => a + b, 0)
      parts.forEach((part, i) => {
        let code = part
        if (/^[A-Z]{2,5}\dXX$/.test(code)) code = nextPlaceholder(code, taken)
        if (taken.has(code)) return
        taken.add(code)
        const credits = parts.length === 1 || total === 0 ? course.credits / parts.length : (course.credits * catalogCredits[i]) / total
        fresh.push({
          code,
          credits: Math.round(credits * 100) / 100,
          term: 'transfer',
          transfer_from: file.school ?? null,
          title: `${course.code} ${course.title}`.trim(),
          in_progress: course.in_progress,
        })
      })
      if (parts.length > 0 && fresh.length === before) {
        kept.add(course)
        repeats.push(`${parts.join(' + ')} is already in the list, so ${course.code} was not added. Enter a different Mines course or skip it.`)
      }
    }
    setProblem(repeats.length ? repeats.join(' ') : null)
    const done = new Set(picks.map((p) => p.course).filter((c) => !kept.has(c)))
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

  // Enter in one of these fields means "add this course", never "submit the setup form"
  const onEnter = (action: () => void) => (e: React.KeyboardEvent) => {
    if (e.key !== 'Enter' || e.defaultPrevented) return // an open dropdown has already used the key
    if (!(e.target instanceof HTMLInputElement)) return
    e.preventDefault()
    action()
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
          const [file, ...others] = Array.from(e.dataTransfer.files ?? [])
          if (file)
            void read(
              file,
              null,
              others.map((f) => f.name),
            )
        }}
      >
        <button type="button" className="tu-pick" disabled={reading} onClick={() => fileInput.current?.click()}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M12 16V4m0 0l-4 4m4-4l4 4M4 16v3a1 1 0 001 1h14a1 1 0 001-1v-3" />
          </svg>
          {reading ? 'Reading your transcript...' : 'Upload transcript'}
        </button>
        <span className="tu-or">or drop a .csv or .pdf here</span>
        {reading && (
          <button type="button" className="link" onClick={() => controller.current?.abort()}>
            Stop reading
          </button>
        )}
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
        We read course codes, credits and terms. The file itself is not saved; only the courses in the list below are sent to the planner.
        A Mines transcript is read on our server. A transcript in another layout is read by Claude (Anthropic&apos;s AI) after
        your name, student ID, birth date and contact details are removed.{' '}
        <button type="button" className="link" onClick={downloadTemplate}>
          Download a CSV template
        </button>
      </p>
      {(files.length > 0 || readingName) && (
        <ul className="tu-files" aria-label="Uploaded files">
          {files.filter((f) => f.name !== readingName).map((f) => (
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
                    {f.readByClaude && <span className="tu-claude"> &middot; read by Claude</span>}
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
          {readingName && <ReadingChip name={readingName} />}
        </ul>
      )}
      {files.map((f) => {
        const file = fileObjects.get(f.name)
        const pickSchool = file && (changingSchool === f.name || (!f.school && f.kind === 'pdf'))
        const unmatched = f.unmatched ?? []
        if (!pickSchool && unmatched.length === 0 && !(f.skipped ?? []).length && !f.notice) return null
        return (
          <div className="tu-review" key={`review-${f.name}`}>
            {f.notice && (
              <p className="tu-notice" role="note">
                {f.notice}
              </p>
            )}
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
        <div className="tu-add" onKeyDown={onEnter(addByHand)}>
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

const CONFIDENCE = { high: 'Strong match', medium: 'Likely match', low: 'A guess' } as const

/** A Mines code the page can add: a catalog course, or placeholder credit such as FREE1XX. */
const addable = (value: string): boolean =>
  !!value.trim() &&
  value.split('+').every((part) => !!catalogCourse(part) || /^[A-Z]{2,5}\dXX$/.test(normalizeCode(part)))

/**
 * Courses from another school with no saved Mines equivalent. Each box is pre-filled with a suggestion (a guess from
 * the course title, or the free-elective rule); the student checks it in TES and adds it, changes it, or skips it.
 */
function UnmatchedList({ file, courses, onResolve }: { file: UploadedFile; courses: UnmatchedCourse[]; onResolve: (picks: { course: UnmatchedCourse; mines: string | null }[]) => void }) {
  const listId = useId()
  const [typed, setTyped] = useState<Record<string, string>>({})
  const keyOf = (c: UnmatchedCourse) => `${c.code}|${c.title}`
  const valueOf = (c: UnmatchedCourse) => typed[keyOf(c)] ?? c.suggestion ?? ''
  const ready = courses.filter((c) => addable(valueOf(c)))
  const guessed = courses.some((c) => c.suggested_by === 'claude')
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
          ? `${file.school} is a ${file.system} college. These courses are not on Mines' preapproved list.`
          : `Mines has no saved list for ${file.school ?? 'this school'}.`}{' '}
        {guessed
          ? 'We filled in a suggested Mines course for each one from its title. Suggestions are guesses: check them in TES, change any that are wrong, then add them.'
          : 'Search for the school in TES, find each course, and enter the Mines course it became.'}{' '}
        The registrar decides when your official transcript arrives.
      </p>
      <datalist id={listId}>
        <option value="FREE1XX">Free elective</option>
        <option value="HASS2XX">CAS/HASS mid-level elective</option>
        <option value="CSM2XX">Success &amp; Wellness</option>
      </datalist>
      <ul>
        {courses.map((c) => {
          const key = keyOf(c)
          const value = valueOf(c)
          const changed = typed[key] !== undefined && typed[key] !== (c.suggestion ?? '')
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
                onKeyDown={(e) => {
                  if (e.key !== 'Enter') return
                  e.preventDefault()
                  if (addable(value)) onResolve([{ course: c, mines: value }])
                }}
              />
              <button type="button" className="tu-pick small" disabled={!addable(value)} onClick={() => onResolve([{ course: c, mines: value }])}>
                Add
              </button>
              {c.suggestion !== 'FREE1XX' ? (
                <button type="button" className="link" onClick={() => onResolve([{ course: c, mines: 'FREE1XX' }])}>
                  Free elective
                </button>
              ) : (
                <span />
              )}
              <button type="button" className="tu-x" aria-label={`Skip ${c.code}`} title="No Mines credit for this course" onClick={() => onResolve([{ course: c, mines: null }])}>
                &times;
              </button>
              {c.suggestion && !changed && (
                <span className="tu-suggest">
                  {c.suggested_by === 'claude' && c.confidence && <em className={`conf ${c.confidence}`}>{CONFIDENCE[c.confidence]}</em>}
                  Suggested: <b>{displayCode(c.suggestion)}</b> {c.suggestion_title ?? catalogCourse(c.suggestion)?.title ?? ''}
                  {c.suggested_by === 'rule' ? ' (Mines treats unlisted academic courses as free electives)' : ''}
                  {c.suggestion_reason ? `. ${c.suggestion_reason}` : ''}
                </span>
              )}
            </li>
          )
        })}
      </ul>
      {ready.length > 1 && (
        <button type="button" className="tu-pick small tu-accept" onClick={() => onResolve(ready.map((c) => ({ course: c, mines: valueOf(c) })))}>
          Accept all {ready.length} suggestions
        </button>
      )}
    </div>
  )
}

const READING_STEPS = ['Opening your file', 'Finding your courses', 'Working out the layout', 'Matching courses to Mines']

/** The file being read: a scanning line over its icon, a moving bar, and what is happening now. */
function ReadingChip({ name }: { name: string }) {
  const [step, setStep] = useState(0)
  const [slow, setSlow] = useState(false)
  useEffect(() => {
    const steps = setInterval(() => setStep((n) => Math.min(n + 1, READING_STEPS.length - 1)), 1800)
    const late = setTimeout(() => setSlow(true), 7000)
    return () => {
      clearInterval(steps)
      clearTimeout(late)
    }
  }, [])
  return (
    <li className="tu-file reading" aria-busy="true">
      <span className="tu-scan">
        <FileIcon kind={fileKind(name)} />
        <i aria-hidden="true" />
      </span>
      <span className="tu-file-text">
        <b title={name}>{name}</b>
        <small role="status" key={step} className="tu-step">
          {READING_STEPS[step]}...
        </small>
        {slow && <small className="tu-slow">An unfamiliar layout can take up to 20 seconds.</small>}
        <span className="tu-bar" aria-hidden="true">
          <i />
        </span>
      </span>
    </li>
  )
}
