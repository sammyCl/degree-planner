// Turns a plan into the short, readable "About this plan" panel: a checklist of requirements, the things the student
// should look at, and the choices the planning assistant made. The checklist comes from the backend's own checks
// (Plan.requirement_status); nothing here decides whether a requirement is met.
import { PROGRAMS } from '../setup/validate.ts'
import inferredEquivalents from './inferredEquivalents.json'
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
  /** the requirement groups behind this row ("program|group"), to list the courses that fill it */
  groups?: string[]
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

/** Requirement groups of the same kind (Core, Free electives, ...) merged into one row each, per program. */
const groupKey = (s: { program_id: string; group_id: string }) => `${s.program_id}|${s.group_id}`

function mergeByKind(statuses: RequirementStatus[]): { name: string; category: Category; group: RequirementStatus[] }[] {
  const merged = new Map<string, RequirementStatus[]>()
  for (const s of statuses) {
    const category = groupCategory(s.group_id, s.label)
    const key = category === 'Requirement' ? `label:${plainLabel(s.label)}` : category
    merged.set(key, [...(merged.get(key) ?? []), s])
  }
  return [...merged.entries()].map(([key, group]) => {
    const category = key.startsWith('label:') ? 'Requirement' : key
    return {
      name: category === 'Requirement' ? key.slice('label:'.length) : (ROW_NAMES[category] ?? category),
      category: categoryOf(category),
      group,
    }
  })
}

/** One row per kind of requirement (Core, Free electives, ...), merging groups of the same kind, per program. */
function rowsFor(statuses: RequirementStatus[]): ChecklistRow[] {
  return mergeByKind(statuses).map(({ name, category, group }) => {
    const met = group.every((s) => s.met)
    const required = group.reduce((sum, s) => sum + (s.kind === 'choose_credits' ? (s.credits_required ?? 0) : 0), 0)
    const earned = group.reduce((sum, s) => sum + (s.kind === 'choose_credits' ? (s.credits_earned ?? 0) : 0), 0)
    const missing = group.reduce((sum, s) => sum + s.missing_count, 0)
    let detail = ''
    if (required > 0) detail = `${formatCredits(Math.min(earned, required))}/${formatCredits(required)} credits`
    else if (!met && missing > 0) detail = `${missing} ${missing === 1 ? 'course' : 'courses'} missing`
    return { name, category, met, detail, groups: group.map(groupKey) }
  })
}

/**
 * What the completed courses already cover, from the validator's check of the completed courses on their own
 * (`donePlan`): each kind of requirement they count toward, ticked when they fill it completely. Kinds they do not
 * touch are left out.
 */
export function buildCompletedChecklist(donePlan: Plan): ChecklistSection[] {
  const byProgram = new Map<string, RequirementStatus[]>()
  for (const s of donePlan.requirement_status ?? []) byProgram.set(s.program_id, [...(byProgram.get(s.program_id) ?? []), s])
  const sections: ChecklistSection[] = []
  for (const [programId, statuses] of byProgram) {
    const rows: ChecklistRow[] = []
    for (const { name, category, group } of mergeByKind(statuses)) {
      const earned = group.reduce((sum, s) => sum + (s.credits_earned ?? 0), 0)
      const met = group.every((s) => s.met)
      if (!met && earned <= 0) continue
      // "x/y credits" only when every merged group is a credit count; a fixed list of courses has no credit target
      const allCredits = group.every((s) => s.kind === 'choose_credits')
      const required = group.reduce((sum, s) => sum + (s.credits_required ?? 0), 0)
      const detail = met
        ? 'already met'
        : allCredits && required > 0
          ? `${formatCredits(Math.min(earned, required))}/${formatCredits(required)} credits done`
          : `${formatCredits(earned)} credits done`
      rows.push({ name, category, met, detail, groups: group.map(groupKey) })
    }
    if (rows.length) sections.push({ title: programTitle(programId), rows })
  }
  return sections
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

/** The courses of a plan that fill a checklist row, in plan order (from the backend's counts_toward). */
export function coursesFor(plan: Plan, row: ChecklistRow): { code: string; title: string }[] {
  const wanted = new Set(row.groups ?? [])
  const map = plan.counts_toward ?? {}
  return plan.semesters
    .flatMap((s) => s.courses)
    .filter((c) => (map[c.course_id] ?? []).some((g) => wanted.has(groupKey(g))))
    .map((c) => ({ code: c.code, title: c.title }))
}

/** "Computer Science electives (18 credits): CSCI403 Data Base Management, ..." as a heading and its courses. */
export interface ChoiceParts {
  heading: string
  /** course codes named in the choice, in order */
  codes: string[]
  /** the choice in plain words when it is not a list of courses, or what follows the list */
  text: string
}

const CODE = /\b[A-Z]{3,4}\d{3}[A-Z]?\b/g

export function splitChoice(choice: string): ChoiceParts {
  const clean = choice.replace(/\*\*/g, '').trim()
  const lead = /^([^:.]{3,70}):\s*(.+)$/s.exec(clean)
  const codes = [...new Set(clean.match(CODE) ?? [])]
  if (lead && codes.length >= 2) {
    // the list ends at the first sentence that is not part of it ("Swap any of these for courses you prefer.")
    const sentences = lead[2].match(/[^.!?]+[.!?]*/g) ?? [lead[2]]
    const after = sentences.slice(1).join(' ').trim()
    return { heading: lead[1].trim(), codes, text: after }
  }
  return { heading: '', codes, text: clean }
}

/** A long note as its first sentence and the rest, so the panel shows one line and "more". */
export function firstSentence(text: string): { head: string; rest: string } {
  const match = /^(.+?[.!?])(\s+[A-Z(].*)?$/s.exec(text.trim())
  return match ? { head: match[1], rest: (match[2] ?? '').trim() } : { head: text.trim(), rest: '' }
}

export interface CheckItem {
  /** the course's title (not its number), or empty for a plan-wide note */
  title: string
  text: string
  kind: 'confirm' | 'warning' | 'info'
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
  items.push(...inferredEquivalentChecks(plan), ...addOnCreditNote(plan))
  return items
}

/** Courses the data treats as the same course although the catalog does not say so: the student confirms them. */
function inferredEquivalentChecks(plan: Plan): CheckItem[] {
  const inPlan = new Map(plan.semesters.flatMap((s) => s.courses.map((c) => [c.code, c] as const)))
  const items: CheckItem[] = []
  for (const group of inferredEquivalents as { codes: string[] }[]) {
    const mine = group.codes.find((code) => inPlan.has(code))
    if (!mine) continue
    const others = group.codes.filter((code) => code !== mine)
    items.push({
      title: inPlan.get(mine)!.title,
      text: `Counted as the same course as ${others.join(' and ')}; confirm with your advisor. The catalog does not say so (${mine}); the data assumes it because the catalog names both as prerequisites of other courses.`,
      kind: 'confirm',
    })
  }
  return items
}

/** A minor or ASI adds credits to the plan: at least 9 of its credits cannot also count toward the degree. */
function addOnCreditNote(plan: Plan): CheckItem[] {
  const levels = plan.student.programs.map((id) => PROGRAMS.find((p) => p.id === id)?.level)
  const addOn = levels.includes('minor') ? 'minor' : levels.includes('asi') ? 'ASI' : null
  if (!addOn || !levels.some((l) => l === 'bachelor' || l === 'combined')) return []
  const { total_credits: total, total_credits_required: required } = plan.summary
  return [
    {
      title: 'Credits',
      text: `A ${addOn} adds about 9 credits beyond your degree: at least 9 of its credits cannot also count toward the degree, and only free electives can overlap. This plan has ${formatCredits(total)} credits and the degree needs ${formatCredits(required)}.`,
      kind: 'info',
    },
  ]
}

// ---------- What the assistant wrote ----------
// The assistant writes free text with its own headings ("Order of courses", "Choices I made", "Things to check with your
// advisor", ...). These rules sort it so the panel stays short and in plain words. The lasting fix is for the agent to
// return its choices and notes as separate fields (Samantha's part); until then the page reads the text.

/** Sentences about the tools, or that only repeat what the checklist already shows. */
const NOT_FOR_STUDENTS =
  /`|check_plan|requirements_met|\bthe checker\b|\b(totals?|adds up to) \d+ of (the )?\d+|\bno errors\b|\bgoes over \d+ credits|\bat or under \d+ credits|^the plan (meets|satisfies|fulfills) every requirement/i
const sentences = (text: string): string[] => text.match(/[^.!?]+[.!?]*/g)?.map((s) => s.trim()).filter(Boolean) ?? []

type Destination = 'choices' | 'checks' | 'drop'

/** Where a heading's section goes: a semester rundown repeats the board; exceptions are listed from the flags. */
function destinationOf(heading: string): Destination {
  if (/order|semester by semester|schedule|timeline|by year/i.test(heading)) return 'drop'
  if (/exception|decide/i.test(heading)) return 'drop'
  if (/check|advisor|confirm|note|caveat|limit/i.test(heading)) return 'checks'
  return 'choices'
}

export interface AssistantNotes {
  /** what the assistant chose, in its own words */
  choices: Block[]
  /** things it says to confirm with an advisor */
  checks: string[]
}

/** Course numbers become course titles, for every course in the plan; anything else stays as written. */
function withTitles(text: string, titles: Map<string, string>): string {
  return text.replace(/\b([A-Z]{3,4})(\d{3}[A-Z]?)\b/g, (code) => titles.get(code) ?? code)
}

function clean(text: string, titles: Map<string, string>): string {
  return withTitles(
    sentences(text)
      .filter((s) => !NOT_FOR_STUDENTS.test(s))
      .join(' '),
    titles,
  ).trim()
}

/** Sorts the assistant's message into its choices and its notes to check, in plain words with no course numbers. */
export function readExplanation(explanation: string, plan: Plan): AssistantNotes {
  const titles = new Map(plan.semesters.flatMap((s) => s.courses.map((c) => [c.code, c.title] as const)))
  const notes: AssistantNotes = { choices: [], checks: [] }
  let where: Destination = 'choices'
  // A heading on its own line ("**Order of courses**") covers everything up to the next heading. A heading that starts a
  // paragraph ("**Exceptions.** Decide each one.") covers that paragraph and the list right after it, then text goes
  // back to the choices.
  let untilNextHeading = true
  let listMayFollow = false
  // a table (the assistant's semester-by-semester rundown) repeats the board and reads as gibberish as text
  const withoutTables = explanation
    .split('\n')
    .filter((line) => !/^\s*\|/.test(line))
    .join('\n')
  for (const block of parseBlocks(withoutTables)) {
    if (block.type === 'p') {
      const lead = /^\*\*([^*]+)\*\*[.:]?\s*/.exec(block.text)
      let text = block.text
      if (lead) {
        where = destinationOf(lead[1])
        text = text.slice(lead[0].length) // the panel has its own headings
        untilNextHeading = text.trim() === ''
        listMayFollow = !untilNextHeading
      } else if (!untilNextHeading) {
        where = 'choices'
        listMayFollow = false
      }
      if (where === 'drop') continue
      text = clean(text, titles)
      if (!text || /^\(.*\)$/.test(text)) continue // nothing left, or only an aside like "(you can change any of these)"
      if (where === 'checks') notes.checks.push(text)
      else notes.choices.push({ type: 'p', text })
    } else {
      const section = untilNextHeading || listMayFollow ? where : 'choices'
      listMayFollow = false
      if (!untilNextHeading) where = 'choices'
      if (section === 'drop') continue
      // a bullet is one thought: if any of it is about the tools, leave the whole bullet out rather than half of it
      const items = block.items
        .filter((item) => !sentences(item).some((s) => NOT_FOR_STUDENTS.test(s)))
        .map((item) => withTitles(item, titles).trim())
        .filter(Boolean)
      if (!items.length) continue
      if (section === 'checks') notes.checks.push(...items.map((i) => i.replace(/\*\*/g, '')))
      else notes.choices.push({ type: 'ul', items })
    }
  }
  return notes
}
