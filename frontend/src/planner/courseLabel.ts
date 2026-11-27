import { PROGRAMS } from '../setup/validate.ts'
import type { CountsToward, Plan } from '../types.ts'

export interface CourseLabel {
  /** what the course is for in the student's degree: Core, Free elective, Tech elective, ... */
  primary: string
  /** a second use, when the same course also counts toward a minor or ASI */
  also?: string
}

/** A program's level, from the options list, or from its id for one the setup page does not offer (the ASIs today). */
const levelOf = (programId: string) =>
  PROGRAMS.find((p) => p.id === programId)?.level ??
  (programId.endsWith('-asi') ? 'asi' : programId.endsWith('-minor') ? 'minor' : programId.endsWith('-certificate') ? 'certificate' : undefined)

/** Programs added on top of a degree, with the name used in a course label. */
const ADD_ON_LABELS: Record<string, string> = { minor: 'Minor', asi: 'ASI', certificate: 'Certificate' }
const isAddOn = (programId: string) => (levelOf(programId) ?? '') in ADD_ON_LABELS

/** Course codes written in a group's label, as in "Linear Algebra: MATH332 or MATH342". */
const CODE_OR_CODE = /\b[A-Z]{3,4}\s?\d{3}[A-Z]?\b.*\bor\b|\bor\b.*\b[A-Z]{3,4}\s?\d{3}\b|^[A-Z]{3,4}\s?\d{3}\b/

/**
 * A short name for a requirement group, from its id (the backend sends ids like "free-electives" or "cas-mid").
 * When the id says nothing, the label decides: a pick-one-of-these-courses requirement is Core, a group called an
 * elective or selection is an Elective, and anything else is a plain Requirement.
 */
export function groupCategory(groupId: string, label = ''): string {
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
  if (/elective|selection/i.test(label)) return 'Elective'
  if (CODE_OR_CODE.test(label)) return 'Core' // a required slot with a choice of courses, such as MATH332 or MATH342
  return 'Requirement'
}

/**
 * The label for one planned course, or null when there is nothing to say.
 * - It fills a group of the student's degree: that group's category.
 * - It only fills a minor's, ASI's or certificate's group: "Minor core" or "Minor elective" ("ASI core", ...).
 * - It is core for the degree: just "Core", even when it is also core for the minor.
 * - It fills another group of the degree and also a minor or ASI group: the category, noting the minor or ASI.
 * - It fills no group at all (only said when the backend sent any assignments): "Extra".
 */
export function courseLabel(plan: Plan, courseId: string): CourseLabel | null {
  const map = plan.counts_toward
  if (!map || Object.keys(map).length === 0) return null // an older plan, or nothing counted at all
  const entries: CountsToward[] | undefined = map[courseId]
  if (!entries || entries.length === 0) return { primary: 'Extra' }

  const degree = entries.find((e) => !isAddOn(e.program_id))
  const addOn = entries.find((e) => isAddOn(e.program_id))
  const addOnName = addOn ? ADD_ON_LABELS[levelOf(addOn.program_id)!] : undefined
  if (degree) {
    const primary = groupCategory(degree.group_id, degree.label)
    return { primary, also: primary === 'Core' ? undefined : addOnName }
  }
  if (!addOn || !addOnName) return { primary: 'Requirement' }
  return { primary: `${addOnName} ${groupCategory(addOn.group_id, addOn.label) === 'Core' ? 'core' : 'elective'}` }
}

/** The colour family of a label or requirement: one place, so the cards, the checklist and the page all agree. */
export type Category = 'core' | 'elective' | 'free' | 'cas' | 'minor' | 'extra' | 'other'

export function categoryOf(primary: string): Category {
  if (primary.startsWith('Minor ') || primary.startsWith('ASI ') || primary.startsWith('Certificate ')) return 'minor'
  switch (primary) {
    case 'Core':
      return 'core'
    case 'Free elective':
      return 'free'
    case 'CAS':
    case 'S&W':
      return 'cas'
    case 'Extra':
      return 'extra'
    case 'Requirement':
      return 'other'
    default:
      return 'elective' // CS, EE, ME and tech electives, focus areas, tracks
  }
}
