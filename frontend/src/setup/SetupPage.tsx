import { useId, useMemo, useRef, useState } from 'react'
import type { AgentRequest } from '../types.ts'
import { AddOnPicker } from './AddOnPicker.tsx'
import { Dropdown } from './Dropdown.tsx'
import { SegmentedControl } from './SegmentedControl.tsx'
import { TranscriptUpload } from './TranscriptUpload.tsx'
import { totalCredits } from './transcript.ts'
import { defaultStart, semesterLabels, SEASONS, type Season } from './terms.ts'
import {
  ADD_ON_NAMES,
  addOns,
  addOnsOfKind,
  allowsAddOns,
  type AddOnKind,
  buildRequest,
  CATALOG_YEAR,
  LEVELS,
  majorsFor,
  NEEDS_SUMMER,
  SEMESTER_LIMITS,
  shortName,
  validateSetup,
  type Level,
  type SetupForm,
} from './validate.ts'
import './SetupPage.css'

interface Props {
  /** Called with the request to send and the form it came from, so the page can restore it on the way back. */
  onSubmit: (request: AgentRequest, form: SetupForm) => void
  /** The student's earlier choices, when they come back from the planner or an error. */
  initial?: SetupForm
  /** Injectable for tests; the current date is used otherwise. */
  today?: Date
}

export function SetupPage({ onSubmit, initial, today }: Props) {
  const [now] = useState(() => today ?? new Date())
  const ids = { major: useId(), semesters: useId(), completed: useId() }
  const start = useMemo(() => defaultStart(now), [now])
  const thisYear = now.getFullYear()
  const years = Array.from({ length: 6 }, (_, i) => thisYear + i)

  const [form, setForm] = useState<SetupForm>(
    () =>
      initial ?? {
        level: 'bachelor',
        programId: '',
        addOnIds: [],
        season: start.season,
        year: start.year,
        semesters: SEMESTER_LIMITS.bachelor.default,
        includeSummers: false,
        hasCompleted: false,
        completed: [],
        files: [],
      },
  )
  const [submitted, setSubmitted] = useState(false)
  // a transcript still being read: building now would leave its courses out of the plan
  const [reading, setReading] = useState(false)
  const [mustWait, setMustWait] = useState(false)
  const errors = validateSetup(form)
  const shown = submitted ? errors : {}
  /**
   * Choosing a degree that needs a summer field session switches summer terms on, with enough semesters to reach the
   * fourth spring; leaving it for another degree puts the level's usual choices back.
   */
  const chooseProgram = (programId: string) => {
    const count = NEEDS_SUMMER[programId]
    if (count !== undefined) patch({ programId, includeSummers: true, semesters: count })
    else if (NEEDS_SUMMER[form.programId] !== undefined)
      patch({ programId, includeSummers: false, semesters: SEMESTER_LIMITS[form.level].default })
    else patch({ programId })
  }
  const majorRef = useRef<HTMLInputElement>(null)
  const semestersRef = useRef<HTMLInputElement>(null)

  const patch = (changes: Partial<SetupForm>) => setForm((f) => ({ ...f, ...changes }))
  const setLevel = (level: Level) =>
    patch({
      level,
      programId: '',
      addOnIds: allowsAddOns(level) ? form.addOnIds : [],
      semesters: SEMESTER_LIMITS[level].default,
    })

  const limits = SEMESTER_LIMITS[form.level]
  const majors = majorsFor(form.level)
  const labels = Number.isInteger(form.semesters) && form.semesters >= 1 && form.semesters <= 60
    ? semesterLabels(form.season, form.year, form.semesters, form.includeSummers)
    : []
  const major = majors.find((m) => m.id === form.programId)
  const summerCount = NEEDS_SUMMER[form.programId]
  const needsSummer = summerCount !== undefined && (!form.includeSummers || form.semesters < summerCount)
  const allAddOns = useMemo(() => addOns(), [])
  const byId = new Map(allAddOns.map((a) => [a.id, a]))
  // minors, ASIs and certifications each get their own picker (a kind with no data stored is not shown)
  const kinds = (['minor', 'asi', 'certificate'] as const).filter((k) => addOnsOfKind(k).length > 0)
  const chosenOfKind = (kind: AddOnKind) => form.addOnIds.filter((id) => byId.get(id)?.level === kind)
  const setKind = (kind: AddOnKind, ids: string[]) =>
    patch({ addOnIds: [...form.addOnIds.filter((id) => byId.get(id)?.level !== kind), ...ids] })

  const submit = (e: React.FormEvent) => {
    e.preventDefault()
    setSubmitted(true)
    if (Object.keys(errors).length > 0) {
      ;(errors.programId ? majorRef : semestersRef).current?.focus()
      return
    }
    if (reading) {
      setMustWait(true)
      return
    }
    onSubmit(buildRequest(form), form)
  }

  const stepSemesters = (delta: number) => {
    const next = (Number.isInteger(form.semesters) ? form.semesters : limits.default) + delta
    patch({ semesters: Math.min(limits.max, Math.max(limits.min, next)) })
  }

  return (
    <main className="setup-wrap">
      <div>
        <div className="hero">
          <h2>
            Plan your path to <span className="grad">graduation</span>.
          </h2>
          <p>Tell us your program and when you start. We lay out every semester and check every prerequisite.</p>
        </div>

        <form className="panel form" onSubmit={submit} noValidate aria-label="Plan setup">
          <div className="field">
            <div className="lbl">Degree level</div>
            <SegmentedControl label="Degree level" options={LEVELS} value={form.level} onChange={setLevel} />
          </div>

          <div className="field">
            <label className="lbl" htmlFor={ids.major}>
              Program
            </label>
            <Dropdown
              id={ids.major}
              ref={majorRef}
              searchable
              placeholder="Select your program..."
              options={majors.map((m) => ({ value: m.id, label: m.name }))}
              value={form.programId}
              invalid={!!shown.programId}
              describedBy={shown.programId ? `${ids.major}-err` : undefined}
              onChange={chooseProgram}
            />
            {shown.programId && (
              <p className="err" id={`${ids.major}-err`} role="alert">
                {shown.programId}
              </p>
            )}
          </div>

          {allowsAddOns(form.level) &&
            kinds.map((kind) => (
              <div className="field" key={kind}>
                <div className="lbl">
                  {ADD_ON_NAMES[kind].many} <span className="opt">optional, add as many as you like</span>
                </div>
                <AddOnPicker
                  options={addOnsOfKind(kind)}
                  noun={ADD_ON_NAMES[kind].plural}
                  selected={chosenOfKind(kind)}
                  onChange={(ids) => setKind(kind, ids)}
                />
              </div>
            ))}

          <div className="field">
            <div className="lbl">
              Completed courses <span className="opt">optional</span>
            </div>
            <label className="check check-first">
              <input
                type="checkbox"
                checked={form.hasCompleted}
                aria-controls={ids.completed}
                onChange={(e) => patch({ hasCompleted: e.target.checked })}
              />
              I have already completed some courses, or I am a transfer student
            </label>
            {form.hasCompleted && (
              <div id={ids.completed} className="completed-box">
                <p className="completed-help">
                  Upload your transcript, or add the courses you finished one by one. Your plan then holds only the courses
                  you still need, starting {form.season} {form.year}.
                </p>
                <TranscriptUpload
                  courses={form.completed}
                  files={form.files}
                  onChange={(completed, files) => patch({ completed, files })}
                  thisYear={thisYear}
                  onReadingChange={(now) => {
                    setReading(now)
                    if (!now) setMustWait(false)
                  }}
                />
              </div>
            )}
          </div>

          <div className="field">
            <div className="lbl">Starting term</div>
            <div className="row">
              <Dropdown
                label="Starting season"
                options={SEASONS.map((s) => ({ value: s, label: s }))}
                value={form.season}
                onChange={(season) => patch({ season: season as Season })}
              />
              <Dropdown
                label="Starting year"
                options={years.map((y) => ({ value: String(y), label: String(y) }))}
                value={String(form.year)}
                onChange={(year) => patch({ year: Number(year) })}
              />
            </div>
            {shown.year && (
              <p className="err" role="alert">
                {shown.year}
              </p>
            )}
            <label className="check">
              <input
                type="checkbox"
                checked={form.includeSummers}
                onChange={(e) => patch({ includeSummers: e.target.checked })}
              />
              Include summer terms
            </label>
            {summerCount !== undefined && !needsSummer && (
              <p className="summer-hint ok" role="note">
                Summer terms are on and the plan has {form.semesters} semesters, because this degree has a summer field
                session.
              </p>
            )}
            {needsSummer && (
              <p className="summer-hint" role="alert">
                This degree has a summer field session. With these choices its courses will not fit unless you have already
                completed some of them.{' '}
                <button type="button" className="link" onClick={() => patch({ includeSummers: true, semesters: summerCount })}>
                  Include summers and plan {summerCount} semesters
                </button>
              </p>
            )}
          </div>

          <div className="field">
            <label className="lbl" htmlFor={ids.semesters}>
              Number of semesters <span className="opt">{limits.min} to {limits.max}</span>
            </label>
            <div className="stepper">
              <div className="ctl">
                <button type="button" aria-label="Fewer semesters" onClick={() => stepSemesters(-1)}>
                  &minus;
                </button>
                <input
                  id={ids.semesters}
                  ref={semestersRef}
                  type="number"
                  inputMode="numeric"
                  min={limits.min}
                  max={limits.max}
                  value={Number.isNaN(form.semesters) ? '' : form.semesters}
                  aria-invalid={!!shown.semesters}
                  aria-describedby={shown.semesters ? `${ids.semesters}-err` : undefined}
                  onChange={(e) => patch({ semesters: e.target.value === '' ? NaN : Number(e.target.value) })}
                />
                <button type="button" aria-label="More semesters" onClick={() => stepSemesters(1)}>
                  +
                </button>
              </div>
              <div className="terms" aria-hidden="true">
                {labels.slice(0, 18).map((l) => (
                  <i key={l} className={l.startsWith('Spring') ? 'sp' : l.startsWith('Summer') ? 'su' : ''} title={l} />
                ))}
              </div>
            </div>
            {shown.semesters && (
              <p className="err" id={`${ids.semesters}-err`} role="alert">
                {shown.semesters}
              </p>
            )}
          </div>

          {mustWait && (
            <p className="err" role="alert">
              Wait for your transcript to finish reading, so its courses are in your plan.
            </p>
          )}

          <button className="cta" type="submit">
            Build my plan
            <svg className="arr" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M5 12h14m-6-6l6 6-6 6" />
            </svg>
          </button>
        </form>
      </div>

      <aside className="panel preview" aria-label="Your plan at a glance">
        <h3>Your plan at a glance</h3>
        <dl>
          <div className="pv-row">
            <dt>Degree</dt>
            <dd>{LEVELS.find((l) => l.value === form.level)?.label}</dd>
          </div>
          <div className="pv-row">
            <dt>Program</dt>
            <dd>{major ? major.name : <span className="muted">Not chosen yet</span>}</dd>
          </div>
          {allowsAddOns(form.level) && (
            <div className="pv-row">
              <dt>Add-ons</dt>
              <dd>
                {form.addOnIds.length
                  ? form.addOnIds.map((id) => shortName(byId.get(id)?.name ?? id)).join(', ')
                  : <span className="muted">None</span>}
              </dd>
            </div>
          )}
          <div className="pv-row">
            <dt>Completed</dt>
            <dd>
              {form.hasCompleted && form.completed.length ? (
                `${form.completed.length} ${form.completed.length === 1 ? 'course' : 'courses'}, ${totalCredits(form.completed)} cr`
              ) : (
                <span className="muted">None</span>
              )}
            </dd>
          </div>
          <div className="pv-row">
            <dt>Starts</dt>
            <dd>{`${form.season} ${form.year}`}</dd>
          </div>
        </dl>
        <div className="grad-card">
          <small>Projected graduation</small>
          <b>{labels.length ? labels[labels.length - 1] : '...'}</b>
          <small>
            {labels.length} semester{labels.length === 1 ? '' : 's'} &middot; catalog {CATALOG_YEAR}
          </small>
        </div>
        <p className="tip">Department-approved electives are left open in the plan. Confirm those with your advisor.</p>
      </aside>
    </main>
  )
}
