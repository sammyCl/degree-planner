import type { Plan, PlannedCourse } from '../types.ts'
import type { CompletedColumn } from './completed.ts'
import { categoryOf, courseLabel } from './courseLabel.ts'
import { formatCredits, subjectColor } from './graph.ts'

interface Props {
  columns: CompletedColumn[]
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

/** The courses the student already finished, on the left of the board: a column per term, or a folded rail. */
export function CompletedColumns({ columns, donePlan, collapsible, open, onToggle }: Props) {
  const courses = columns.flatMap((c) => c.courses)
  const credits = columns.reduce((sum, c) => sum + c.credits, 0)
  const summary = `${courses.length} ${courses.length === 1 ? 'course' : 'courses'}, ${formatCredits(credits)} cr`

  if (collapsible && !open) {
    return (
      <button type="button" className="done-rail" onClick={onToggle} aria-expanded={false} aria-label={`Show completed courses (${summary})`}>
        <span className="done-rail-ic">
          <Check size={14} />
        </span>
        <span className="done-rail-text">
          <b>Completed</b>
          <small>{summary}</small>
        </span>
        <span className="done-rail-cta">Show completed courses</span>
      </button>
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
        {columns.map((col, i) => {
          const [term, year] = /^(Fall|Spring|Summer) \d{4}$/.test(col.label) ? col.label.split(' ') : [col.label, '']
          return (
            <section className="sem done" key={col.key} aria-label={`${col.label}, completed`} style={{ ['--col' as string]: i }}>
              <div className="sem-h">
                <b>{term}</b>
                {year && <span className="sem-year">{year}</span>}
              </div>
              <div className="meter done">
                <span className="meter-track">
                  <i style={{ width: `${Math.min(100, (col.credits / 18) * 100)}%` }} />
                </span>
                <span className="meter-val">{formatCredits(col.credits)} cr</span>
              </div>
              {col.courses.map((c, row) => (
                <CompletedCard key={c.course_id} course={c} donePlan={donePlan} col={i} row={row} />
              ))}
            </section>
          )
        })}
      </div>
    </div>
  )
}

function CompletedCard({ course, donePlan, col, row }: { course: PlannedCourse; donePlan: Plan | null; col: number; row: number }) {
  const label = donePlan ? courseLabel(donePlan, course.course_id) : null
  return (
    <div
      className="card completed"
      data-id={course.course_id}
      aria-label={`${course.code} ${course.title}, ${formatCredits(course.credits)} credits, completed${label ? `, ${label.primary}` : ''}`}
      style={{ ['--col' as string]: col, ['--row' as string]: row, ['--sub' as string]: subjectColor(course.code) }}
    >
      <div className="card-row">
        <span className="card-dot" />
        <span className="card-code">{course.code}</span>
        <span className="card-cr">{formatCredits(course.credits)} cr</span>
        {label && <span className={`card-tag cat-${categoryOf(label.primary)}`}>{label.primary}</span>}
      </div>
      <div className="card-title">{course.title}</div>
      <div className="card-done">
        <Check /> Completed
      </div>
    </div>
  )
}
