import { describe, expect, it } from 'vitest'
import type { CompletedCourse } from '../types.ts'
import { fileProblem, manualProblem, mergeCourses, normalizeCode, termLabel, termOptions, toCourse, totalCredits } from './transcript.ts'

const course = (code: string, credits = 3, term = 'Fall 2025'): CompletedCourse => ({ code, credits, term, transfer_from: null })

describe('fileProblem', () => {
  it('accepts a .csv or .pdf of a sensible size, in any letter case', () => {
    expect(fileProblem({ name: 'transcript.csv', size: 500 })).toBeNull()
    expect(fileProblem({ name: 'My Transcript.PDF', size: 500_000 })).toBeNull()
  })
  it('turns away other types, huge files and empty files, with the reason', () => {
    expect(fileProblem({ name: 'transcript.docx', size: 500 })).toMatch(/\.csv or \.pdf/)
    expect(fileProblem({ name: 'transcript', size: 500 })).toMatch(/\.csv or \.pdf/)
    expect(fileProblem({ name: 'a.pdf', size: 6 * 1024 * 1024 })).toMatch(/5 MB/)
    expect(fileProblem({ name: 'a.csv', size: 0 })).toMatch(/empty/)
  })
})

describe('typed-in courses', () => {
  const entry = { code: 'csci 128', credits: '3', term: 'Fall 2025', transferFrom: '' }
  it('tidies the code and builds the course', () => {
    expect(normalizeCode(' csci 128 ')).toBe('CSCI128')
    expect(manualProblem(entry, [])).toBeNull()
    expect(toCourse(entry)).toEqual({ code: 'CSCI128', credits: 3, term: 'Fall 2025', transfer_from: null })
  })
  it('keeps the sending school only for transfer credit', () => {
    expect(toCourse({ ...entry, term: 'transfer', transferFrom: ' Front Range CC ' }).transfer_from).toBe('Front Range CC')
    expect(toCourse({ ...entry, transferFrom: 'Front Range CC' }).transfer_from).toBeNull()
  })
  it('says what is wrong, one thing at a time', () => {
    expect(manualProblem({ ...entry, code: 'hello' }, [])).toMatch(/course code/)
    expect(manualProblem({ ...entry, credits: '' }, [])).toMatch(/credits/)
    expect(manualProblem({ ...entry, credits: '-1' }, [])).toMatch(/credits/)
    expect(manualProblem({ ...entry, credits: '40' }, [])).toMatch(/credits/)
    expect(manualProblem({ ...entry, term: '' }, [])).toMatch(/when/)
    expect(manualProblem(entry, [course('CSCI128')])).toBe('CSCI128 is already in the list.')
  })
})

describe('mergeCourses', () => {
  it('adds the new courses and keeps the student\'s own version of one already listed', () => {
    const mine = [course('MATH111', 4)]
    const { merged, added } = mergeCourses(mine, [course('math111', 3), course('CSCI128'), course('CSCI128')])
    expect(merged.map((c) => c.code)).toEqual(['MATH111', 'CSCI128'])
    expect(merged[0].credits).toBe(4)
    expect(added).toBe(1)
  })
})

describe('wording and totals', () => {
  it('words the special terms the way a student says them', () => {
    expect(termLabel('transfer')).toBe('Transfer credit')
    expect(termLabel('aplcredit')).toBe('AP credit')
    expect(termLabel('Fall 2024')).toBe('Fall 2024')
  })
  it('adds credits without floating-point noise', () => {
    expect(totalCredits([course('A100', 0.1), course('B100', 0.2), course('C100', 4)])).toBe(4.3)
  })
  it('offers transfer, AP and past Mines semesters, never a semester that has not happened', () => {
    const options = termOptions(2026)
    expect(options[0].value).toBe('transfer')
    expect(options[1].value).toBe('aplcredit')
    const values = options.map((o) => o.value)
    expect(values).toContain('Spring 2026')
    expect(values).toContain('Fall 2018')
    expect(values).not.toContain('Fall 2026')
    expect(new Set(values).size).toBe(values.length)
  })
})
