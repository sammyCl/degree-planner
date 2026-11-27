// Read-only helpers over a plan. The frontend never computes flags or prerequisite edges itself: the backend's
// validator does (docs/plan-format.md). These functions only index what the plan already says, for drawing.
import labPairs from './labPairs.json'
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
 * confirm, so it gets its own calm "confirm" style; so does a course counted as another's equivalent by inference.
 */
export type FlagKind = 'error' | 'warning' | 'confirm'

export function flagKind(flag: Flag): FlagKind {
  if (flag.severity === 'error') return 'error'
  return ['exception_claimed', 'assumed_equivalent', 'unlisted_course'].includes(flag.type) ? 'confirm' : 'warning'
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

/** The labels of semesters the validator says are over the credit limit (18 undergraduate, 15 graduate). */
export function overloadedSemesters(flags: Flag[]): Set<string> {
  const labels = new Set<string>()
  for (const f of flags) {
    if (f.type !== 'semester_overload' || !isOpen(f)) continue
    const label = /^((?:Fall|Spring|Summer) \d{4}) has /.exec(f.message)?.[1]
    if (label) labels.add(label)
  }
  return labels
}

/**
 * How to colour a semester's credit bar. Over the limit is the validator's call (`overloaded`), not the page's.
 * Full time is 12 credits (9 for a master's student); less is marked low. A Summer is a short, optional term, so a
 * light one is normal and is never marked as under full time.
 */
export function creditLevel(credits: number, label = '', overloaded = false, fullTime = 12): 'low' | 'ok' | 'high' {
  if (overloaded) return 'high'
  if (credits > 0 && credits < fullTime && !label.startsWith('Summer')) return 'low'
  return 'ok'
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

// ---------- Edits the student makes on the board ----------
// These only rearrange the plan. They never decide whether the result is valid: the backend's validator does that
// (POST /plans/check) and its answer replaces the plan.

const sumCredits = (courses: PlannedCourse[]): number => courses.reduce((sum, c) => sum + c.credits, 0)

const LAB_OF: Record<string, string> = labPairs

/**
 * The planned courses that travel together with this one: a lecture and its lab(s) taken in the same semester.
 * Always includes the course itself; a completed course, or one with no partner in its semester, is alone.
 */
export function togetherWith(plan: Plan, courseId: string): string[] {
  const semester = plan.semesters.find((s) => s.courses.some((c) => c.course_id === courseId))
  const me = semester?.courses.find((c) => c.course_id === courseId)
  if (!semester || !me || me.status !== 'planned') return [courseId]
  const lectureCode = LAB_OF[me.code] ?? me.code // a lab's lecture, or the course itself when it is the lecture
  return semester.courses
    .filter((c) => c.status === 'planned' && (c.code === lectureCode || LAB_OF[c.code] === lectureCode))
    .map((c) => c.course_id)
}

/** For each lab shown attached to a lecture in the same semester: the lab's course_id to the lecture's. */
export function attachedLabs(plan: Plan): Map<string, string> {
  const result = new Map<string, string>()
  for (const s of plan.semesters) {
    for (const lab of s.courses) {
      const lecture = LAB_OF[lab.code] && s.courses.find((c) => c.code === LAB_OF[lab.code])
      if (lecture) result.set(lab.course_id, lecture.course_id)
    }
  }
  return result
}

/** The plan with one planned course (and the lab or lecture that goes with it) moved to the end of another semester. */
export function movePlanned(plan: Plan, courseId: string, toIndex: number): Plan {
  const fromIndex = plan.semesters.findIndex((s) => s.courses.some((c) => c.course_id === courseId))
  if (fromIndex < 0 || toIndex < 0 || toIndex >= plan.semesters.length || fromIndex === toIndex) return plan
  const ids = new Set(togetherWith(plan, courseId))
  const moving = plan.semesters[fromIndex].courses.filter((c) => ids.has(c.course_id))
  const semesters = plan.semesters.map((s, i) => {
    if (i !== fromIndex && i !== toIndex) return s
    const courses = i === fromIndex ? s.courses.filter((c) => !ids.has(c.course_id)) : [...s.courses, ...moving]
    return { ...s, courses, total_credits: sumCredits(courses) }
  })
  return { ...plan, semesters }
}

const ADDED = 'sem-added-'

/** The plan with an empty semester inserted at `index` (0 to length). */
export function insertSemester(plan: Plan, index: number, label: string): Plan {
  const used = plan.semesters.map((s) => s.semester_id)
  let n = 1
  while (used.includes(`${ADDED}${n}`)) n++
  const semester = { semester_id: `${ADDED}${n}`, label, courses: [], total_credits: 0 }
  const semesters = [...plan.semesters.slice(0, index), semester, ...plan.semesters.slice(index)]
  return { ...plan, semesters }
}

/** A semester the student added and has not put anything in can be taken away again. */
export const isRemovable = (semester: { semester_id: string; courses: unknown[] }): boolean =>
  semester.semester_id.startsWith(ADDED) && semester.courses.length === 0

export function removeSemester(plan: Plan, semesterId: string): Plan {
  const target = plan.semesters.find((s) => s.semester_id === semesterId)
  if (!target || !isRemovable(target)) return plan
  return { ...plan, semesters: plan.semesters.filter((s) => s.semester_id !== semesterId) }
}

// ---------- Terms ----------

const LABEL = /^(Fall|Spring|Summer) (\d{4})$/

/** The term that follows in the calendar: Fall Y then Spring Y+1, Spring Y then Summer Y, Summer Y then Fall Y. */
export function termAfter(label: string): string | null {
  const m = LABEL.exec(label)
  if (!m) return null
  const year = Number(m[2])
  if (m[1] === 'Fall') return `Spring ${year + 1}`
  return m[1] === 'Spring' ? `Summer ${year}` : `Fall ${year}`
}

/** The next regular (Fall or Spring) term after a label, for a semester added at the end. */
export function nextRegularTerm(label: string): string | null {
  const m = LABEL.exec(label)
  if (!m) return null
  const year = Number(m[2])
  return m[1] === 'Fall' ? `Spring ${year + 1}` : `Fall ${year}`
}

/** Where a Summer can be added: right after a Spring that is not already followed by a Summer. */
export function summerSlots(plan: Plan): { after: number; label: string }[] {
  const slots: { after: number; label: string }[] = []
  plan.semesters.forEach((s, i) => {
    const m = LABEL.exec(s.label)
    if (!m || m[1] !== 'Spring') return
    const next = plan.semesters[i + 1]
    if (next && next.label.startsWith('Summer')) return
    slots.push({ after: i, label: `Summer ${m[2]}` })
  })
  return slots
}
