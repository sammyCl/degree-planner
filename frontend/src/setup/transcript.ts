// Small, pure helpers for the "Completed courses" part of the setup page: checking a file before it is sent,
// merging what was read with what the student typed, and wording a term the way a student would say it.
import catalog from '../courseCatalog.json'
import type { CompletedCourse } from '../types.ts'

/** A transcript file that was read: its name and kind for the chip, and the courses it added to the list. */
export interface UploadedFile {
  name: string
  kind: 'pdf' | 'csv'
  /** how many courses were found in it */
  found: number
  /** the codes this file added (not ones already in the list), so removing the file removes only those */
  added: string[]
}

export const fileKind = (name: string): 'pdf' | 'csv' => (name.toLowerCase().endsWith('.pdf') ? 'pdf' : 'csv')

/** Every catalog course: code to [title, credits] (data/json/courses.json, built by data/tools/build_frontend_options.py). */
export const CATALOG = catalog as unknown as Record<string, [string, number]>

/** A course's catalog title and credits, or null for a code the catalog does not have. */
export function catalogCourse(code: string): { title: string; credits: number } | null {
  const entry = CATALOG[normalizeCode(code)]
  return entry ? { title: entry[0], credits: entry[1] } : null
}

export const MAX_FILE_BYTES = 5 * 1024 * 1024
const COURSE_CODE = /^[A-Z]{2,5}\d{3}[A-Z]?$/
const TERM = /^(Fall|Spring|Summer) \d{4}$/

/** The CSV format the backend reads (backend/transcript_parser.py), with two example rows. */
export const TEMPLATE_CSV = 'code,credits,term,transfer_from\nMATH111,4.0,Fall 2025,\nPHGN100,4.0,transfer,Front Range Community College\n'

/** "csci 128" and "CSCI128 " both become "CSCI128". */
export const normalizeCode = (raw: string): string => raw.replace(/\s+/g, '').toUpperCase()

/** A file the page will send: .csv or .pdf, and not huge. Returns the reason it will not, or null. */
export function fileProblem(file: { name: string; size: number }): string | null {
  const ext = /\.[^./\\]+$/.exec(file.name)?.[0].toLowerCase()
  if (ext !== '.csv' && ext !== '.pdf') return 'Upload a .csv or .pdf file.'
  if (file.size > MAX_FILE_BYTES) return 'That file is over 5 MB. A transcript should be much smaller.'
  if (file.size === 0) return 'That file is empty.'
  return null
}

/** How a term reads on screen: "Fall 2025", "Transfer credit" or "AP credit". */
export function termLabel(term: string): string {
  const t = term.trim().toLowerCase()
  if (t === 'transfer') return 'Transfer credit'
  if (t === 'aplcredit') return 'AP credit'
  return term
}

export const isKnownTerm = (term: string): boolean => TERM.test(term) || term === 'transfer' || term === 'aplcredit'

export interface ManualCourse {
  code: string
  credits: string
  term: string
  transferFrom: string
}

/** What is wrong with a course the student typed, or null. `existing` is checked for a repeat of the same course. */
export function manualProblem(entry: ManualCourse, existing: CompletedCourse[]): string | null {
  const code = normalizeCode(entry.code)
  if (!COURSE_CODE.test(code)) return 'Enter a course code like MATH111.'
  const credits = Number(entry.credits)
  if (entry.credits.trim() === '' || !Number.isFinite(credits) || credits < 0 || credits > 20) return 'Enter the credits, from 0 to 20.'
  if (!isKnownTerm(entry.term)) return 'Choose when you took it.'
  if (existing.some((c) => c.code === code)) return `${code} is already in the list.`
  return null
}

export function toCourse(entry: ManualCourse): CompletedCourse {
  const transfer = entry.term === 'transfer' ? entry.transferFrom.trim() : ''
  return { code: normalizeCode(entry.code), credits: Number(entry.credits), term: entry.term, transfer_from: transfer || null }
}

/** The courses read from a file added to the list. A course already listed (same code) keeps the student's version. */
export function mergeCourses(existing: CompletedCourse[], incoming: CompletedCourse[]): { merged: CompletedCourse[]; added: number } {
  const have = new Set(existing.map((c) => c.code))
  const fresh: CompletedCourse[] = []
  for (const c of incoming) {
    const code = normalizeCode(c.code)
    if (have.has(code)) continue
    have.add(code)
    fresh.push({ ...c, code })
  }
  return { merged: [...existing, ...fresh], added: fresh.length }
}

export const totalCredits = (courses: CompletedCourse[]): number =>
  Math.round(courses.reduce((sum, c) => sum + c.credits, 0) * 10) / 10

/** Terms the student can pick for a course they took: transfer, AP, then Mines semesters back from this year. */
export function termOptions(thisYear: number): { value: string; label: string }[] {
  const options = [
    { value: 'transfer', label: 'Transfer credit' },
    { value: 'aplcredit', label: 'AP credit' },
  ]
  for (let year = thisYear; year >= thisYear - 8; year--) {
    for (const season of ['Fall', 'Summer', 'Spring']) {
      if (year === thisYear && season === 'Fall') continue // not yet taken
      options.push({ value: `${season} ${year}`, label: `${season} ${year}` })
    }
  }
  return options
}
