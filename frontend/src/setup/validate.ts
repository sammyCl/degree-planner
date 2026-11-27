import type { AgentRequest, CompletedCourse } from '../types.ts'
import options from './programOptions.json'
import summerPrograms from './summerPrograms.json'
import { startTerm, type Season } from './terms.ts'
import type { UploadedFile } from './transcript.ts'

export type Level = 'bachelor' | 'master' | 'combined'

export const LEVELS: { value: Level; label: string }[] = [
  { value: 'bachelor', label: "Bachelor's" },
  { value: 'master', label: "Master's" },
  { value: 'combined', label: 'Combined BS+MS' },
]

export interface ProgramOption {
  id: string
  name: string
  level: 'bachelor' | 'master' | 'combined' | 'minor' | 'asi' | 'certificate'
  /** the catalog the program was collected from; add-ons may be older than CATALOG_YEAR */
  catalog_year: string
}

export type AddOnKind = 'minor' | 'asi' | 'certificate'

export const CATALOG_YEAR: string = options.catalog_year
export const PROGRAMS = options.programs as ProgramOption[]

/** Semester limits and starting values per level (the limits match the backend: 1 to 18, or 1 to 15 for master's). */
export const SEMESTER_LIMITS: Record<Level, { min: number; max: number; default: number }> = {
  bachelor: { min: 1, max: 18, default: 8 },
  master: { min: 1, max: 15, default: 4 },
  combined: { min: 1, max: 18, default: 10 },
}

export const majorsFor = (level: Level): ProgramOption[] => PROGRAMS.filter((p) => p.level === level)
/** Degrees that require a summer course, with those courses (data/tools/build_summer_courses.py). */
export const SUMMER_PROGRAMS = summerPrograms as Record<string, string[]>

/**
 * Semester count, summers included, for a degree that requires a summer course: Fall to the last Spring, which is four
 * years for a bachelor's (11) and five for a combined degree (14). Undefined for every other degree.
 */
export const summerSemesters = (programId: string): number | undefined =>
  SUMMER_PROGRAMS[programId] ? (programId.includes('combined') ? 14 : 11) : undefined

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
  /** the student ticked "I have completed courses or transfer credit"; when false, no completed courses are sent */
  hasCompleted: boolean
  /** courses already finished, from an uploaded transcript and/or typed in; the student has reviewed them */
  completed: CompletedCourse[]
  /** the transcript files read so far, shown by name so the student knows the upload worked */
  files: UploadedFile[]
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

/** The request body for POST /plans/submit-setup. */
export function buildRequest(form: SetupForm): AgentRequest {
  const programs = [form.programId, ...(allowsAddOns(form.level) ? form.addOnIds : [])]
  return {
    student: {
      degree_level: form.level,
      programs,
      catalog_year: CATALOG_YEAR,
      completed_courses: form.hasCompleted ? form.completed : [],
    },
    semesters: form.semesters,
    start_term: startTerm(form.season, form.year),
    include_summers: form.includeSummers,
    overrides: [],
  }
}

/** "Minor in Computer Science" becomes "Computer Science"; the kind is shown next to it. */
export const shortName = (name: string): string =>
  name.replace(/^Minor in /, '').replace(/^Area of Special Interest in /, '').replace(/^(Online )?Graduate Certificate in /, '')

/** The minors, ASIs or certificates, alphabetical by the name shown in the picker. */
export const addOnsOfKind = (kind: AddOnKind): ProgramOption[] =>
  PROGRAMS.filter((p) => p.level === kind).sort((a, b) => shortName(a.name).localeCompare(shortName(b.name)))

/** Every minor, ASI and certificate. */
export const addOns = (): ProgramOption[] => (['minor', 'asi', 'certificate'] as const).flatMap(addOnsOfKind)

/** The minors, ASIs and certificates in a plan whose data is from an older catalog than the plan's, with the year used. */
export function staleInPlan(programIds: string[], planYear: string): { name: string; kind: AddOnKind; year: string }[] {
  return programIds.flatMap((id) => {
    const p = PROGRAMS.find((o) => o.id === id)
    return p && (p.level === 'minor' || p.level === 'asi' || p.level === 'certificate') && p.catalog_year !== planYear
      ? [{ name: shortName(p.name), kind: p.level, year: p.catalog_year }]
      : []
  })
}

export const ADD_ON_NAMES: Record<AddOnKind, { one: string; many: string; plural: string }> = {
  minor: { one: 'minor', many: 'Minors', plural: 'minors' },
  asi: { one: 'ASI', many: 'ASIs', plural: 'ASIs' },
  certificate: { one: 'certification', many: 'Certifications', plural: 'certifications' },
}
