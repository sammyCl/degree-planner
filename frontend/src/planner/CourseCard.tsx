import type { Flag, PlannedCourse } from '../types.ts'
import { flagKind, formatCredits, subjectColor } from './graph.ts'

export type CardState = 'idle' | 'in-chain' | 'focus' | 'dim'

interface Props {
  course: PlannedCourse
  flag?: Flag
  state: CardState
  /** stagger for the entrance animation */
  col: number
  row: number
  setRef: (id: string, el: HTMLDivElement | null) => void
  onEnter: (id: string) => void
  onLeave: () => void
  onOpen: (id: string, el: HTMLDivElement) => void
  /** set briefly after a flag is clicked in the flags list, to draw the eye */
  pulse?: boolean
}

export function CourseCard({ course, flag, state, col, row, setRef, onEnter, onLeave, onOpen, pulse }: Props) {
  const open = flag && !flag.overridden
  const kind = open ? flagKind(flag) : null
  const aria =
    `${course.code} ${course.title}, ${formatCredits(course.credits)} credits` +
    (course.status === 'completed' ? ', completed' : '') +
    (flag ? `. Problem: ${flag.message}` : '')
  const classes = ['card', kind === 'error' ? 'flagged' : '', kind === 'warning' ? 'warned' : '', kind === 'confirm' ? 'confirm' : '', course.status === 'completed' ? 'completed' : '', state, pulse ? 'pulse' : '']
    .filter(Boolean)
    .join(' ')
  return (
    <div
      ref={(el) => setRef(course.course_id, el)}
      className={classes}
      role="button"
      tabIndex={0}
      data-id={course.course_id}
      aria-label={aria}
      style={{ ['--col' as string]: col, ['--row' as string]: row, ['--sub' as string]: subjectColor(course.code) }}
      onMouseEnter={() => onEnter(course.course_id)}
      onMouseLeave={onLeave}
      onFocus={() => onEnter(course.course_id)}
      onBlur={onLeave}
      onClick={(e) => onOpen(course.course_id, e.currentTarget)}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          onOpen(course.course_id, e.currentTarget)
        }
      }}
    >
      <div className="card-row">
        <span className="card-dot" />
        <span className="card-code">{course.code}</span>
        <span className="card-cr">{formatCredits(course.credits)} cr</span>
      </div>
      <div className="card-title">{course.title}</div>
      {open && (
        <div className="card-warn" aria-hidden="true">
          <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M12 3l10 18H2z" />
            <path d="M12 10v4m0 3h.01" />
          </svg>
          {flag.type === 'broken_prerequisite' ? 'Prerequisite out of order' : kind === 'confirm' ? 'To confirm' : kind === 'warning' ? 'Check this' : 'Needs attention'}
        </div>
      )}
    </div>
  )
}
