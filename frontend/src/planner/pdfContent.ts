// What goes into the downloaded PDF, as plain data: pdfFile.ts only draws it. Everything comes from the plan as it
// stands on screen (the validator's flags, labels and requirement checks); nothing here decides whether it is valid.
import { completedTitle, displayCode, sourceLabel } from '../setup/transcript.ts'
import { ADD_ON_NAMES, LEVELS, PROGRAMS, staleInPlan } from '../setup/validate.ts'
import type { Plan } from '../types.ts'
import { completedColumns, completedCredits, completedId, remainingCredits } from './completed.ts'
import { courseLabel } from './courseLabel.ts'
import { flagKind, formatCredits, isOpen } from './graph.ts'
import { plainAlert } from './plainFlags.ts'
import { buildChecklist, buildChecks, readExplanation } from './summary.ts'

export interface PdfInput {
  plan: Plan
  /** the validator's check of the completed courses alone, which labels them; null when there is none */
  donePlan?: Plan | null
  explanation?: string
  checks?: string[]
  choices?: string[]
}

export interface PdfTable {
  heading: string
  columns: string[]
  rows: string[][]
}

export interface PdfNotes {
  heading: string
  items: string[]
}

export interface PdfDocument {
  fileName: string
  title: string
  /** lines under the title: programs, catalog year, start, date */
  details: string[]
  credits: string
  /** warnings that must be read first: open errors and older catalog data */
  alerts: PdfNotes[]
  completed: PdfTable | null
  semesters: PdfTable[]
  requirements: PdfTable[]
  notes: PdfNotes[]
  footer: string
}

const programName = (id: string): string => PROGRAMS.find((p) => p.id === id)?.name ?? id

const labelText = (plan: Plan | null | undefined, courseId: string): string => {
  const label = plan ? courseLabel(plan, courseId) : null
  if (!label) return ''
  return label.also ? `${label.primary} (also ${label.also})` : label.primary
}

const isoDay = (d: Date): string =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`

export function buildPdfDocument({ plan, donePlan, explanation, checks, choices }: PdfInput, today = new Date()): PdfDocument {
  const { total_credits: total, total_credits_required: required } = plan.summary
  const completed = plan.student.completed_courses
  const level = LEVELS.find((l) => l.value === plan.student.degree_level)?.label ?? plan.student.degree_level
  const start = plan.semesters[0]?.label

  const alerts: PdfNotes[] = []
  const errors = plan.flags.filter((f) => isOpen(f) && flagKind(f) === 'error')
  if (errors.length) {
    alerts.push({
      heading: `This plan still has ${errors.length} ${errors.length === 1 ? 'problem' : 'problems'} to fix`,
      items: errors.map((f) => `${plainAlert(f).title}: ${plainAlert(f).text}`),
    })
  }
  const stale = staleInPlan(plan.student.programs, plan.student.catalog_year)
  if (stale.length) {
    alerts.push({
      heading: 'Some rules may be out of date',
      items: stale.map((s) => `${s.name} (${ADD_ON_NAMES[s.kind].one}) uses ${s.year} rules. Check them with your advisor.`),
    })
  }

  const doneColumns = completedColumns(completed)
  const done: PdfTable | null = completed.length
    ? {
        heading: `Completed courses (${formatCredits(completedCredits(plan))} credits)`,
        columns: ['Course', 'Title', 'Credits', 'From', 'Counts as'],
        // in the order the board shows them
        rows: doneColumns
          .flatMap((col) => col.courses)
          .map((shown) => {
            const c = completed.find((x) => completedId(x.code) === shown.course_id)!
            return [
              displayCode(c.code),
              completedTitle(c),
              formatCredits(c.credits),
              `${sourceLabel(c)}${c.in_progress ? ', in progress' : ''}`,
              labelText(donePlan, shown.course_id),
            ]
          }),
      }
    : null

  const semesters: PdfTable[] = plan.semesters.map((s) => ({
    heading: `${s.label} (${formatCredits(s.total_credits)} credits)`,
    columns: ['Course', 'Title', 'Credits', 'Counts as'],
    rows: s.courses.length
      ? s.courses.map((c) => [displayCode(c.code), c.title, formatCredits(c.credits), labelText(plan, c.course_id)])
      : [['', 'No courses', '', '']],
  }))

  const requirements: PdfTable[] = buildChecklist(plan).map((section) => ({
    heading: section.title,
    columns: ['Requirement', 'Status', 'Detail'],
    rows: section.rows.map((r) => [r.name, r.met ? 'Met' : r.confirm ? 'Confirm' : 'Not met', r.detail]),
  }))

  // the assistant's own lists; an older answer only has free text
  const read =
    checks?.length || choices?.length || !explanation ? null : readExplanation(explanation, plan)
  const fromAssistant = checks?.length ? checks : (read?.checks ?? [])
  const toCheck = buildChecks(plan).map((c) => (c.title ? `${c.title}: ${c.text}` : c.text))
  const notes: PdfNotes[] = []
  if (toCheck.length) notes.push({ heading: 'Things to check', items: toCheck })
  if (fromAssistant.length) {
    notes.push({
      heading: 'To ask your advisor (written when the plan was first built)',
      items: fromAssistant.map((text) => text.replace(/\*\*/g, '')),
    })
  }

  const names = plan.student.programs.map(programName)
  const slug = `${plan.student.programs[0] ?? 'plan'}-${start ?? ''}`.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '')

  return {
    fileName: `degree-plan-${slug}.pdf`,
    title: 'Degree plan',
    details: [
      ...names,
      `${level} plan, catalog ${plan.student.catalog_year}${start ? `, ${plan.semesters.length} semesters starting ${start}` : ''}`,
      `Downloaded ${isoDay(today)}`,
    ],
    credits:
      `${formatCredits(total)} of ${formatCredits(required)} credits` +
      (completed.length ? `: ${formatCredits(completedCredits(plan))} completed, ${formatCredits(remainingCredits(plan))} planned` : ''),
    alerts,
    completed: done,
    semesters,
    requirements,
    notes,
    footer: 'Unofficial plan from the Group 9 Degree Planner. Confirm it with your advisor.',
  }
}
