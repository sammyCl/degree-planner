import { useEffect, useRef } from 'react'
import type { Flag, Plan } from '../types.ts'
import { formatCredits, type PlanIndex } from './graph.ts'

interface Props {
  plan: Plan
  index: PlanIndex
  courseId: string
  anchor: HTMLElement
  flags: Flag[]
  onClose: () => void
}

/** Details for one course: its flags, what it needs and what it unlocks. Placed beside the card that was clicked. */
export function CoursePopover({ plan, index, courseId, anchor, flags, onClose }: Props) {
  const ref = useRef<HTMLDivElement>(null)
  const course = index.courses.get(courseId)!
  const here = index.semesterOf.get(courseId) ?? 0

  // Place next to the card, on whichever side has room.
  useEffect(() => {
    const el = ref.current
    if (!el) return
    const r = anchor.getBoundingClientRect()
    const w = el.offsetWidth
    const h = el.offsetHeight
    let x = r.right + 10
    if (x + w > window.innerWidth - 10) x = r.left - w - 10
    x = Math.max(10, x)
    const y = Math.min(Math.max(10, r.top - 8), Math.max(10, window.innerHeight - h - 10))
    el.style.left = `${x}px`
    el.style.top = `${y}px`
    el.focus()
  }, [anchor])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
    const onDown = (e: MouseEvent) => {
      const t = e.target as Node
      if (!ref.current?.contains(t) && !anchor.contains(t)) onClose()
    }
    document.addEventListener('keydown', onKey)
    document.addEventListener('mousedown', onDown)
    return () => {
      document.removeEventListener('keydown', onKey)
      document.removeEventListener('mousedown', onDown)
    }
  }, [anchor, onClose])

  const tag = (id: string, bad: boolean) => {
    const c = index.courses.get(id)!
    const label = plan.semesters[index.semesterOf.get(id) ?? 0]?.label
    return (
      <span key={id} className={bad ? 'tag bad' : 'tag'} title={c.title}>
        {c.code} &middot; {label}
      </span>
    )
  }
  const needs = index.needs.get(courseId) ?? []
  const unlocks = index.unlocks.get(courseId) ?? []

  return (
    <div className="pop" ref={ref} role="dialog" aria-label={`${course.code} details`} tabIndex={-1}>
      <button className="pop-close" type="button" aria-label="Close" onClick={onClose}>
        &times;
      </button>
      <h4>{course.code}</h4>
      <div className="pop-sub">
        {course.title} &middot; {formatCredits(course.credits)} credits &middot; {plan.semesters[here].label}
        {course.status === 'completed' ? ' (completed)' : ''}
      </div>
      {flags.map((f) => (
        <div key={f.flag_id} className={`pop-msg ${f.severity}`}>
          {f.message}
        </div>
      ))}
      <div className="pop-sec">Needs</div>
      <div className="pop-list">
        {needs.length ? needs.map((id) => tag(id, (index.semesterOf.get(id) ?? 0) >= here)) : <span className="tag">Nothing in this plan</span>}
      </div>
      <div className="pop-sec">Unlocks</div>
      <div className="pop-list">
        {unlocks.length ? unlocks.map((id) => tag(id, (index.semesterOf.get(id) ?? 0) <= here)) : <span className="tag">Nothing in this plan</span>}
      </div>
    </div>
  )
}
