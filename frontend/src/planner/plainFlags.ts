// The validator's alerts in everyday words, each saying what to do. Only the wording changes here: which alerts there
// are, and how serious, is always the backend's call (validator.py). A message this file does not recognise is shown as
// the backend wrote it, so nothing is ever hidden. If the validator's wording changes, update the pattern here.
import { displayCode } from '../setup/transcript.ts'
import type { Flag, FlagType } from '../types.ts'

export interface PlainAlert {
  /** a few words: what is wrong */
  title: string
  /** one or two short sentences: what to do */
  text: string
}

const TITLES: Record<FlagType, string> = {
  broken_prerequisite: 'Course taken too early',
  credit_shortfall: 'Not enough credits',
  requirement_unmet: 'Missing course',
  double_count_exceeded: 'Too many shared credits',
  exception_claimed: 'Check you can take this',
  ineligible_course: 'Course taken too early',
  semester_overload: 'Semester too full',
  stale_program_year: 'Older rules',
  assumed_equivalent: 'Check this course swap',
  unlisted_course: 'Ask your advisor',
  undergraduate_prerequisite: 'Check your background',
  summer_course: 'Summer course',
}

const credits = (n: number): string => `${Math.round(n * 10) / 10} ${n === 1 ? 'credit' : 'credits'}`

/** "Free electives (3 courses)" as "Free electives". */
const plainGroup = (label: string): string => label.replace(/\s*\([^()]*\)\s*$/, '').trim()

/** A rule as the validator writes it, "((CSCI100 or an exception (instructor consent)) and MATH111)", in plain words. */
const plainRule = (rule: string): string => {
  const text = rule.replace(/an exception \(([^()]*)\)/g, '$1')
  return text.startsWith('(') && text.endsWith(')') ? text.slice(1, -1) : text
}

/** What to do about a rule the catalog words as something to check rather than a course to take. */
function exceptionAdvice(code: string, reason: string): string {
  const r = reason.toLowerCase()
  if (r.includes('independent study')) return `For ${code}, fill out the Independent Study form and send it to the Registrar.`
  if (r.includes('the catalog names')) return `${code} lists a required course we know nothing about. Ask your advisor if you can take it.`
  if (r === 'equivalent course') return `Make sure you took the course ${code} requires, or a similar one. Not sure? Ask your advisor.`
  if (r === 'instructor consent') return `${code} may need the instructor's OK. Ask them before you sign up.`
  if (r.startsWith('none')) return `The catalog is unclear about what ${code} requires. Ask your advisor.`
  return `Make sure you meet this before taking ${code}: ${reason}. Not sure? Ask your advisor.`
}

type Rule = [FlagType, RegExp, (m: string[]) => string | PlainAlert]

const RULES: Rule[] = [
  ['broken_prerequisite', /^(\S+) requires (.+) to be completed in an earlier semester\./, ([code, need]) =>
    `Take ${plainRule(need)} before ${code}. Move one of them to another semester.`],
  ['broken_prerequisite', /^(\S+) needs (.+) as a corequisite,/, ([code, need]) => ({
    title: 'Take these together',
    text: `Take ${plainRule(need)} before ${code}, or in the same semester.`,
  })],
  ['exception_claimed', /^(\S+) relies on a claimed exception \((.+)\); confirm it still applies\.$/, ([code, reason]) =>
    exceptionAdvice(code, reason)],
  ['undergraduate_prerequisite', /^(\S+) builds on (.+?): undergraduate coursework/, ([code, need]) =>
    `${code} expects you took ${plainRule(need)} in your bachelor's degree. If you didn't, ask your advisor.`],
  ['summer_course', /^(\S+) is taken in summer, .*Move it to a summer semester\.$/, ([code]) =>
    `${code} is usually a summer course. Move it to a summer, or ask your advisor.`],
  ['summer_course', /^(\S+) is taken in summer,/, ([code]) =>
    `${code} is usually a summer course. Add a summer semester for it, or ask your advisor.`],
  ['requirement_unmet', /^(\S+) is equivalent to (\S+), so only/, ([code, twin]) => ({
    title: 'Same course twice',
    text: `${code} and ${twin} count as one course. Replace ${code} with a different course.`,
  })],
  ['requirement_unmet', /^(.+?): (.+) needs (.+) in every fall and spring semester; missing in (.+)\.$/, ([, , codes, term]) =>
    `Add ${codes} to ${term}. You need it every fall and spring.`],
  ['requirement_unmet', /^(.+): only ([\d.]+) of its credits are not also used .*at least ([\d.]+) must not be/, ([program, have, need]) => ({
    title: 'Too much overlap',
    text: `${program} needs ${credits(Number(need) - Number(have))} more that don't also count for your degree. Add or swap courses.`,
  })],
  ['requirement_unmet', /^(.+?): (.+) is missing (.+)\.$/, ([, group, codes]) =>
    `Add ${codes} to your plan. Needed for: ${plainGroup(group)}.`],
  ['requirement_unmet', /^(.+?): (.+) needs (.+)\.$/, ([, group, rule]) =>
    `Add ${plainRule(rule)} to your plan. Needed for: ${plainGroup(group)}.`],
  ['credit_shortfall', /^Plan has ([\d.]+) credits; needs ([\d.]+)\.$/, ([have, need]) =>
    `Add ${credits(Number(need) - Number(have))}. This plan needs ${Number(need)} in total.`],
  ['credit_shortfall', /^(.+?): (.+) needs ([\d.]+) credits, only ([\d.]+) completed or planned\.$/, ([, group, need, have]) =>
    `Add ${credits(Number(need) - Number(have))} of ${plainGroup(group)}.`],
  ['semester_overload', /^(.+) has ([\d.]+) credits, over the ([\d.]+)-credit limit/, ([term, have, limit]) =>
    `${term} has ${credits(Number(have))}, but the most allowed is ${limit}. Move a course to another semester.`],
  ['double_count_exceeded', /share ([\d.]+) credits, over the ([\d.]+)-credit cap/, ([shared, cap]) =>
    `Only ${credits(Number(cap))} can count for both degrees, and you have ${Number(shared)}. Replace a shared course.`],
  ['ineligible_course', /^(\S+) is a 700-level course .* work planned through (.+?)\. Combined/, ([code, term]) =>
    `You can't take ${code} until your bachelor's courses are done. Move it after ${term}, or replace it.`],
  ['stale_program_year', /^(.+) is not in the (\S+) catalog data; using the newest version on record \((\S+)\)/, ([program, , used]) =>
    `We only have the ${used} rules for ${program}. Check them with your advisor.`],
  ['unlisted_course', /^(.+?): (.+) (?:requires|needs) ([A-Z].*?), which the course catalog data does not have\./, ([, group, codes]) =>
    `We have no information on ${codes}${plainGroup(group) === codes ? '' : `, needed for ${plainGroup(group)}`}. Ask your advisor how to take it.`],
  ['unlisted_course', /^(.+?): (.+) needs ([\d.]+) credits, but the courses in the data add up to only ([\d.]+)/, ([, group, need, have]) =>
    `We only found ${have} of the ${need} credits for ${plainGroup(group)}. Ask your advisor which courses count.`],
  ['assumed_equivalent', /^(\S+) stands in for (\S+) here/, ([actual, listed]) =>
    `We counted ${actual} in place of ${listed}. Ask your advisor if that's OK.`],
]

export function plainAlert(flag: Pick<Flag, 'type' | 'message'>): PlainAlert {
  const title = TITLES[flag.type] ?? 'Needs your attention'
  for (const [type, pattern, say] of RULES) {
    if (type !== flag.type) continue
    const match = pattern.exec(flag.message)
    if (!match) continue
    const said = say(match.slice(1))
    const alert = typeof said === 'string' ? { title, text: said } : said
    // transcript credit without a Mines course is "HASS2XX-1" in the data and "HASS 2XX" to a student
    return { ...alert, text: alert.text.replace(/\b[A-Z]{3,4}\d?XX-\d+\b/g, displayCode) }
  }
  return { title, text: flag.message }
}

/** The few words on a course card. */
export function cardWarning(type: FlagType, kind: 'error' | 'warning' | 'confirm'): string {
  if (type === 'broken_prerequisite' || type === 'ineligible_course') return TITLES[type]
  return kind === 'error' ? 'Fix this' : 'Please check'
}
