import { displayCode } from '../setup/transcript.ts'
import type { Plan, PlannedCourse } from '../types.ts'
import type { CompletedColumn } from './completed.ts'
import { categoryOf, courseLabel } from './courseLabel.ts'
import { formatCredits, subjectColor } from './graph.ts'

interface Props {
  columns: CompletedColumn[]
  /** codes of courses the transcript lists as in progress */
  inProgress: Set<string>
  /** the validator's answer for the completed courses on their own: labels them (Core, Free elective, ...) */
  donePlan: Plan | null
  /** more than a semester's worth: the student can fold them away */
  collapsible: boolean
  open: boolean
  onToggle: () => void
}

const Check = ({ size = 12 }: { size?: number }) => (
  <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M5 12l5 5L20 7" />
  </svg>
)

/** Most courses in one completed column; more continue in the next column. */
export const COLUMN_HEIGHT = 8

const chunks = <T,>(items: T[], size: number): T[][] =>
  Array.from({ length: Math.max(1, Math.ceil(items.length / size)) }, (_, k) => items.slice(k * size, (k + 1) * size))

const Clock = () => (
  <svg width={12} height={12} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <circle cx="12" cy="12" r="9" />
    <path d="M12 7v5l3 2" />
  </svg>
)

/** The courses the student already finished, on the left of the board: a column per term, or a folded rail. */
export function CompletedColumns({ columns, inProgress, donePlan, collapsible, open, onToggle }: Props) {
  const courses = columns.flatMap((c) => c.courses)
  const credits = columns.reduce((sum, c) => sum + c.credits, 0)
  const summary = `${courses.length} ${courses.length === 1 ? 'course' : 'courses'}, ${formatCredits(credits)} cr`

  if (collapsible && !open) {
    // folded: a card the width of a narrow column, read left to right
    return (
      <section className="done-fold" aria-label={`Completed courses: ${summary}`}>
        <div className="done-fold-h">
          <span className="done-fold-ic">
            <Check size={14} />
          </span>
          <b>Completed</b>
        </div>
        <div className="done-fold-total">
          <b>{formatCredits(credits)}</b> credits
          <small>
            {courses.length} {courses.length === 1 ? 'course' : 'courses'}
          </small>
        </div>
        <ul className="done-fold-list">
          {columns.slice(0, 6).map((col) => (
            <li key={col.key}>
              <span className={col.inProgress ? 'ip' : ''} title={col.from ? `${col.label} from ${col.from}` : col.label}>
                {col.from ?? col.label}
                {col.inProgress ? ' (in progress)' : ''}
              </span>
              <em>{formatCredits(col.credits)} cr</em>
            </li>
          ))}
          {columns.length > 6 && <li className="more">and {columns.length - 6} more</li>}
        </ul>
        <button type="button" className="done-fold-btn" onClick={onToggle} aria-expanded={false} aria-label={`Show completed courses (${summary})`}>
          Show completed courses
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M5 12h14m-6-6l6 6-6 6" />
          </svg>
        </button>
      </section>
    )
  }

  return (
    <div className="done-group" role="group" aria-label={`Completed courses: ${summary}`}>
      <div className="done-group-h">
        <span className="done-badge">
          <Check /> Completed
        </span>
        <span className="done-sum">{summary}</span>
        {collapsible && (
          <button type="button" className="link done-hide" onClick={onToggle} aria-expanded>
            Hide completed courses
          </button>
        )}
      </div>
      <div className="done-cols">
        {columns.flatMap((col, i) => {
          const [term, year] = /^(Fall|Spring|Summer) \d{4}$/.test(col.label) ? col.label.split(' ') : [col.label, '']
          const name = col.from ? `${col.label} from ${col.from}` : col.label
          const state = col.inProgress ? 'in progress' : 'completed'
          // a long column continues in the next one, so no column is taller than COLUMN_HEIGHT courses
          return chunks(col.courses, COLUMN_HEIGHT).map((part, n) => (
            <section
              className={`sem done${n > 0 ? ' cont' : ''}`}
              key={`${col.key}:${n}`}
              aria-label={n === 0 ? `${name}, ${state}` : `${name}, ${state}, continued (${n + 1})`}
              style={{ ['--col' as string]: i }}
            >
              <div className="sem-h">
                <b>{col.from ? 'Transfer' : term}</b>
                {year && <span className="sem-year">{year}</span>}
                {n > 0 && <span className="sem-cont">continued</span>}
                {n === 0 && col.inProgress && <span className="sem-ip">In progress</span>}
              </div>
              {col.from && (
                <div className="sem-from" title={col.from}>
                  {col.from}
                </div>
              )}
              {n === 0 && (
                <div className="meter done">
                  <span className="meter-track">
                    <i style={{ width: `${Math.min(100, (col.credits / 18) * 100)}%` }} />
                  </span>
                  <span className="meter-val">{formatCredits(col.credits)} cr</span>
                </div>
              )}
              {part.map((c, row) => (
                <CompletedCard key={c.course_id} course={c} inProgress={inProgress.has(c.code)} donePlan={donePlan} col={i} row={row} />
              ))}
            </section>
          ))
        })}
      </div>
    </div>
  )
}

function CompletedCard({ course, inProgress, donePlan, col, row }: { course: PlannedCourse; inProgress: boolean; donePlan: Plan | null; col: number; row: number }) {
  const label = donePlan ? courseLabel(donePlan, course.course_id) : null
  const code = displayCode(course.code)
  return (
    <div
      className={`card completed${inProgress ? ' in-progress' : ''}`}
      data-id={course.course_id}
      aria-label={`${code} ${course.title}, ${formatCredits(course.credits)} credits, ${inProgress ? 'in progress' : 'completed'}${label ? `, ${label.primary}` : ''}`}
      style={{ ['--col' as string]: col, ['--row' as string]: row, ['--sub' as string]: subjectColor(course.code) }}
    >
      <div className="card-row">
        <span className="card-dot" />
        <span className="card-code">{code}</span>
        <span className="card-cr">{formatCredits(course.credits)} cr</span>
        {label && <span className={`card-tag cat-${categoryOf(label.primary)}`}>{label.primary}</span>}
      </div>
      <div className="card-title">{course.title}</div>
      <div className="card-done">
        {inProgress ? (
          <>
            <Clock /> In progress
          </>
        ) : (
          <>
            <Check /> Completed
          </>
        )}
      </div>
    </div>
  )
}
