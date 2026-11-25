import { PROGRAMS } from '../setup/validate.ts'
import type { CountsToward, Plan } from '../types.ts'

export interface CourseLabel {
  /** what the course is for in the student's degree: Core, Free elective, Tech elective, ... */
  primary: string
  /** a second use, when the same course also counts toward a minor or ASI */
  also?: string
}

const levelOf = (programId: string) => PROGRAMS.find((p) => p.id === programId)?.level

/** A short name for a requirement group, from its id (the backend sends ids like "free-electives" or "cas-mid"). */
export function groupCategory(groupId: string): string {
  const id = groupId.toLowerCase()
  if (id === 'required' || id === 'core' || id === 'first-year-core' || id === 'track-required') return 'Core'
  if (id.startsWith('cas')) return 'CAS'
  if (id.startsWith('success')) return 'S&W'
  if (id.includes('free')) return 'Free elective'
  if (id.includes('tech')) return 'Tech elective'
  if (id.startsWith('focus')) return 'Focus area'
  if (id.startsWith('track')) return 'Track'
  const short = /^(cs|ee|me)-/.exec(id)
  if (id.includes('elective') && short) return `${short[1].toUpperCase()} elective`
  if (id.includes('elective') || id.startsWith('restricted')) return 'Elective'
  return 'Requirement'
}

/**
 * The label for one planned course, or null when there is nothing to say.
 * - It fills a group of the student's degree: that group's category.
 * - It only fills a minor's or ASI's group: "Minor" or "ASI".
 * - It also fills a minor or ASI group: the category plus "+ Minor" or "+ ASI".
 * - It fills no group at all (only said when the backend sent any assignments): "Extra".
 */
export function courseLabel(plan: Plan, courseId: string): CourseLabel | null {
  const map = plan.counts_toward
  if (!map || Object.keys(map).length === 0) return null // an older plan, or nothing counted at all
  const entries: CountsToward[] | undefined = map[courseId]
  if (!entries || entries.length === 0) return { primary: 'Extra' }

  const degree = entries.find((e) => !['minor', 'asi'].includes(levelOf(e.program_id) ?? ''))
  const addOn = entries.find((e) => ['minor', 'asi'].includes(levelOf(e.program_id) ?? ''))
  const addOnName = addOn ? (levelOf(addOn.program_id) === 'asi' ? 'ASI' : 'Minor') : undefined
  if (degree) return { primary: groupCategory(degree.group_id), also: addOnName }
  return { primary: addOnName ?? 'Requirement' }
}
