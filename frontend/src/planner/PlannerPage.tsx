import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { ApiError, checkPlan } from '../api.ts'
import { ADD_ON_NAMES, LEVELS, PROGRAMS, staleInPlan } from '../setup/validate.ts'
import type { Flag, Plan, PlannedCourse } from '../types.ts'
import { Arrows } from './Arrows.tsx'
import { ChatPanel } from './ChatPanel.tsx'
import { CompletedColumns } from './CompletedColumns.tsx'
import { completedColumns, completedOnlyPlan, startsCollapsed } from './completed.ts'
import { CourseCard, type CardState } from './CourseCard.tsx'
import { CoursePopover } from './CoursePopover.tsx'
import { Downloads } from './Downloads.tsx'
import { PlanSummary } from './PlanSummary.tsx'
import { courseLabel } from './courseLabel.ts'
import {
  attachedLabs,
  chainOf,
  creditLevel,
  overloadedSemesters,
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
  togetherWith,
} from './graph.ts'
import { SummaryBar } from './SummaryBar.tsx'
import './PlannerPage.css'

interface Props {
  plan: Plan
  /** what the planning assistant says about the plan */
  explanation?: string
  /** the assistant's choices and things to check, one per item */
  choices?: string[]
  checks?: string[]
  /** why it could not finish a valid plan, if it could not */
  problems?: string[]
  onBack: () => void
}

const HISTORY_LIMIT = 50

const programName = (plan: Plan): string => {
  const id = plan.student.programs[0]
  return PROGRAMS.find((p) => p.id === id)?.name ?? id ?? 'Your plan'
}

const undoMessage = (error: unknown): string =>
  error instanceof ApiError && error.kind === 'network'
    ? "Can't reach the server, so we undid your change. Try again."
    : "We couldn't check your change, so we undid it. Try again."

export function PlannerPage({ plan: initialPlan, explanation, choices, checks, problems, onBack }: Props) {
  // The plan on screen. After every change the backend re-checks it and its answer replaces this, so the flags,
  // arrows and totals are always the validator's, never the page's own.
  const [plan, setPlan] = useState(initialPlan)
  // the last plan the backend returned, with the undo and redo history that goes with it
  const confirmed = useRef({ plan: initialPlan, past: [] as Plan[], future: [] as Plan[] })
  const latest = useRef(0) // numbers the checks, so an old answer cannot overwrite a newer edit
  const [checking, setChecking] = useState(false)
  const [notice, setNotice] = useState<string | null>(null)

  // Completed courses: columns of their own on the left. More than a semester's worth starts folded into a rail.
  const doneColumns = useMemo(() => completedColumns(plan.student.completed_courses), [plan.student.completed_courses])
  const doneCollapsible = useMemo(
    () => startsCollapsed(plan.student.completed_courses, plan.student.degree_level),
    [plan.student.completed_courses, plan.student.degree_level],
  )
  const [showDone, setShowDone] = useState(!doneCollapsible)
  const doneInProgress = useMemo(
    () => new Set(plan.student.completed_courses.filter((c) => c.in_progress).map((c) => c.code)),
    [plan.student.completed_courses],
  )
  // the validator's answer for the completed courses alone: their labels, and the requirements they already meet
  const [donePlan, setDonePlan] = useState<Plan | null>(null)
  const [doneState, setDoneState] = useState<'loading' | 'ready' | 'failed'>('loading')
  useEffect(() => {
    if (doneColumns.length === 0) return
    const abort = new AbortController()
    checkPlan(completedOnlyPlan(initialPlan, doneColumns), abort.signal)
      .then((result) => {
        setDonePlan(result)
        setDoneState('ready')
      })
      .catch(() => {
        if (!abort.signal.aborted) setDoneState('failed') // without it the completed cards just have no labels
      })
    return () => abort.abort()
  }, [initialPlan, doneColumns])

  const index = useMemo(() => indexPlan(plan), [plan])
  const stale = useMemo(() => staleInPlan(plan.student.programs, plan.student.catalog_year), [plan.student])
  const overloaded = useMemo(() => overloadedSemesters(plan.flags), [plan.flags])
  const labs = useMemo(() => attachedLabs(plan), [plan]) // lab course_id to the lecture it is drawn under
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
  // a lecture and its lab are dragged as one, so both look lifted
  const dragIds = useMemo(() => new Set(dragId ? togetherWith(plan, dragId) : []), [plan, dragId])
  const closePopover = useCallback(
    (refocus?: boolean) => {
      if (refocus) openCard?.el.focus({ preventScroll: true })
      setOpenCard(null)
    },
    [openCard, setOpenCard],
  )
  // a course moved from its details is drawn anew in its new column: put the keyboard back on it
  const refocus = useRef<string | null>(null)
  useEffect(() => {
    if (!refocus.current) return
    cardEls.get(refocus.current)?.focus()
    refocus.current = null
  }, [plan, cardEls])

  useEffect(() => {
    if (!pulseId) return
    const t = setTimeout(() => setPulseId(null), 900)
    return () => clearTimeout(t)
  }, [pulseId])

  // Every change goes on a history, so it can be undone and redone. The buttons show once there is something to undo.
  const [past, setPast] = useState<Plan[]>([])
  const [future, setFuture] = useState<Plan[]>([])

  /** Show a plan at once, then have the backend check it; its answer replaces the plan, or the change is undone. */
  const run = (next: Plan, nextPast: Plan[], nextFuture: Plan[]) => {
    const mine = ++latest.current
    setPlan(next)
    setPast(nextPast)
    setFuture(nextFuture)
    setOpenCard(null)
    setChecking(true)
    setNotice(null)
    checkPlan(next)
      .then((result) => {
        if (latest.current !== mine) return
        confirmed.current = { plan: result, past: nextPast, future: nextFuture }
        setPlan(result)
        setChecking(false)
      })
      .catch((error) => {
        if (latest.current !== mine) return
        setPlan(confirmed.current.plan)
        setPast(confirmed.current.past)
        setFuture(confirmed.current.future)
        setChecking(false)
        setNotice(undoMessage(error))
      })
  }
  const applyEdit = (next: Plan) => {
    if (next !== plan) run(next, [...past.slice(-(HISTORY_LIMIT - 1)), plan], [])
  }
  const undo = () => past.length > 0 && run(past[past.length - 1], past.slice(0, -1), [...future, plan])
  const redo = () => future.length > 0 && run(future[future.length - 1], [...past, plan], future.slice(0, -1))

  // Ctrl or Cmd+Z undoes, Shift+Ctrl or Cmd+Z (or Ctrl+Y) redoes, unless the student is typing in a field
  const keys = useRef({ undo, redo })
  useEffect(() => {
    keys.current = { undo, redo } // the shortcut always calls the latest undo and redo
  })
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null
      if (t && (t.tagName === 'INPUT' || t.tagName === 'TEXTAREA' || t.isContentEditable)) return
      if (!(e.metaKey || e.ctrlKey)) return
      const k = e.key.toLowerCase()
      if (k === 'z' && !e.shiftKey) keys.current.undo()
      else if ((k === 'z' && e.shiftKey) || k === 'y') keys.current.redo()
      else return
      e.preventDefault()
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [])

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
      {stale.length > 0 && (
        <div className="stale-warning" role="note">
          <b>Some rules may be out of date.</b>{' '}
          {stale.map((s) => `${s.name} (${ADD_ON_NAMES[s.kind].one}) uses ${s.year} rules`).join('; ')}. Check{' '}
          {stale.length === 1 ? 'it' : 'them'} with your advisor.
        </div>
      )}
      <div className="planner-notice">
        <button type="button" className="edit-setup" onClick={onBack}>
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M4 6h10M18 6h2M4 12h4M12 12h8M4 18h12M20 18h0" />
            <circle cx="16" cy="6" r="2" />
            <circle cx="10" cy="12" r="2" />
            <circle cx="18" cy="18" r="2" />
          </svg>
          Edit setup
        </button>
        <span>
          {LEVELS.find((l) => l.value === plan.student.degree_level)?.label ?? plan.student.degree_level} plan,{' '}
          {plan.semesters.length} semesters, starting {plan.semesters[0]?.label}
          {doneColumns.length > 0 ? ', with your completed courses on the left' : ''}. Drag a course to another semester to move it.
        </span>
        <Downloads
          board={cols}
          plan={plan}
          donePlan={donePlan}
          explanation={explanation}
          checks={checks}
          choices={choices}
          // not while a change is being checked (its flags are not in yet), nor before the completed courses are labelled
          waiting={checking || (doneColumns.length > 0 && doneState === 'loading')}
        />
      </div>
      {problems && problems.length > 0 && (
        <div className="note-problems planner-problems" role="alert">
          <b>This plan still has problems.</b> Fix the courses in red by moving or replacing them. The reasons are below.
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
            {doneColumns.length > 0 && (
              <CompletedColumns
                columns={doneColumns}
                inProgress={doneInProgress}
                donePlan={donePlan}
                collapsible={doneCollapsible}
                open={showDone}
                onToggle={() => setShowDone((v) => !v)}
              />
            )}
            {plan.semesters.map((s, i) => {
              const [term, year] = s.label.split(' ')
              const credits = s.courses.reduce((sum, c) => sum + c.credits, 0)
              const level = creditLevel(credits, s.label, overloaded.has(s.label), plan.student.degree_level === 'master' ? 9 : 12)
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
                  {s.courses
                    .filter((c) => !labs.has(c.course_id))
                    .map((c) => {
                      const attached = s.courses.filter((x) => labs.get(x.course_id) === c.course_id)
                      const card = (x: PlannedCourse, attachedTo?: string) => (
                        <CourseCard
                          key={x.course_id}
                          course={x}
                          flag={byCourse.get(x.course_id)?.[0]}
                          label={courseLabel(plan, x.course_id)}
                          state={stateOf(x.course_id)}
                          col={i}
                          row={s.courses.indexOf(x)}
                          setRef={setRef}
                          onEnter={setActiveId}
                          onLeave={() => setActiveId(null)}
                          onOpen={(id, el) => setOpenCard({ id, el })}
                          canDrag={x.status === 'planned'}
                          dragging={dragIds.has(x.course_id)}
                          attachedTo={attachedTo}
                          onDragStart={(id) => {
                            setActiveId(null)
                            setOpenCard(null)
                            setDragId(id)
                          }}
                          onDragEnd={() => {
                            setDragId(null)
                            setOverIndex(null)
                          }}
                          pulse={pulseId === x.course_id}
                        />
                      )
                      return attached.length === 0 ? (
                        card(c)
                      ) : (
                        <div className="card-group" key={c.course_id}>
                          {card(c)}
                          {attached.map((lab) => card(lab, c.code))}
                        </div>
                      )
                    })}
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
              layoutKey={showDone}
            />
          </div>
          {(past.length > 0 || future.length > 0) && (
            <div className="board-tools" role="group" aria-label="Undo and redo">
              <button type="button" className="tool" disabled={past.length === 0} onClick={undo} title="Undo (Ctrl or Cmd+Z)">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <path d="M9 14L4 9l5-5" />
                  <path d="M4 9h10.5a5.5 5.5 0 0 1 0 11H11" />
                </svg>
                Undo
              </button>
              <button type="button" className="tool" disabled={future.length === 0} onClick={redo} title="Redo (Shift+Ctrl or Cmd+Z)">
                Redo
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <path d="M15 14l5-5-5-5" />
                  <path d="M20 9H9.5a5.5 5.5 0 0 0 0 11H13" />
                </svg>
              </button>
            </div>
          )}
        </div>
      </div>
      <PlanSummary plan={plan} explanation={explanation} choices={choices} checks={checks} donePlan={donePlan} doneState={doneState} />
      <ChatPanel
        plan={plan}
        busy={checking}
        // a suggestion goes on the board like any other edit: checked by the backend, and undoable
        onApply={applyEdit}
      />
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
          key={openCard.id}
          plan={plan}
          index={index}
          courseId={openCard.id}
          anchor={openCard.el}
          flags={byCourse.get(openCard.id) ?? []}
          onMove={
            index.courses.get(openCard.id)?.status === 'planned'
              ? (to) => {
                  refocus.current = openCard.id
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
