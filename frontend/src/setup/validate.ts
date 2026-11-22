import type { AgentRequest } from '../types.ts'
import options from './programOptions.json'
import { startTerm, type Season } from './terms.ts'

export type Level = 'bachelor' | 'master' | 'combined'

export const LEVELS: { value: Level; label: string }[] = [
  { value: 'bachelor', label: "Bachelor's" },
  { value: 'master', label: "Master's" },
  { value: 'combined', label: 'Combined BS+MS' },
]

export interface ProgramOption {
  id: string
  name: string
  level: 'bachelor' | 'master' | 'combined' | 'minor' | 'asi'
}

export const CATALOG_YEAR: string = options.catalog_year
export const PROGRAMS = options.programs as ProgramOption[]

/** Semester limits and starting values per level (the limits match the backend: 1 to 18, or 1 to 15 for master's). */
export const SEMESTER_LIMITS: Record<Level, { min: number; max: number; default: number }> = {
  bachelor: { min: 1, max: 18, default: 8 },
  master: { min: 1, max: 15, default: 4 },
  combined: { min: 1, max: 18, default: 10 },
}

export const majorsFor = (level: Level): ProgramOption[] => PROGRAMS.filter((p) => p.level === level)
export const addOns = (): ProgramOption[] => PROGRAMS.filter((p) => p.level === 'minor' || p.level === 'asi')
/** Minors and ASIs are undergraduate programs, so the picker is shown for bachelor's and combined only. */
export const allowsAddOns = (level: Level): boolean => level !== 'master'

export interface SetupForm {
  level: Level
  programId: string
  addOnIds: string[]
  season: Season
  year: number
  semesters: number
  includeSummers: boolean
}

export type SetupErrors = Partial<Record<'programId' | 'year' | 'semesters', string>>

export function validateSetup(form: SetupForm): SetupErrors {
  const errors: SetupErrors = {}
  if (!majorsFor(form.level).some((p) => p.id === form.programId)) {
    errors.programId = 'Choose your program.'
  }
  if (!Number.isInteger(form.year) || form.year < 2000 || form.year > 2500) {
    errors.year = 'Enter a four-digit year.'
  }
  const { min, max } = SEMESTER_LIMITS[form.level]
  if (!Number.isInteger(form.semesters) || form.semesters < min || form.semesters > max) {
    errors.semesters = `Choose between ${min} and ${max} semesters.`
  }
  return errors
}

/** The request body for POST /plans/submit-setup. Completed courses come with the transcript upload task. */
export function buildRequest(form: SetupForm): AgentRequest {
  const programs = [form.programId, ...(allowsAddOns(form.level) ? form.addOnIds : [])]
  return {
    student: { degree_level: form.level, programs, catalog_year: CATALOG_YEAR, completed_courses: [] },
    semesters: form.semesters,
    start_term: startTerm(form.season, form.year),
    include_summers: form.includeSummers,
    overrides: [],
  }
}

/** "Minor in Computer Science" becomes "Computer Science"; the kind is shown next to it. */
export const shortName = (name: string): string =>
  name.replace(/^Minor in /, '').replace(/^Area of Special Interest in /, '')
