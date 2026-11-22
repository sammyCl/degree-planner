import { describe, expect, it } from 'vitest'
import { samplePlan } from '../samplePlan.ts'
import { chainOf, creditLevel, flagCounts, flagsByCourse, indexPlan, subjectColor } from './graph.ts'

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
    expect(flagCounts(samplePlan.flags)).toEqual({ errors: 2, warnings: 1 })
    const overridden = samplePlan.flags.map((f) => ({ ...f, overridden: true }))
    expect(flagCounts(overridden)).toEqual({ errors: 0, warnings: 0 })
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
  })
  it('colours known subjects and greys the rest', () => {
    expect(subjectColor('CSCI200')).toContain('csci')
    expect(subjectColor('HASS100')).toContain('other')
  })
})
