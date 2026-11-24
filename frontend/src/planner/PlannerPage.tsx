import { useCallback, useEffect, useMemo, useState } from 'react'
import { LEVELS, PROGRAMS } from '../setup/validate.ts'
import type { Flag, Plan } from '../types.ts'
import { Arrows } from './Arrows.tsx'
import { CourseCard, type CardState } from './CourseCard.tsx'
import { CoursePopover } from './CoursePopover.tsx'
import { AssistantNote } from './AssistantNote.tsx'
import { chainOf, creditLevel, flagsByCourse, formatCredits, indexPlan, isOpen } from './graph.ts'
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

export function PlannerPage({ plan, explanation, problems, onBack }: Props) {
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
  const closePopover = useCallback(() => setOpenCard(null), [])

  useEffect(() => {
    if (!pulseId) return
    const t = setTimeout(() => setPulseId(null), 900)
    return () => clearTimeout(t)
  }, [pulseId])

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

  return (
    <div className="planner">
      <SummaryBar plan={plan} programName={programName(plan)} onSelectFlag={selectFlag} />
      <div className="planner-notice">
        <span>
          {LEVELS.find((l) => l.value === plan.student.degree_level)?.label ?? plan.student.degree_level} plan,{' '}
          {plan.semesters.length} semesters, starting {plan.semesters[0]?.label}
        </span>
        <button type="button" className="link" onClick={onBack}>
          Edit setup
        </button>
      </div>
      <AssistantNote explanation={explanation} problems={problems} />
      <div className="board">
        <div className="board-inner">
          <div className={`cols${chain ? ' chain-mode' : ''}`} ref={setCols} data-testid="board">
            {plan.semesters.map((s, i) => {
              const [term, year] = s.label.split(' ')
              const credits = s.courses.reduce((sum, c) => sum + c.credits, 0)
              const level = creditLevel(credits)
              return (
                <section className="sem" key={s.semester_id} aria-label={s.label} style={{ ['--col' as string]: i }}>
                  <div className="sem-h">
                    <b>{term}</b>
                    <span>{year}</span>
                  </div>
                  <div className={`meter ${level}`}>
                    <span className="meter-track">
                      <i style={{ width: `${Math.min(100, (credits / 18) * 100)}%` }} />
                    </span>
                    <span className="meter-val">{formatCredits(s.total_credits)} cr</span>
                  </div>
                  {s.courses.map((c, j) => (
                    <CourseCard
                      key={c.course_id}
                      course={c}
                      flag={byCourse.get(c.course_id)?.[0]}
                      state={stateOf(c.course_id)}
                      col={i}
                      row={j}
                      setRef={setRef}
                      onEnter={setActiveId}
                      onLeave={() => setActiveId(null)}
                      onOpen={(id, el) => setOpenCard({ id, el })}
                      pulse={pulseId === c.course_id}
                    />
                  ))}
                </section>
              )
            })}
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
      {openCard && (
        <CoursePopover
          plan={plan}
          index={index}
          courseId={openCard.id}
          anchor={openCard.el}
          flags={byCourse.get(openCard.id) ?? []}
          onClose={closePopover}
        />
      )}
    </div>
  )
}
