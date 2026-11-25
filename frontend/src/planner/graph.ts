// Read-only helpers over a plan. The frontend never computes flags or prerequisite edges itself: the backend's
// validator does (docs/plan-format.md). These functions only index what the plan already says, for drawing.
import type { Flag, Plan, PlannedCourse } from '../types.ts'

export interface PlanIndex {
  courses: Map<string, PlannedCourse>
  /** course_id to the index of the semester it sits in */
  semesterOf: Map<string, number>
  /** course_id to the course_ids it needs (its prerequisites placed in this plan) */
  needs: Map<string, string[]>
  /** course_id to the course_ids that need it */
  unlocks: Map<string, string[]>
}

export function indexPlan(plan: Plan): PlanIndex {
  const courses = new Map<string, PlannedCourse>()
  const semesterOf = new Map<string, number>()
  plan.semesters.forEach((s, i) =>
    s.courses.forEach((c) => {
      courses.set(c.course_id, c)
      semesterOf.set(c.course_id, i)
    }),
  )
  const needs = new Map<string, string[]>()
  const unlocks = new Map<string, string[]>()
  for (const e of plan.prerequisite_edges) {
    if (!courses.has(e.from) || !courses.has(e.to)) continue // an edge to a course not in the plan is not drawn
    needs.set(e.to, [...(needs.get(e.to) ?? []), e.from])
    unlocks.set(e.from, [...(unlocks.get(e.from) ?? []), e.to])
  }
  return { courses, semesterOf, needs, unlocks }
}

/** The whole prerequisite chain of a course: everything it needs and everything that needs it, and the edges between. */
export function chainOf(plan: Plan, index: PlanIndex, id: string): { ids: Set<string>; edges: Set<number> } {
  const ids = new Set<string>([id])
  const edges = new Set<number>()
  const walk = (start: string, next: Map<string, string[]>, up: boolean) => {
    const stack = [start]
    while (stack.length) {
      const here = stack.pop()!
      for (const other of next.get(here) ?? []) {
        plan.prerequisite_edges.forEach((e, k) => {
          if (up ? e.from === other && e.to === here : e.from === here && e.to === other) edges.add(k)
        })
        if (!ids.has(other)) {
          ids.add(other)
          stack.push(other)
        }
      }
    }
  }
  walk(id, index.needs, true)
  walk(id, index.unlocks, false)
  return { ids, edges }
}

/** An overridden flag no longer counts against the plan (the student chose to accept it). */
export const isOpen = (flag: Flag): boolean => !flag.overridden

/**
 * How a flag is shown. An error is red and a warning is amber: those mean something is wrong or at risk. A claimed
 * exception (instructor consent, "or equivalent", class standing) is not a problem, only something for the student to
 * confirm, so it gets its own calm "confirm" style.
 */
export type FlagKind = 'error' | 'warning' | 'confirm'

export function flagKind(flag: Flag): FlagKind {
  if (flag.severity === 'error') return 'error'
  return flag.type === 'exception_claimed' ? 'confirm' : 'warning'
}

export function flagCounts(flags: Flag[]): { errors: number; warnings: number; confirm: number } {
  const kinds = flags.filter(isOpen).map(flagKind)
  return {
    errors: kinds.filter((k) => k === 'error').length,
    warnings: kinds.filter((k) => k === 'warning').length,
    confirm: kinds.filter((k) => k === 'confirm').length,
  }
}

export function flagsByCourse(flags: Flag[]): Map<string, Flag[]> {
  const map = new Map<string, Flag[]>()
  for (const f of flags) {
    if (f.course_id === null) continue
    map.set(f.course_id, [...(map.get(f.course_id) ?? []), f])
  }
  return map
}

/** Full time is 12 or more credits; more than 19 is an overload. Only used to colour the semester's credit bar. */
export function creditLevel(credits: number): 'low' | 'ok' | 'high' {
  if (credits > 0 && credits < 12) return 'low'
  return credits > 19 ? 'high' : 'ok'
}

export const formatCredits = (n: number): string => String(Math.round(n * 10) / 10)

/** Course subject colours; anything else is grey. */
export function subjectColor(code: string): string {
  const subject = code.replace(/\d.*$/, '')
  const known: Record<string, string> = {
    CSCI: 'var(--sub-csci)',
    MATH: 'var(--sub-math)',
    PHGN: 'var(--sub-phgn)',
    CHGN: 'var(--sub-chgn)',
  }
  return known[subject] ?? 'var(--sub-other)'
}
