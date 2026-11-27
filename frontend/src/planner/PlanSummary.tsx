import { useMemo, useState, type ReactNode } from 'react'
import { catalogCourse, completedTitle, displayCode } from '../setup/transcript.ts'
import type { Plan } from '../types.ts'
import { completedCredits } from './completed.ts'
import { formatCredits } from './graph.ts'
import {
  buildChecklist,
  buildChecks,
  buildCompletedChecklist,
  coursesFor,
  firstSentence,
  readExplanation,
  splitChoice,
  type ChecklistRow,
  type ChecklistSection,
} from './summary.ts'

interface Props {
  plan: Plan
  /** what the planning assistant wrote about the plan; used only when it sent no choices and checks lists */
  explanation?: string
  /** the assistant's choices where the requirements left it open, one per item (AgentResponse.choices) */
  choices?: string[]
  /** what the assistant says to confirm with an advisor, one per item (AgentResponse.checks) */
  checks?: string[]
  /** the validator's check of the completed courses on their own, for "Already completed"; null until it answers */
  donePlan?: Plan | null
  /** whether that check is still running, or failed (then only the totals are shown) */
  doneState?: 'loading' | 'ready' | 'failed'
}

const Tick = ({ ok }: { ok: boolean }) => (
  <svg className={ok ? 'req-icon ok' : 'req-icon bad'} width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    {ok ? <path d="M5 12l5 5L20 7" /> : <path d="M6 6l12 12M18 6L6 18" />}
  </svg>
)

/** The first `limit` items, and a button for the rest. */
function ShowMore<T>({ items, limit, render, noun }: { items: T[]; limit: number; render: (item: T, i: number) => ReactNode; noun: string }) {
  const [all, setAll] = useState(false)
  const shown = all ? items : items.slice(0, limit)
  return (
    <>
      {shown.map(render)}
      {items.length > limit && (
        <li className="more-row">
          <button type="button" className="link more-btn" onClick={() => setAll((a) => !a)} aria-expanded={all}>
            {all ? 'Show fewer' : `Show ${items.length - limit} more ${noun}`}
          </button>
        </li>
      )}
    </>
  )
}

/** A list of courses, hidden until the student asks for it. */
function CourseToggle({ courses, label }: { courses: { code: string; title: string }[]; label: string }) {
  const [open, setOpen] = useState(false)
  if (courses.length === 0) return null
  return (
    <>
      <button
        type="button"
        className="link course-toggle"
        aria-expanded={open}
        aria-label={`${open ? 'Hide' : 'See'} the courses for ${label}`}
        onClick={() => setOpen((o) => !o)}
      >
        {open ? 'hide' : `${label.startsWith('your') ? 'See ' : ''}${courses.length} ${courses.length === 1 ? 'course' : 'courses'}`}
      </button>
      {open && <CourseChips courses={courses} />}
    </>
  )
}

/** The courses, as small chips under the row they belong to. */
function CourseChips({ courses }: { courses: { code: string; title: string }[] }) {
  return (
    <ul className="course-chips">
      {courses.map((c) => (
        <li key={c.code} title={c.title}>
          <b>{displayCode(c.code)}</b> {c.title}
        </li>
      ))}
    </ul>
  )
}

/** One requirement: its name opens the courses that fill it, below the row. */
function RequirementRow({ row, plan, partial }: { row: ChecklistRow; plan: Plan | null; partial?: boolean }) {
  const [open, setOpen] = useState(false)
  const courses = plan ? coursesFor(plan, row) : []
  return (
    <li className={`req-row ${row.met ? 'met' : partial ? 'part' : row.confirm ? 'ask' : 'unmet'}`}>
      <span className="req-line">
        {row.confirm && !partial ? (
          <span className="req-icon ask" role="img" aria-label="Confirm with your advisor">
            ?
          </span>
        ) : row.met || !partial ? (
          <Tick ok={row.met} />
        ) : (
          <span className="req-icon part" aria-hidden="true" />
        )}
        <span className={`req-dot cat-${row.category}`} aria-hidden="true" />
        {courses.length > 0 ? (
          <button
            type="button"
            className="req-name req-toggle"
            aria-expanded={open}
            aria-label={`${open ? 'Hide' : 'See'} the courses for ${row.name}`}
            title={`${courses.length} ${courses.length === 1 ? 'course' : 'courses'}`}
            onClick={() => setOpen((o) => !o)}
          >
            {row.name}
            <svg className={open ? 'chev open' : 'chev'} width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M9 6l6 6-6 6" />
            </svg>
          </button>
        ) : (
          <span className="req-name">{row.name}</span>
        )}
        {row.detail && <span className="req-detail">{row.detail}</span>}
      </span>
      {open && <CourseChips courses={courses} />}
    </li>
  )
}

function Checklist({ sections, plan, partial }: { sections: ChecklistSection[]; plan: Plan | null; partial?: boolean }) {
  return (
    <>
      {sections.map((section) => (
        <div className="req-section" key={section.title}>
          <div className="req-title">{section.title}</div>
          <ul className="req-list">
            {section.rows.map((row: ChecklistRow) => (
              <RequirementRow key={row.name} row={row} plan={plan} partial={partial} />
            ))}
          </ul>
        </div>
      ))}
    </>
  )
}

const TAGS = { confirm: 'Check', warning: 'Warning', info: 'Note', advisor: 'Ask your advisor' } as const

/** One note. The assistant's longer ones show their first sentence and the rest behind "more"; ours are short and say what to do, so they show whole. */
function Note({ tag, title, text }: { tag: keyof typeof TAGS; title?: string; text: string }) {
  const [open, setOpen] = useState(false)
  const { head, rest } = tag === 'advisor' ? firstSentence(text) : { head: text, rest: '' }
  return (
    <li className={`check-item ${tag}`}>
      <span className="check-tag">{TAGS[tag]}</span>
      <span className="check-text">
        {title && <b>{title}: </b>}
        {head}
        {rest && open && ` ${rest}`}
        {rest && (
          <button type="button" className="link more-inline" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
            {open ? 'less' : 'more'}
          </button>
        )}
      </span>
    </li>
  )
}

/** One choice the assistant made: "CS electives · 6 courses", the courses behind a click; a sentence otherwise. */
function Choice({ text }: { text: string }) {
  const [open, setOpen] = useState(false)
  const parts = splitChoice(text)
  if (!parts.heading) {
    const { head, rest } = firstSentence(parts.text)
    return (
      <li className="choice-item">
        {head}
        {rest && open && ` ${rest}`}
        {rest && (
          <button type="button" className="link more-inline" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
            {open ? 'less' : 'more'}
          </button>
        )}
      </li>
    )
  }
  const courses = parts.codes.map((code) => ({ code, title: catalogCourse(code)?.title ?? '' }))
  return (
    <li className="choice-item">
      <span className="choice-line">
        <b>{parts.heading}</b>
        <CourseToggle courses={courses} label={parts.heading} />
      </span>
      {parts.text && <span className="choice-note">{parts.text}</span>}
    </li>
  )
}

/** A short summary of the plan under the board: what is met, what is done, what to look at, and what was chosen. */
export function PlanSummary({ plan, explanation, choices, checks, donePlan, doneState }: Props) {
  // starts closed under the board so the flowchart comes first, but the top few lines stay visible as a peek
  const [open, setOpen] = useState(false)
  const checklist = useMemo(() => buildChecklist(plan), [plan])
  const flagChecks = useMemo(() => buildChecks(plan), [plan])
  // the assistant's own lists; older plans only have its free text, read the old way (tables left out)
  const notes = useMemo(() => {
    if ((choices && choices.length) || (checks && checks.length)) return { choices: choices ?? [], checks: checks ?? [] }
    if (!explanation) return { choices: [] as string[], checks: [] as string[] }
    const read = readExplanation(explanation, plan)
    return {
      choices: read.choices.flatMap((b) => (b.type === 'p' ? [b.text] : b.items)),
      checks: read.checks,
    }
  }, [choices, checks, explanation, plan])
  const completed = plan.student.completed_courses
  const doneChecklist = useMemo(() => (donePlan ? buildCompletedChecklist(donePlan) : []), [donePlan])
  const transfer = completed.filter((c) => c.term === 'transfer' || c.term === 'aplcredit').length
  const inProgress = completed.filter((c) => c.in_progress).length
  const notesToCheck = [
    ...flagChecks.map((c) => ({ tag: c.kind, title: c.title, text: c.text })),
    ...notes.checks.map((text) => ({ tag: 'advisor' as const, title: '', text })),
  ]

  return (
    <section className="about" aria-label="About this plan">
      <div className="about-head">
        <h2>About this plan</h2>
        <button type="button" className="link" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
          {open ? 'Hide' : 'Show'}
        </button>
      </div>
      <div className={open ? 'about-body' : 'about-body peek'} inert={!open}>
        <div className="about-grid">
          <div className="about-card c-req">
            <h3>Degree requirements</h3>
            <Checklist sections={checklist} plan={plan} />
          </div>

          {completed.length > 0 && (
            <div className="about-card c-done">
              <h3>Already completed</h3>
              <p className="done-total">
                <b>{formatCredits(completedCredits(plan))}</b> of {formatCredits(plan.summary.total_credits_required)} credits
                <span>
                  {completed.length} {completed.length === 1 ? 'course' : 'courses'}
                  {transfer > 0 ? ` · ${transfer} transfer, AP or IB` : ''}
                  {inProgress > 0 ? ` · ${inProgress} in progress` : ''}
                </span>
              </p>
              {doneState === 'loading' && (
                <div className="skeleton" aria-busy="true" aria-label="Loading which requirements they meet">
                  <i />
                  <i />
                </div>
              )}
              {donePlan && doneChecklist.length > 0 && <Checklist sections={doneChecklist} plan={donePlan} partial />}
              {donePlan && doneChecklist.length === 0 && (
                <p className="about-none">They add to your credit total but do not fill a specific requirement.</p>
              )}
              <div className="done-courses">
                <CourseToggle courses={completed.map((c) => ({ code: c.code, title: completedTitle(c) }))} label="your completed courses" />
              </div>
            </div>
          )}

          <div className="about-card c-check">
            <h3>Things to check</h3>
            {notesToCheck.length === 0 ? (
              <p className="about-none">
                <Tick ok /> Nothing needs your attention.
              </p>
            ) : (
              <ul className="check-list">
                <ShowMore items={notesToCheck} limit={3} noun="to check" render={(n, i) => <Note key={i} tag={n.tag} title={n.title} text={n.text} />} />
              </ul>
            )}
          </div>

          {notes.choices.length > 0 && (
            <div className="about-card c-choice">
              <h3>Choices I made</h3>
              <ul className="choice-list">
                <ShowMore items={notes.choices} limit={4} noun="choices" render={(text, i) => <Choice key={i} text={text} />} />
              </ul>
              <p className="choice-foot">You can change any of these: drag courses on the board, or edit your setup.</p>
            </div>
          )}
        </div>
      </div>
    </section>
  )
}
