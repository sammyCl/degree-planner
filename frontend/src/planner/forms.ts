// The Mines forms a student may need, in everyday words. The facts come from data/json/forms-policies.json (forms data
// slice); only the wording is written here, and forms.test.ts fails if that file gains, loses or relinks a form. Which
// forms a plan calls for is a simple reading of the plan, never a statement that nothing else is needed.
import { PROGRAMS } from '../setup/validate.ts'
import type { Plan } from '../types.ts'

export const REGISTRAR_FORMS = 'https://www.mines.edu/registrar/forms/'

export interface Form {
  id: string
  name: string
  /** the situation that calls for it */
  when: string
  /** what the student does */
  todo: string
  /** the page it is on; absent when none was collected */
  url?: string
  undergraduateOnly?: boolean
}

export const FORMS: Form[] = [
  {
    id: 'independent-study-credit',
    name: 'Independent Study Credit Form',
    when: 'You take an independent study course (its number ends in 99).',
    todo: 'Have you, the instructor and the department head sign it. Turn it in to the Registrar by Census Day (the last day to register) of that term.',
    url: REGISTRAR_FORMS,
  },
  {
    id: 'minor-declaration',
    name: 'Minor Declaration Form',
    when: 'You are adding a minor.',
    todo: 'It needs Registrar approval. Submit it when you apply to graduate, or, if you add the minor later, by the first day of your last term. A minor cannot be added after your degree is posted.',
    url: REGISTRAR_FORMS,
    undergraduateOnly: true,
  },
  {
    id: 'course-substitution',
    name: 'Course Substitution Form',
    when: 'You want one course to count in place of a required course.',
    todo: "Get it from the Registrar's Office. It needs approval from the Registrar, the heads of both courses' departments and your own department head.",
  },
  {
    id: 'transfer-course-approval',
    name: 'Transfer Course Approval Form',
    when: 'You want to take a course at another college.',
    todo: 'Get approval for how it will count. You can skip it for an ordinary free elective, unless you are unsure.',
    url: REGISTRAR_FORMS,
    undergraduateOnly: true,
  },
  {
    id: 'ten-year-course-approval',
    name: '10 Year Transfer Course Approval Form',
    when: 'A course you want to transfer was more than 10 years old when you started at Mines.',
    todo: "Have the course's department head and your degree's department head sign it, then email it to transfer@mines.edu. Use one form per Mines department.",
    url: REGISTRAR_FORMS,
    undergraduateOnly: true,
  },
  {
    id: 'decline-ap-ib-transfer-credit',
    name: 'Decline Credit Form (AP, IB or transfer)',
    when: 'You want to give up AP, IB or transfer credit, for example to take the Mines course instead.',
    todo: 'Email transfer@mines.edu from your Mines email.',
    url: REGISTRAR_FORMS,
  },
  {
    id: 'double-degree-declaration',
    name: 'Double Degree Declaration',
    when: "You want a second bachelor's degree.",
    todo: "Have you, your advisor, the department head and the Registrar sign it. List at least 30 credits that count only toward the second degree.",
    url: REGISTRAR_FORMS,
    undergraduateOnly: true,
  },
]

const INDEPENDENT_STUDY = /^[A-Z]{3,4}\d99$/

export interface PlanForm extends Form {
  /** why this plan calls for it */
  because: string
}

/** The forms this plan calls for, and the others the student may want. */
export function formsFor(plan: Plan): { needed: PlanForm[]; others: Form[] } {
  const reasons = new Map<string, string>()
  const studies = plan.semesters.flatMap((s) => s.courses.filter((c) => INDEPENDENT_STUDY.test(c.code)).map((c) => `${c.code} in ${s.label}`))
  if (studies.length) reasons.set('independent-study-credit', `Your plan has ${studies.join(' and ')}.`)
  const minors = plan.student.programs.map((id) => PROGRAMS.find((p) => p.id === id)).filter((p) => p?.level === 'minor')
  if (minors.length) reasons.set('minor-declaration', `Your plan includes ${minors.map((p) => p!.name).join(' and ')}.`)

  const graduate = plan.student.degree_level === 'master' || plan.student.degree_level === 'phd'
  const mine = FORMS.filter((f) => !(graduate && f.undergraduateOnly))
  return {
    needed: mine.flatMap((f) => (reasons.has(f.id) ? [{ ...f, because: reasons.get(f.id)! }] : [])),
    others: mine.filter((f) => !reasons.has(f.id)),
  }
}
