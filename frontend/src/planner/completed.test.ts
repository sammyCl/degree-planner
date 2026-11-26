import { describe, expect, it } from 'vitest'
import { samplePlan } from '../samplePlan.ts'
import type { CompletedCourse, Plan } from '../types.ts'
import { completedColumns, completedOnlyPlan, remainingCredits, startsCollapsed } from './completed.ts'
import { buildCompletedChecklist } from './summary.ts'

const course = (code: string, credits: number, term: string): CompletedCourse => ({ code, credits, term, transfer_from: null })

describe('completedColumns', () => {
  it('puts AP, IB and transfer credit first (one column per school), then the terms in order, with catalog titles', () => {
    const columns = completedColumns([
      course('CSCI128', 3, 'Spring 2026'),
      course('MATH111', 4, 'aplcredit'),
      course('CHGN121', 4, 'Fall 2025'),
      { code: 'PHGN100', credits: 4, term: 'transfer', transfer_from: 'Example State University' },
      { code: 'CHGN122', credits: 4, term: 'transfer', transfer_from: 'IB credit' },
      course('MATH112', 4, 'Spring 2026'),
    ])
    expect(columns.map((c) => [c.label, c.from])).toEqual([
      ['AP credit', undefined],
      ['IB credit', undefined],
      ['Transfer credit', 'Example State University'],
      ['Fall 2025', undefined],
      ['Spring 2026', undefined],
    ])
    expect(columns[4].courses.map((c) => c.code)).toEqual(['CSCI128', 'MATH112'])
    expect(columns[4].credits).toBe(7)
    expect(columns[0].courses[0]).toMatchObject({ course_id: 'done-MATH111', status: 'completed' })
    expect(columns[0].courses[0].title).toMatch(/Calculus/)
  })

  it('titles placeholder credit from the transcript, and marks a term that is all in progress', () => {
    const columns = completedColumns([
      { code: 'FREE1XX-1', credits: 3, term: 'transfer', transfer_from: 'IB credit', title: 'Free Elective-Art History' },
      { code: 'HASS2XX-1', credits: 3, term: 'transfer', transfer_from: 'IB credit' },
      { code: 'CSCI261', credits: 3, term: 'Fall 2025', transfer_from: null, in_progress: true },
    ])
    expect(columns[0].courses.map((c) => c.title)).toEqual(['Free Elective-Art History', 'CAS/HASS mid-level elective credit'])
    expect(columns[1]).toMatchObject({ label: 'Fall 2025', inProgress: true })
  })

  it('names a course the catalog does not have by where it came from', () => {
    const [col] = completedColumns([{ code: 'ENGL101', credits: 3, term: 'transfer', transfer_from: 'Red Rocks CC' }])
    expect(col.courses[0].title).toBe('Transfer from Red Rocks CC')
  })
})

describe('startsCollapsed', () => {
  it('keeps up to a semester of completed courses on the board, and folds more away', () => {
    expect(startsCollapsed([course('A', 4, 'transfer'), course('B', 4, 'transfer')], 'bachelor')).toBe(false)
    expect(startsCollapsed([course('A', 9, 'Fall 2025'), course('B', 9, 'Fall 2025')], 'bachelor')).toBe(false) // 18: one full semester
    expect(startsCollapsed([course('A', 10, 'Fall 2025'), course('B', 9, 'Spring 2026')], 'bachelor')).toBe(true)
    expect(startsCollapsed([course('A', 16, 'Fall 2025')], 'master')).toBe(true) // a graduate semester holds 15
  })
})

describe('completedOnlyPlan', () => {
  it('asks the validator about the completed courses alone, as columns, with nothing else', () => {
    const plan = completedOnlyPlan(samplePlan, completedColumns(samplePlan.student.completed_courses))
    expect(plan.student.completed_courses).toEqual([])
    expect(plan.student.programs).toEqual(samplePlan.student.programs)
    expect(plan.semesters.flatMap((s) => s.courses.map((c) => c.code))).toEqual(['MATH111'])
    expect(plan.semesters.every((s) => s.semester_id.startsWith('done-'))).toBe(true)
  })

  it('counts the credits still to take as everything in the semester columns', () => {
    const planned = samplePlan.semesters.flatMap((s) => s.courses).reduce((n, c) => n + c.credits, 0)
    expect(remainingCredits(samplePlan)).toBe(planned)
  })
})

describe('buildCompletedChecklist', () => {
  const status = (group_id: string, label: string, met: boolean, earned: number | null, required: number | null = null) => ({
    program_id: 'cs-bs-general-track',
    group_id,
    label,
    kind: required === null ? ('all' as const) : ('choose_credits' as const),
    met,
    credits_required: required,
    credits_earned: earned,
    missing_count: 0,
  })
  it('lists only what the completed courses count toward, ticking what they fill completely', () => {
    const done = {
      ...samplePlan,
      requirement_status: [
        status('required', 'Required core', false, 11),
        status('success-wellness', 'Success and Wellness', true, 1, 1),
        status('free-electives', 'Free Electives', false, 3, 9),
        status('cas-mid', 'CAS mid-level', false, 0, 9),
      ],
    } as Plan
    const [section] = buildCompletedChecklist(done)
    expect(section.rows.map((r) => [r.name, r.met, r.detail])).toEqual([
      ['Core courses', false, '11 credits done'],
      ['Success & Wellness', true, 'already met'],
      ['Free electives', false, '3/9 credits done'],
    ])
  })
  it('does not show a credit target for core that mixes a course list with a credit group', () => {
    const done = {
      ...samplePlan,
      requirement_status: [status('required', 'Required core', false, 19), status('core', 'Core choice', true, 6, 6)],
    } as Plan
    expect(buildCompletedChecklist(done)[0].rows).toMatchObject([{ name: 'Core courses', category: 'core', met: false, detail: '25 credits done' }])
  })
})
