// Small, pure helpers for the "Completed courses" part of the setup page: checking a file before it is sent,
// merging what was read with what the student typed, and wording a term the way a student would say it.
import catalog from '../courseCatalog.json'
import type { CompletedCourse, UnmatchedCourse } from '../types.ts'

/** A transcript file that was read: its name and kind for the chip, and the courses it added to the list. */
export interface UploadedFile {
  name: string
  kind: 'pdf' | 'csv'
  /** how many courses were found in it */
  found: number
  /** the codes this file added (not ones already in the list), so removing the file removes only those */
  added: string[]
  /** the school the transcript is from, or null when it could not tell */
  school?: string | null
  fromMines?: boolean
  /** "Colorado Community College System" when the school is on Mines' preapproved list */
  system?: string | null
  /** courses from another school still waiting for a Mines equivalent (or to be skipped) */
  unmatched?: UnmatchedCourse[]
  /** rows that earn no Mines credit, with the reason */
  skipped?: string[]
  /** Mines' Transfer Evaluation System, where the student looks up a course from another school */
  tesUrl?: string
  /** schools the student can say the transcript is from (Mines, and every school with a saved list) */
  knownSchools?: string[]
  /** Claude read it (a layout the built-in reader does not know) */
  readByClaude?: boolean
  /** what the reader wants the student to know (for example, a scanned PDF it could not read) */
  notice?: string | null
}

/** Placeholder credit: "FREE1XX-3" or "HASS2XX" (a level of a subject, not a named course). */
const PLACEHOLDER = /^([A-Z]{2,5})(\d)XX(?:-(\d+))?$/
export const isPlaceholder = (code: string): boolean => PLACEHOLDER.test(code)

/** How a code reads on screen: "FREE1XX-3" is "FREE 1XX"; a real code stays as it is. */
export function displayCode(code: string): string {
  const m = PLACEHOLDER.exec(code)
  return m ? `${m[1]} ${m[2]}XX` : code
}

/** What a placeholder is, in words, for its card when the transcript gave no title. */
export const PLACEHOLDER_NAMES: Record<string, string> = {
  FREE1XX: 'Free elective credit',
  HASS2XX: 'CAS/HASS mid-level elective credit',
  CSM2XX: 'Success & Wellness credit',
  PAGN1XX: 'Physical activity credit',
}

/** The Mines course to show for a completed course: the catalog's title, else the transcript's, else the kind. */
export function completedTitle(c: CompletedCourse): string {
  if (isPlaceholder(c.code)) return c.title || PLACEHOLDER_NAMES[c.code.replace(/-\d+$/, '')] || 'Elective credit'
  return catalogCourse(c.code)?.title ?? c.title ?? (c.transfer_from ? `Transfer from ${c.transfer_from}` : 'Completed course')
}

/** Where a completed course came from, the way a student says it: "IB credit", "AP credit", "Transfer from X", "Fall 2025". */
export function sourceLabel(c: CompletedCourse): string {
  if (c.term === 'transfer' && c.transfer_from === 'IB credit') return 'IB credit'
  return `${termLabel(c.term)}${c.transfer_from ? ` (${c.transfer_from})` : ''}`
}

/** The next free number for a placeholder code among `taken`: FREE1XX with FREE1XX-1, -2 taken is FREE1XX-3. */
export function nextPlaceholder(base: string, taken: Set<string>): string {
  let n = 1
  while (taken.has(`${base}-${n}`)) n++
  return `${base}-${n}`
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
  if (!isKnownTerm(entry.term) && entry.term !== 'ibcredit') return 'Choose when you took it.'
  if (existing.some((c) => c.code === code)) return `${code} is already in the list.`
  return null
}

export function toCourse(entry: ManualCourse): CompletedCourse {
  if (entry.term === 'ibcredit') return { code: normalizeCode(entry.code), credits: Number(entry.credits), term: 'transfer', transfer_from: 'IB credit' }
  const transfer = entry.term === 'transfer' ? entry.transferFrom.trim() : ''
  return { code: normalizeCode(entry.code), credits: Number(entry.credits), term: entry.term, transfer_from: transfer || null }
}

/** The courses read from a file added to the list. A course already listed (same code) keeps the student's version. */
export function mergeCourses(existing: CompletedCourse[], incoming: CompletedCourse[]): { merged: CompletedCourse[]; added: number } {
  const have = new Set(existing.map((c) => c.code))
  const fresh: CompletedCourse[] = []
  for (const c of incoming) {
    let code = normalizeCode(c.code)
    // two transcripts both number their placeholders from 1: a second FREE1XX-1 is a different course, renumbered
    if (have.has(code) && isPlaceholder(code)) code = nextPlaceholder(code.replace(/-\d+$/, ''), have)
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
    { value: 'ibcredit', label: 'IB credit' },
  ]
  for (let year = thisYear; year >= thisYear - 8; year--) {
    for (const season of ['Fall', 'Summer', 'Spring']) {
      if (year === thisYear && season === 'Fall') continue // not yet taken
      options.push({ value: `${season} ${year}`, label: `${season} ${year}` })
    }
  }
  return options
}
