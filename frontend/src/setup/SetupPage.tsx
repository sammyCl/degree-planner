import { useId, useMemo, useRef, useState } from 'react'
import type { AgentRequest } from '../types.ts'
import { AddOnPicker } from './AddOnPicker.tsx'
import { Dropdown } from './Dropdown.tsx'
import { SegmentedControl } from './SegmentedControl.tsx'
import { defaultStart, semesterLabels, SEASONS, type Season } from './terms.ts'
import {
  addOns,
  allowsAddOns,
  buildRequest,
  CATALOG_YEAR,
  LEVELS,
  majorsFor,
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
  const ids = { major: useId(), semesters: useId() }
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
      },
  )
  const [submitted, setSubmitted] = useState(false)
  const errors = validateSetup(form)
  const shown = submitted ? errors : {}
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
  const allAddOns = useMemo(() => addOns(), [])
  // ASIs are only offered once they are stored for the student's catalog year (data/tools/build_frontend_options.py)
  const addOnNoun = allAddOns.some((a) => a.level === 'asi') ? 'minors and ASIs' : 'minors'
  const byId = new Map(allAddOns.map((a) => [a.id, a]))

  const submit = (e: React.FormEvent) => {
    e.preventDefault()
    setSubmitted(true)
    if (Object.keys(errors).length > 0) {
      ;(errors.programId ? majorRef : semestersRef).current?.focus()
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
              onChange={(programId) => patch({ programId })}
            />
            {shown.programId && (
              <p className="err" id={`${ids.major}-err`} role="alert">
                {shown.programId}
              </p>
            )}
          </div>

          {allowsAddOns(form.level) && (
            <div className="field">
              <div className="lbl">
                {addOnNoun === 'minors' ? 'Minors' : 'Minors and ASIs'} <span className="opt">optional, add as many as you like</span>
              </div>
              <AddOnPicker options={allAddOns} noun={addOnNoun} selected={form.addOnIds} onChange={(addOnIds) => patch({ addOnIds })} />
            </div>
          )}

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
