import { describe, expect, it } from 'vitest'
import { defaultStart, semesterLabels } from './terms.ts'
import {
  addOnsOfKind,
  allowsAddOns,
  buildRequest,
  CATALOG_YEAR,
  majorsFor,
  PROGRAMS,
  SEMESTER_LIMITS,
  staleInPlan,
  validateSetup,
  type SetupForm,
} from './validate.ts'

const form = (over: Partial<SetupForm> = {}): SetupForm => ({
  level: 'bachelor',
  programId: 'cs-bs-general-track',
  addOnIds: [],
  season: 'Fall',
  year: 2026,
  semesters: 8,
  includeSummers: false,
  ...over,
})

describe('semesterLabels (same examples as docs/agent-request-format.md)', () => {
  it('alternates Fall and Spring without summers', () => {
    expect(semesterLabels('Fall', 2026, 3, false)).toEqual(['Fall 2026', 'Spring 2027', 'Fall 2027'])
  })
  it('adds Summer after Spring with summers', () => {
    expect(semesterLabels('Spring', 2027, 3, true)).toEqual(['Spring 2027', 'Summer 2027', 'Fall 2027'])
  })
  it('always keeps a Summer start term', () => {
    expect(semesterLabels('Summer', 2027, 3, false)).toEqual(['Summer 2027', 'Fall 2027', 'Spring 2028'])
  })
})

describe('defaultStart', () => {
  it('starts next Spring when today is in the fall', () => {
    expect(defaultStart(new Date(2026, 10, 22))).toEqual({ season: 'Spring', year: 2027 })
  })
  it('starts this Fall when today is in the spring or summer', () => {
    expect(defaultStart(new Date(2027, 2, 1))).toEqual({ season: 'Fall', year: 2027 })
  })
})

describe('program options', () => {
  it('has real bachelor, master and combined majors, and minors', () => {
    expect(majorsFor('bachelor').length).toBeGreaterThan(0)
    expect(majorsFor('master').length).toBeGreaterThan(0)
    expect(majorsFor('combined').length).toBeGreaterThan(0)
    expect(PROGRAMS.some((p) => p.level === 'minor')).toBe(true)
  })

  it('offers the newest ASI data stored, even from an older catalog year, and says which year it is', () => {
    const asis = addOnsOfKind('asi')
    expect(asis.length).toBeGreaterThan(0)
    expect(asis.every((a) => /^\d{4}-\d{4}$/.test(a.catalog_year))).toBe(true)
  })
  it('lists the add-ons in a plan whose data is from an older catalog, with the year used', () => {
    const asi = addOnsOfKind('asi')[0]
    const minor = addOnsOfKind('minor')[0]
    expect(staleInPlan([asi.id, minor.id, 'not-a-program'], CATALOG_YEAR)).toEqual([
      { name: expect.any(String), kind: 'asi', year: asi.catalog_year },
    ])
    expect(staleInPlan([minor.id], CATALOG_YEAR)).toEqual([])
  })
  it('has unique ids', () => {
    expect(new Set(PROGRAMS.map((p) => p.id)).size).toBe(PROGRAMS.length)
  })
})

describe('validateSetup', () => {
  it('accepts a good form', () => {
    expect(validateSetup(form())).toEqual({})
  })
  it('requires a program that matches the level', () => {
    expect(validateSetup(form({ programId: '' })).programId).toBeTruthy()
    expect(validateSetup(form({ level: 'master' })).programId).toBeTruthy() // a bachelor's id under master's
  })
  it('limits semesters by level', () => {
    expect(validateSetup(form({ semesters: 0 })).semesters).toBeTruthy()
    expect(validateSetup(form({ semesters: 19 })).semesters).toBeTruthy()
    expect(validateSetup(form({ semesters: 1.5 })).semesters).toBeTruthy()
    const m = majorsFor('master')[0].id
    expect(validateSetup(form({ level: 'master', programId: m, semesters: SEMESTER_LIMITS.master.max })).semesters).toBeUndefined()
    expect(validateSetup(form({ level: 'master', programId: m, semesters: 16 })).semesters).toBeTruthy()
  })
  it('rejects a bad year', () => {
    expect(validateSetup(form({ year: 26 })).year).toBeTruthy()
    expect(validateSetup(form({ year: NaN })).year).toBeTruthy()
  })
})

describe('buildRequest', () => {
  it('matches the shape of docs/agent-request.sample.json', () => {
    expect(buildRequest(form({ addOnIds: ['computer-science-minor'] }))).toEqual({
      student: {
        degree_level: 'bachelor',
        programs: ['cs-bs-general-track', 'computer-science-minor'],
        catalog_year: '2026-2027',
        completed_courses: [],
      },
      semesters: 8,
      start_term: 'Fall 2026',
      include_summers: false,
      overrides: [],
    })
  })
  it('drops minors and ASIs for a master\'s student', () => {
    expect(allowsAddOns('master')).toBe(false)
    const m = majorsFor('master')[0].id
    expect(buildRequest(form({ level: 'master', programId: m, addOnIds: ['x'] })).student.programs).toEqual([m])
  })
})
