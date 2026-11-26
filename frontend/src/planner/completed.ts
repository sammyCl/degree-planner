// Completed courses on the planner page. The agent plans only what is left, starting at the chosen semester; the
// courses the student already finished stay in plan.student.completed_courses, outside the semester columns. These
// helpers turn them into columns of their own (one per term they were taken in) for the left side of the board.
import { catalogCourse, termLabel } from '../setup/transcript.ts'
import type { CompletedCourse, Plan, PlannedCourse, Semester } from '../types.ts'

export interface CompletedColumn {
  key: string
  /** what the column header says: "Fall 2025", "Transfer credit" or "AP credit" */
  label: string
  courses: PlannedCourse[]
  credits: number
}

/** Ids for completed courses, so they never clash with the plan's own course ids. */
export const completedId = (code: string): string => `done-${code}`

const SEASON_ORDER: Record<string, number> = { Spring: 0, Summer: 1, Fall: 2 }

/** Transfer and AP credit first (they come before Mines), then the semesters in the order they were taken. */
function termRank(term: string): [number, number, number] {
  if (term === 'transfer') return [0, 0, 0]
  if (term === 'aplcredit') return [0, 0, 1]
  const m = /^(Fall|Spring|Summer) (\d{4})$/.exec(term)
  return m ? [1, Number(m[2]), SEASON_ORDER[m[1]]] : [2, 0, 0]
}

const compare = (a: string, b: string): number => {
  const [x, y] = [termRank(a), termRank(b)]
  return x[0] - y[0] || x[1] - y[1] || x[2] - y[2] || a.localeCompare(b)
}

/** The completed courses as board columns, one per term, with the catalog's titles. */
export function completedColumns(completed: CompletedCourse[]): CompletedColumn[] {
  const byTerm = new Map<string, CompletedCourse[]>()
  for (const c of completed) byTerm.set(c.term, [...(byTerm.get(c.term) ?? []), c])
  return [...byTerm.keys()].sort(compare).map((term) => {
    const courses = byTerm.get(term)!.map(
      (c): PlannedCourse => ({
        course_id: completedId(c.code),
        code: c.code,
        title: catalogCourse(c.code)?.title ?? (c.transfer_from ? `Transfer from ${c.transfer_from}` : 'Completed course'),
        credits: c.credits,
        status: 'completed',
      }),
    )
    return {
      key: `done:${term}`,
      label: termLabel(term),
      courses,
      credits: Math.round(courses.reduce((sum, c) => sum + c.credits, 0) * 10) / 10,
    }
  })
}

/** The most credits one semester may hold (the validator's limit: 18, or 15 for a graduate student). */
export const semesterLimit = (degreeLevel: string): number => (degreeLevel === 'master' ? 15 : 18)

/**
 * Whether the completed courses start folded away: only when they are more than one semester's worth. A few
 * courses (an AP credit or two, one transfer semester) stay on the board, marked as completed.
 */
export function startsCollapsed(completed: CompletedCourse[], degreeLevel: string): boolean {
  const credits = completed.reduce((sum, c) => sum + c.credits, 0)
  return credits > semesterLimit(degreeLevel)
}

/** Credits still to take: everything planned in the semester columns. */
export const remainingCredits = (plan: Plan): number =>
  Math.round(plan.semesters.reduce((sum, s) => sum + s.courses.reduce((n, c) => n + c.credits, 0), 0) * 10) / 10

export const completedCredits = (plan: Plan): number =>
  Math.round(plan.student.completed_courses.reduce((sum, c) => sum + c.credits, 0) * 10) / 10

/**
 * A plan of only the completed courses, for the validator to say which requirement groups they fill on their own
 * (its counts_toward labels the completed cards; its requirement_status is "already met" in About this plan).
 * The backend's own answer for the real plan does not label completed courses, so the page asks this separately.
 */
export function completedOnlyPlan(plan: Plan, columns: CompletedColumn[]): Plan {
  const semesters: Semester[] = columns.map((col, i) => ({
    semester_id: `done-${i}`,
    label: col.label,
    courses: col.courses,
    total_credits: col.credits,
  }))
  return {
    plan_id: null,
    student: { ...plan.student, completed_courses: [] },
    semesters,
    prerequisite_edges: [],
    flags: [],
    summary: { total_credits: 0, total_credits_required: 0, requirements_met: false },
  }
}
