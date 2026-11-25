import type { Flag, PlannedCourse } from '../types.ts'
import type { CourseLabel } from './courseLabel.ts'
import { flagKind, formatCredits, subjectColor } from './graph.ts'

export type CardState = 'idle' | 'in-chain' | 'focus' | 'dim'

interface Props {
  course: PlannedCourse
  flag?: Flag
  /** what the course counts as in the student's degree (Core, Free elective, ...) */
  label?: CourseLabel | null
  state: CardState
  /** stagger for the entrance animation */
  col: number
  row: number
  setRef: (id: string, el: HTMLDivElement | null) => void
  onEnter: (id: string) => void
  onLeave: () => void
  onOpen: (id: string, el: HTMLDivElement) => void
  /** a planned course can be dragged to another semester; a completed one cannot */
  canDrag?: boolean
  dragging?: boolean
  onDragStart?: (id: string) => void
  onDragEnd?: () => void
  /** set briefly after a flag is clicked in the flags list, to draw the eye */
  pulse?: boolean
}

export function CourseCard({ course, flag, label, state, col, row, setRef, onEnter, onLeave, onOpen, canDrag, dragging, onDragStart, onDragEnd, pulse }: Props) {
  const open = flag && !flag.overridden
  const kind = open ? flagKind(flag) : null
  const aria =
    `${course.code} ${course.title}, ${formatCredits(course.credits)} credits` +
    (label ? `, ${label.primary}${label.also ? ` and ${label.also}` : ''}` : '') +
    (course.status === 'completed' ? ', completed' : '') +
    (flag ? `. Problem: ${flag.message}` : '')
  const classes = ['card', kind === 'error' ? 'flagged' : '', kind === 'warning' ? 'warned' : '', kind === 'confirm' ? 'confirm' : '', course.status === 'completed' ? 'completed' : '', state, pulse ? 'pulse' : '', dragging ? 'dragging' : '']
    .filter(Boolean)
    .join(' ')
  return (
    <div
      ref={(el) => setRef(course.course_id, el)}
      className={classes}
      role="button"
      tabIndex={0}
      draggable={canDrag}
      data-id={course.course_id}
      aria-label={aria}
      style={{ ['--col' as string]: col, ['--row' as string]: row, ['--sub' as string]: subjectColor(course.code) }}
      onMouseEnter={() => onEnter(course.course_id)}
      onMouseLeave={onLeave}
      onFocus={() => onEnter(course.course_id)}
      onBlur={onLeave}
      onDragStart={(e) => {
        e.dataTransfer.setData('text/plain', course.course_id)
        e.dataTransfer.effectAllowed = 'move'
        onDragStart?.(course.course_id)
      }}
      onDragEnd={() => onDragEnd?.()}
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
      {label && (
        <div className="card-tags">
          <span className={`tag-pill kind-${label.primary.toLowerCase().replace(/[^a-z]+/g, '-')}`}>{label.primary}</span>
          {label.also && <span className="tag-pill also">+ {label.also}</span>}
        </div>
      )}
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
