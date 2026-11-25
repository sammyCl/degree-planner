import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { ApiError, checkPlan } from '../api.ts'
import { LEVELS, PROGRAMS } from '../setup/validate.ts'
import type { Flag, Plan } from '../types.ts'
import { Arrows } from './Arrows.tsx'
import { CourseCard, type CardState } from './CourseCard.tsx'
import { CoursePopover } from './CoursePopover.tsx'
import { PlanSummary } from './PlanSummary.tsx'
import { courseLabel } from './courseLabel.ts'
import {
  chainOf,
  creditLevel,
  flagsByCourse,
  formatCredits,
  indexPlan,
  insertSemester,
  isOpen,
  isRemovable,
  movePlanned,
  nextRegularTerm,
  removeSemester,
  summerSlots,
} from './graph.ts'
import { SummaryBar } from './SummaryBar.tsx'
import './PlannerPage.css'

interface Props {
  plan: Plan
  /** what the planning assistant says about the plan */
  explanation?: string
  /** why it could not finish a valid plan, if it could not */
  problems?: string[]
  onBack: () => void
}

const programName = (plan: Plan): string => {
  const id = plan.student.programs[0]
  return PROGRAMS.find((p) => p.id === id)?.name ?? id ?? 'Your plan'
}

const undoMessage = (error: unknown): string =>
  error instanceof ApiError && error.kind === 'network'
    ? 'Could not reach the backend, so your change was undone.'
    : `The backend could not re-check the plan, so your change was undone.${error instanceof ApiError ? ` ${error.message}` : ''}`

export function PlannerPage({ plan: initialPlan, explanation, problems, onBack }: Props) {
  // The plan on screen. After every change the backend re-checks it and its answer replaces this, so the flags,
  // arrows and totals are always the validator's, never the page's own.
  const [plan, setPlan] = useState(initialPlan)
  const confirmed = useRef(initialPlan) // the last plan the backend returned
  const latest = useRef(0) // numbers the checks, so an old answer cannot overwrite a newer edit
  const [checking, setChecking] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)

  const index = useMemo(() => indexPlan(plan), [plan])
  const byCourse = useMemo(() => flagsByCourse(plan.flags), [plan.flags])
  const brokenTargets = useMemo(
    () =>
      new Set(
        plan.flags.filter((f) => f.type === 'broken_prerequisite' && isOpen(f) && f.course_id).map((f) => f.course_id as string),
      ),
    [plan.flags],
  )

  const [cols, setCols] = useState<HTMLDivElement | null>(null)
  const [cardEls] = useState(() => new Map<string, HTMLElement>())
  const setRef = useCallback(
    (id: string, el: HTMLElement | null) => {
      if (el) cardEls.set(id, el)
      else cardEls.delete(id)
    },
    [cardEls],
  )

  const [activeId, setActiveId] = useState<string | null>(null)
  const chain = useMemo(() => (activeId ? chainOf(plan, index, activeId) : null), [plan, index, activeId])
  const [openCard, setOpenCard] = useState<{ id: string; el: HTMLElement } | null>(null)
  const [pulseId, setPulseId] = useState<string | null>(null)
  const [dragId, setDragId] = useState<string | null>(null)
  const [overIndex, setOverIndex] = useState<number | null>(null)
  const closePopover = useCallback(() => setOpenCard(null), [setOpenCard])

  useEffect(() => {
    if (!pulseId) return
    const t = setTimeout(() => setPulseId(null), 900)
    return () => clearTimeout(t)
  }, [pulseId])

  /** Show an edit at once, then have the backend check it; its answer replaces the plan, or the edit is undone. */
  const applyEdit = (next: Plan) => {
    if (next === plan) return
    const mine = ++latest.current
    setPlan(next)
    setChecking(true)
    setNotice(null)
    checkPlan(next)
      .then((result) => {
        if (latest.current !== mine) return
        confirmed.current = result
        setPlan(result)
        setChecking(false)
      })
      .catch((error) => {
        if (latest.current !== mine) return
        setPlan(confirmed.current)
        setChecking(false)
        setNotice(undoMessage(error))
      })
  }

  const move = (courseId: string, toIndex: number) => applyEdit(movePlanned(plan, courseId, toIndex))

  const selectFlag = (flag: Flag) => {
    if (!flag.course_id) return // plan-wide flags are not tied to one course
    const el = cardEls.get(flag.course_id)
    el?.scrollIntoView?.({ behavior: 'smooth', block: 'center', inline: 'center' })
    setPulseId(flag.course_id)
    el?.focus({ preventScroll: true })
  }

  const stateOf = (id: string): CardState => {
    if (!chain) return 'idle'
    if (id === activeId) return 'focus'
    return chain.ids.has(id) ? 'in-chain' : 'dim'
  }

  const summers = new Map(summerSlots(plan).map((s) => [s.after, s.label]))
  const last = plan.semesters[plan.semesters.length - 1]
  const endTerm = last ? nextRegularTerm(last.label) : null

  return (
    <div className="planner">
      <SummaryBar plan={plan} programName={programName(plan)} onSelectFlag={selectFlag} checking={checking} />
      <div className="planner-notice">
        <span>
          {LEVELS.find((l) => l.value === plan.student.degree_level)?.label ?? plan.student.degree_level} plan,{' '}
          {plan.semesters.length} semesters, starting {plan.semesters[0]?.label}. Drag a course to another semester to move it.
        </span>
        <button type="button" className="link" onClick={onBack}>
          Edit setup
        </button>
      </div>
      {problems && problems.length > 0 && (
        <div className="note-problems planner-problems" role="alert">
          <b>The assistant could not finish a valid plan.</b> This is its last attempt; check the flagged courses.
          <ul>
            {problems.map((p, i) => (
              <li key={i}>{p}</li>
            ))}
          </ul>
        </div>
      )}
      <div className="board">
        <div className="board-inner">
          <div className={`cols${chain ? ' chain-mode' : ''}${dragId ? ' dragging-any' : ''}`} ref={setCols} data-testid="board">
            {plan.semesters.map((s, i) => {
              const [term, year] = s.label.split(' ')
              const credits = s.courses.reduce((sum, c) => sum + c.credits, 0)
              const level = creditLevel(credits, s.label)
              const summer = summers.get(i)
              return (
                <section
                  className={`sem${overIndex === i ? ' drop-target' : ''}`}
                  key={s.semester_id}
                  aria-label={s.label}
                  style={{ ['--col' as string]: i }}
                  onDragOver={(e) => {
                    if (!dragId) return
                    e.preventDefault()
                    setOverIndex(i)
                  }}
                  onDragLeave={(e) => {
                    if (!e.currentTarget.contains(e.relatedTarget as Node | null)) setOverIndex(null)
                  }}
                  onDrop={(e) => {
                    e.preventDefault()
                    const id = dragId
                    setDragId(null)
                    setOverIndex(null)
                    if (id) move(id, i)
                  }}
                >
                  <div className="sem-h">
                    <b>{term}</b>
                    <span className="sem-year">{year}</span>
                    {isRemovable(s) && (
                      <button type="button" className="sem-remove" aria-label={`Remove ${s.label}`} onClick={() => applyEdit(removeSemester(plan, s.semester_id))}>
                        &times;
                      </button>
                    )}
                  </div>
                  <div className={`meter ${level}`}>
                    <span className="meter-track">
                      <i style={{ width: `${Math.min(100, (credits / 18) * 100)}%` }} />
                    </span>
                    <span className="meter-val">{formatCredits(s.total_credits)} cr</span>
                  </div>
                  {s.courses.length === 0 && <div className="sem-empty">Drag courses here</div>}
                  {s.courses.map((c, j) => (
                    <CourseCard
                      key={c.course_id}
                      course={c}
                      flag={byCourse.get(c.course_id)?.[0]}
                      label={courseLabel(plan, c.course_id)}
                      state={stateOf(c.course_id)}
                      col={i}
                      row={j}
                      setRef={setRef}
                      onEnter={setActiveId}
                      onLeave={() => setActiveId(null)}
                      onOpen={(id, el) => setOpenCard({ id, el })}
                      canDrag={c.status === 'planned'}
                      dragging={dragId === c.course_id}
                      onDragStart={(id) => {
                        setActiveId(null)
                        setOpenCard(null)
                        setDragId(id)
                      }}
                      onDragEnd={() => {
                        setDragId(null)
                        setOverIndex(null)
                      }}
                      pulse={pulseId === c.course_id}
                    />
                  ))}
                  {summer && (
                    <button
                      type="button"
                      className="add-between"
                      aria-label={`Add ${summer} after ${s.label}`}
                      title={`Add ${summer}`}
                      onClick={() => applyEdit(insertSemester(plan, i + 1, summer))}
                    >
                      +
                    </button>
                  )}
                </section>
              )
            })}
            {endTerm && (
              <div className="sem add-end">
                <button type="button" className="btn" aria-label={`Add ${endTerm} at the end`} onClick={() => applyEdit(insertSemester(plan, plan.semesters.length, endTerm))}>
                  + Add {endTerm}
                </button>
              </div>
            )}
            <Arrows
              plan={plan}
              index={index}
              container={cols}
              cardEls={cardEls}
              hotEdges={chain?.edges ?? new Set()}
              brokenTargets={brokenTargets}
            />
          </div>
        </div>
      </div>
      <PlanSummary plan={plan} explanation={explanation} />
      {notice && (
        <div className="planner-toast" role="alert">
          <span>{notice}</span>
          <button type="button" className="link" onClick={() => setNotice(null)}>
            Dismiss
          </button>
        </div>
      )}
      {openCard && (
        <CoursePopover
          plan={plan}
          index={index}
          courseId={openCard.id}
          anchor={openCard.el}
          flags={byCourse.get(openCard.id) ?? []}
          onMove={
            index.courses.get(openCard.id)?.status === 'planned'
              ? (to) => {
                  move(openCard.id, to)
                  setOpenCard(null)
                }
              : undefined
          }
          onClose={closePopover}
        />
      )}
    </div>
  )
}
