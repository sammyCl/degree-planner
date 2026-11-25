// Turns a plan into the short, readable "About this plan" panel: a checklist of requirements, the things the student
// should look at, and the choices the planning assistant made. The checklist comes from the backend's own checks
// (Plan.requirement_status); nothing here decides whether a requirement is met.
import { PROGRAMS } from '../setup/validate.ts'
import type { Plan, RequirementStatus } from '../types.ts'
import { categoryOf, groupCategory, type Category } from './courseLabel.ts'
import { flagKind, formatCredits, indexPlan, isOpen } from './graph.ts'
import { parseBlocks, type Block } from './parseMarkdown.ts'

export interface ChecklistRow {
  name: string
  category: Category
  met: boolean
  /** "12/18 credits" or "3 courses missing"; empty when there is nothing useful to add */
  detail: string
}

export interface ChecklistSection {
  title: string
  rows: ChecklistRow[]
}

const ROW_NAMES: Record<string, string> = {
  Core: 'Core courses',
  CAS: 'Culture & Society (CAS)',
  'S&W': 'Success & Wellness',
  'Free elective': 'Free electives',
  'Tech elective': 'Technical electives',
  'CS elective': 'CS electives',
  'EE elective': 'EE electives',
  'ME elective': 'ME electives',
  Elective: 'Electives',
  'Focus area': 'Focus area',
  Track: 'Track',
}

/** "Free electives (3 courses)" becomes "Free electives": the bracket is detail the checklist shows another way. */
const plainLabel = (label: string): string => label.replace(/\s*\([^)]*\)/g, '').trim()

const programTitle = (programId: string): string => PROGRAMS.find((p) => p.id === programId)?.name ?? programId

/** One row per kind of requirement (Core, Free electives, ...), merging groups of the same kind, per program. */
function rowsFor(statuses: RequirementStatus[]): ChecklistRow[] {
  const merged = new Map<string, RequirementStatus[]>()
  for (const s of statuses) {
    const category = groupCategory(s.group_id)
    const key = category === 'Requirement' ? `label:${plainLabel(s.label)}` : category
    merged.set(key, [...(merged.get(key) ?? []), s])
  }
  return [...merged.entries()].map(([key, group]) => {
    const category = key.startsWith('label:') ? 'Requirement' : key
    const met = group.every((s) => s.met)
    const required = group.reduce((sum, s) => sum + (s.kind === 'choose_credits' ? (s.credits_required ?? 0) : 0), 0)
    const earned = group.reduce((sum, s) => sum + (s.kind === 'choose_credits' ? (s.credits_earned ?? 0) : 0), 0)
    const missing = group.reduce((sum, s) => sum + s.missing_count, 0)
    let detail = ''
    if (required > 0) detail = `${formatCredits(Math.min(earned, required))}/${formatCredits(required)} credits`
    else if (!met && missing > 0) detail = `${missing} ${missing === 1 ? 'course' : 'courses'} missing`
    return {
      name: category === 'Requirement' ? key.slice('label:'.length) : (ROW_NAMES[category] ?? category),
      category: categoryOf(category),
      met,
      detail,
    }
  })
}

/** The requirement checklist: each program's groups, then the plan-wide checks (credits, prerequisites). */
export function buildChecklist(plan: Plan): ChecklistSection[] {
  const sections: ChecklistSection[] = []
  const byProgram = new Map<string, RequirementStatus[]>()
  for (const s of plan.requirement_status ?? []) byProgram.set(s.program_id, [...(byProgram.get(s.program_id) ?? []), s])
  for (const [programId, statuses] of byProgram) sections.push({ title: programTitle(programId), rows: rowsFor(statuses) })

  const { total_credits: total, total_credits_required: required } = plan.summary
  const outOfOrder = new Set(
    plan.flags.filter((f) => f.type === 'broken_prerequisite' && isOpen(f) && f.course_id).map((f) => f.course_id),
  ).size
  sections.push({
    title: 'Whole plan',
    rows: [
      {
        name: 'Total credits',
        category: 'other',
        met: total >= required,
        detail: `${formatCredits(total)}/${formatCredits(required)} credits`,
      },
      {
        name: 'Prerequisites in order',
        category: 'other',
        met: outOfOrder === 0,
        detail: outOfOrder ? `${outOfOrder} ${outOfOrder === 1 ? 'course' : 'courses'} out of order` : '',
      },
    ],
  })
  return sections
}

export interface CheckItem {
  /** the course's title (not its number), or empty for a plan-wide note */
  title: string
  text: string
  kind: 'confirm' | 'warning'
}

/** What the student should look at: claimed exceptions to confirm, and warnings. Errors are shown on the board itself. */
export function buildChecks(plan: Plan): CheckItem[] {
  const index = indexPlan(plan)
  const items: CheckItem[] = []
  for (const f of plan.flags) {
    const kind = flagKind(f)
    if (!isOpen(f) || kind === 'error') continue
    const title = f.course_id ? (index.courses.get(f.course_id)?.title ?? '') : ''
    const reason = /\(([^)]+)\)/.exec(f.message)?.[1]
    items.push({
      title,
      text: kind === 'confirm' && reason ? `needs ${reason}; confirm it still applies` : f.message,
      kind,
    })
  }
  return items
}

const JARGON = /`|check_plan|requirements_met/i
const RESTATES = /^the plan (meets|satisfies|fulfills) every requirement\b/i
const sentences = (text: string): string[] => text.match(/[^.!?]+[.!?]*/g)?.map((s) => s.trim()).filter(Boolean) ?? []

/**
 * The assistant's own words about the choices it made. It writes free text, so this keeps what a student cares about:
 * it drops the exception list (shown as "Things to check" instead), sentences that talk about the tools, and a plain
 * "the plan meets every requirement" (the checklist says that better).
 */
export function extractChoices(explanation: string): Block[] {
  const out: Block[] = []
  const blocks = parseBlocks(explanation)
  for (let i = 0; i < blocks.length; i++) {
    const block = blocks[i]
    if (block.type === 'p') {
      const lead = /^\*\*([^*]+)\*\*/.exec(block.text)?.[1] ?? ''
      if (/exception|decide/i.test(lead)) {
        if (blocks[i + 1]?.type === 'ul') i++ // the list that belongs to it
        continue
      }
      let text = block.text
      if (/choice|decision|picked|selected/i.test(lead)) text = text.replace(/^\*\*[^*]+\*\*\s*/, '')
      text = sentences(text)
        .filter((s) => !JARGON.test(s) && !RESTATES.test(s))
        .join(' ')
      if (text) out.push({ type: 'p', text })
    } else {
      const items = block.items.filter((it) => !JARGON.test(it))
      if (items.length) out.push({ type: 'ul', items })
    }
  }
  return out
}
