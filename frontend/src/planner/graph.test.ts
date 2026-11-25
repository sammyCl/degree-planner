import { describe, expect, it } from 'vitest'
import { samplePlan } from '../samplePlan.ts'
import {
  chainOf,
  creditLevel,
  flagCounts,
  flagKind,
  flagsByCourse,
  indexPlan,
  insertSemester,
  isRemovable,
  movePlanned,
  nextRegularTerm,
  removeSemester,
  subjectColor,
  summerSlots,
  termAfter,
} from './graph.ts'

describe('indexPlan', () => {
  const index = indexPlan(samplePlan)

  it('finds every course and its semester', () => {
    expect(index.courses.size).toBe(samplePlan.semesters.flatMap((s) => s.courses).length)
    expect(index.semesterOf.get('sem-1-csci128')).toBe(0)
    expect(index.semesterOf.get('sem-5-csci400')).toBe(4)
  })

  it('knows what a course needs and what it unlocks', () => {
    expect(index.needs.get('sem-5-csci400')).toEqual(expect.arrayContaining(['sem-5-csci306', 'sem-3-csci358']))
    expect(index.unlocks.get('sem-5-csci306')).toEqual(expect.arrayContaining(['sem-5-csci400', 'sem-6-csci370']))
  })
})

describe('chainOf', () => {
  const index = indexPlan(samplePlan)

  it('walks up to the first courses and down to the last', () => {
    const { ids } = chainOf(samplePlan, index, 'sem-5-csci306')
    expect(ids.has('sem-1-csci128')).toBe(true) // CSCI128 -> CSCI200 -> CSCI210 -> CSCI306
    expect(ids.has('sem-6-csci370')).toBe(true) // CSCI306 -> CSCI370
    expect(ids.has('sem-1-chgn121')).toBe(false) // unrelated
  })

  it('returns only edges that join courses in the chain', () => {
    const { ids, edges } = chainOf(samplePlan, index, 'sem-5-csci306')
    for (const k of edges) {
      const e = samplePlan.prerequisite_edges[k]
      expect(ids.has(e.from) && ids.has(e.to)).toBe(true)
    }
    expect(edges.size).toBeGreaterThan(0)
  })

  it('is just the course itself when it has no neighbours', () => {
    const { ids, edges } = chainOf(samplePlan, index, 'sem-1-csm101')
    expect([...ids]).toEqual(['sem-1-csm101'])
    expect(edges.size).toBe(0)
  })
})

describe('flags', () => {
  it('counts open errors and warnings, ignoring overridden ones', () => {
    expect(flagCounts(samplePlan.flags)).toEqual({ errors: 2, warnings: 1, confirm: 0 })
    const overridden = samplePlan.flags.map((f) => ({ ...f, overridden: true }))
    expect(flagCounts(overridden)).toEqual({ errors: 0, warnings: 0, confirm: 0 })
  })

  it('tells a claimed exception, which only needs confirming, from a real warning', () => {
    const base = samplePlan.flags[0]
    const confirm = { ...base, type: 'exception_claimed' as const, severity: 'warning' as const }
    const warning = { ...base, type: 'credit_shortfall' as const, severity: 'warning' as const }
    expect(flagKind(base)).toBe('error')
    expect(flagKind(warning)).toBe('warning')
    expect(flagKind(confirm)).toBe('confirm')
    expect(flagCounts([confirm, warning, base])).toEqual({ errors: 1, warnings: 1, confirm: 1 })
  })

  it('groups course flags and leaves out plan-wide ones', () => {
    const by = flagsByCourse(samplePlan.flags)
    expect(by.get('sem-5-csci400')?.[0].type).toBe('broken_prerequisite')
    expect([...by.keys()]).toEqual(['sem-5-csci400'])
  })
})

describe('creditLevel and subjectColor', () => {
  it('marks under full time, normal and overloaded semesters', () => {
    expect(creditLevel(6)).toBe('low')
    expect(creditLevel(15)).toBe('ok')
    expect(creditLevel(20)).toBe('high')
    expect(creditLevel(0)).toBe('ok')
    expect(creditLevel(3, 'Summer 2027')).toBe('ok') // a light Summer is normal
    expect(creditLevel(3, 'Spring 2027')).toBe('low')
    expect(creditLevel(21, 'Summer 2027')).toBe('high')
  })
  it('colours known subjects and greys the rest', () => {
    expect(subjectColor('CSCI200')).toContain('csci')
    expect(subjectColor('HASS100')).toContain('other')
  })
})

describe('edits on the board', () => {
  const ids = (p: typeof samplePlan, i: number) => p.semesters[i].courses.map((c) => c.course_id)

  it('moves a course to another semester and updates only the two totals shown', () => {
    const moved = movePlanned(samplePlan, 'sem-1-csm101', 1)
    expect(ids(moved, 0)).not.toContain('sem-1-csm101')
    expect(ids(moved, 1)).toContain('sem-1-csm101')
    expect(moved.semesters[0].total_credits).toBe(samplePlan.semesters[0].total_credits - 1)
    expect(moved.semesters[1].total_credits).toBe(samplePlan.semesters[1].total_credits + 1)
    expect(moved.semesters[2]).toBe(samplePlan.semesters[2]) // untouched semesters are the same objects
    expect(samplePlan.semesters[1].courses.some((c) => c.course_id === 'sem-1-csm101')).toBe(false) // input unchanged
  })

  it('leaves the plan alone for a move that goes nowhere', () => {
    expect(movePlanned(samplePlan, 'sem-1-csm101', 0)).toBe(samplePlan)
    expect(movePlanned(samplePlan, 'no-such-course', 2)).toBe(samplePlan)
    expect(movePlanned(samplePlan, 'sem-1-csm101', 99)).toBe(samplePlan)
  })

  it('inserts an empty semester, with ids that never repeat', () => {
    const once = insertSemester(samplePlan, 2, 'Summer 2027')
    expect(once.semesters.map((s) => s.label).slice(0, 4)).toEqual(['Fall 2026', 'Spring 2027', 'Summer 2027', 'Fall 2027'])
    expect(once.semesters[2]).toMatchObject({ courses: [], total_credits: 0 })
    const twice = insertSemester(once, 0, 'Summer 2026')
    expect(new Set(twice.semesters.map((s) => s.semester_id)).size).toBe(twice.semesters.length)
  })

  it('removes only a semester the student added and left empty', () => {
    const added = insertSemester(samplePlan, 2, 'Summer 2027')
    const id = added.semesters[2].semester_id
    expect(removeSemester(added, id).semesters).toHaveLength(samplePlan.semesters.length)
    expect(removeSemester(samplePlan, 'sem-1')).toBe(samplePlan) // a planned semester is never removed
    const filled = movePlanned(added, 'sem-1-csm101', 2)
    expect(isRemovable(filled.semesters[2])).toBe(false)
    expect(removeSemester(filled, id)).toBe(filled)
  })
})

describe('terms', () => {
  it('knows the term after each season', () => {
    expect(termAfter('Fall 2026')).toBe('Spring 2027')
    expect(termAfter('Spring 2027')).toBe('Summer 2027')
    expect(termAfter('Summer 2027')).toBe('Fall 2027')
    expect(termAfter('Winter 2027')).toBeNull()
  })

  it('picks the next regular term for a semester added at the end', () => {
    expect(nextRegularTerm('Spring 2030')).toBe('Fall 2030')
    expect(nextRegularTerm('Fall 2029')).toBe('Spring 2030')
    expect(nextRegularTerm('Summer 2028')).toBe('Fall 2028')
  })

  it('offers a Summer after each Spring that has none', () => {
    expect(summerSlots(samplePlan).map((s) => s.label)).toEqual(['Summer 2027', 'Summer 2028', 'Summer 2029', 'Summer 2030'])
    const withSummer = insertSemester(samplePlan, 2, 'Summer 2027')
    expect(summerSlots(withSummer).map((s) => s.label)).not.toContain('Summer 2027')
  })
})
