import { useEffect, useRef, useState } from 'react'
import { Dropdown } from '../setup/Dropdown.tsx'
import type { Flag, Plan } from '../types.ts'
import { flagKind, formatCredits, togetherWith, type PlanIndex } from './graph.ts'
import { plainAlert } from './plainFlags.ts'
import { describeRequirement } from './requirement.ts'

interface Props {
  plan: Plan
  index: PlanIndex
  courseId: string
  anchor: HTMLElement
  flags: Flag[]
  /** move the course to another semester (the keyboard-friendly way); left out for a completed course */
  onMove?: (toIndex: number) => void
  /** `refocus` is set when the keyboard should go back to the card (Escape and the close button) */
  onClose: (refocus?: boolean) => void
}

/** A description longer than this starts shortened, with a button for the rest. */
const SHORT = 220

/** The start of a long description, cut at a word. */
const shorten = (text: string): string => `${text.slice(0, SHORT).replace(/\s+\S*$/, '')}...`

/** Details for one course: its description, flags, corequisites, what it needs and what it unlocks. Placed beside the card that was clicked. */
export function CoursePopover({ plan, index, courseId, anchor, flags, onMove, onClose }: Props) {
  const ref = useRef<HTMLDivElement>(null)
  const course = index.courses.get(courseId)!
  const here = index.semesterOf.get(courseId) ?? 0
  const [target, setTarget] = useState(String(here))
  const [full, setFull] = useState(false)
  const description = course.description?.trim() ?? ''
  const long = description.length > SHORT

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
  }, [anchor, full])

  // move keyboard focus into the popover when it opens (not again when the description is expanded)
  useEffect(() => ref.current?.focus(), [anchor])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose(true)
    const onDown = (e: MouseEvent) => {
      // composedPath is fixed when the click starts. A menu option that React removes while handling the
      // same click (choosing a semester) is no longer in the page, so contains() would call it "outside".
      const path = e.composedPath()
      if (!path.includes(ref.current as EventTarget) && !path.includes(anchor)) onClose()
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
  const partners = togetherWith(plan, courseId).filter((id) => id !== courseId)
  const needs = index.needs.get(courseId) ?? []
  const unlocks = index.unlocks.get(courseId) ?? []

  return (
    <div className="pop" ref={ref} role="dialog" aria-label={`${course.code} details`} tabIndex={-1}>
      <button className="pop-close" type="button" aria-label="Close" onClick={() => onClose(true)}>
        &times;
      </button>
      <h4>{course.code}</h4>
      <div className="pop-sub">
        {course.title} &middot; {formatCredits(course.credits)} credits &middot; {plan.semesters[here].label}
        {course.status === 'completed' ? ' (completed)' : ''}
      </div>
      {flags.map((f) => (
        <div key={f.flag_id} className={`pop-msg ${flagKind(f)}`}>
          <b>{plainAlert(f).title}.</b> {plainAlert(f).text}
        </div>
      ))}
      {description && (
        <p className="pop-desc">
          {long && !full ? shorten(description) : description}
          {long && (
            <button type="button" className="link" aria-expanded={full} onClick={() => setFull((f) => !f)}>
              {full ? 'Less' : 'Read more'}
            </button>
          )}
        </p>
      )}
      {partners.length > 0 && onMove && (
        <div className="pop-note">
          Taken together with {partners.map((id) => index.courses.get(id)?.code).join(', ')}, so they move as one.
        </div>
      )}
      <div className="pop-sec">Needs</div>
      <div className="pop-list">
        {needs.length ? needs.map((id) => tag(id, (index.semesterOf.get(id) ?? 0) >= here)) : <span className="tag">Nothing in this plan</span>}
      </div>
      {course.corequisites && (
        <>
          <div className="pop-sec">Take with, or before</div>
          <div className="pop-coreq">{describeRequirement(course.corequisites)}</div>
        </>
      )}
      <div className="pop-sec">Unlocks</div>
      <div className="pop-list">
        {unlocks.length ? unlocks.map((id) => tag(id, (index.semesterOf.get(id) ?? 0) <= here)) : <span className="tag">Nothing in this plan</span>}
      </div>
      {onMove && (
        <>
          <div className="pop-sec">Move to</div>
          <div className="pop-move">
            <Dropdown
              label="Move to semester"
              options={plan.semesters.map((s, i) => ({ value: String(i), label: s.label }))}
              value={target}
              onChange={setTarget}
            />
            <button type="button" className="btn primary" disabled={Number(target) === here} onClick={() => onMove(Number(target))}>
              Move
            </button>
          </div>
        </>
      )}
    </div>
  )
}
