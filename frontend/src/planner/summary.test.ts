import { describe, expect, it } from 'vitest'
import { samplePlan } from '../samplePlan.ts'
import type { Plan, RequirementStatus } from '../types.ts'
import { buildChecklist, buildChecks, readExplanation } from './summary.ts'

const status = (over: Partial<RequirementStatus>): RequirementStatus => ({
  program_id: 'cs-bs-general-track',
  group_id: 'required',
  label: 'Required core',
  kind: 'all',
  met: true,
  credits_required: null,
  credits_earned: null,
  missing_count: 0,
  ...over,
})

describe('buildChecklist', () => {
  it('turns the backend\'s group statuses into short rows, with no course numbers', () => {
    const sections = buildChecklist(samplePlan)
    const degree = sections[0]
    expect(degree.title).toBe('Bachelor of Science in Computer Science (General Track)')
    const row = (name: string) => degree.rows.find((r) => r.name === name)!
    expect(row('Core courses')).toMatchObject({ met: false, detail: '3 courses missing', category: 'core' })
    expect(row('CS electives')).toMatchObject({ met: true, detail: '18/18 credits', category: 'elective' })
    expect(row('Free electives')).toMatchObject({ met: true, category: 'free' })
    expect(JSON.stringify(sections)).not.toMatch(/[A-Z]{3,4}\d{3}/) // no course codes anywhere
  })

  it('merges groups of one kind into one row, adding their credits', () => {
    const plan: Plan = {
      ...samplePlan,
      requirement_status: [
        status({ group_id: 'cas-mid', kind: 'choose_credits', credits_required: 6, credits_earned: 6 }),
        status({ group_id: 'cas-400', kind: 'choose_credits', credits_required: 3, credits_earned: 0, met: false }),
      ],
    }
    const rows = buildChecklist(plan)[0].rows
    expect(rows).toHaveLength(1)
    expect(rows[0]).toMatchObject({ name: 'Culture & Society (CAS)', met: false, detail: '6/9 credits' })
  })

  it('never shows more credits earned than required', () => {
    const plan: Plan = { ...samplePlan, requirement_status: [status({ group_id: 'free-electives', kind: 'choose_credits', credits_required: 18, credits_earned: 20 })] }
    expect(buildChecklist(plan)[0].rows[0].detail).toBe('18/18 credits')
  })

  it('keeps a separate section for each program, such as a minor', () => {
    const plan: Plan = {
      ...samplePlan,
      requirement_status: [status({}), status({ program_id: 'computer-science-minor', group_id: 'core' })],
    }
    const titles = buildChecklist(plan).map((s) => s.title)
    expect(titles).toEqual(['Bachelor of Science in Computer Science (General Track)', 'Minor in Computer Science', 'Whole plan'])
  })

  it('ends with the plan-wide checks', () => {
    const whole = buildChecklist(samplePlan).at(-1)!
    expect(whole.title).toBe('Whole plan')
    expect(whole.rows.find((r) => r.name === 'Total credits')).toMatchObject({ met: false, detail: '114/130 credits' })
    expect(whole.rows.find((r) => r.name === 'Prerequisites in order')).toMatchObject({ met: false, detail: '1 course out of order' })
  })

  it('still gives the plan-wide checks for an older plan without statuses', () => {
    const sections = buildChecklist({ ...samplePlan, requirement_status: undefined })
    expect(sections.map((s) => s.title)).toEqual(['Whole plan'])
  })
})

/** the sample plan has CSCI303, which the data treats as the same course as DSCI403; these tests are about other notes */
const withoutAssumedEquivalents = (plan: Plan): Plan => ({
  ...plan,
  semesters: plan.semesters.map((s) => ({ ...s, courses: s.courses.filter((c) => c.code !== 'CSCI303') })),
})

describe('buildChecks', () => {
  const flag = (over: object) => ({ flag_id: 'f', type: 'exception_claimed', severity: 'warning', course_id: 'sem-1-csci128', message: 'CSCI128 relies on a claimed exception (instructor consent); confirm it still applies.', overridable: true, overridden: false, ...over })

  it('names the course by title and says what to confirm, without the number', () => {
    const plan = { ...withoutAssumedEquivalents(samplePlan), flags: [flag({})] } as Plan
    expect(buildChecks(plan)).toEqual([
      { title: 'Computer Science for STEM', text: 'needs instructor consent; confirm it still applies', kind: 'confirm' },
    ])
  })

  it('includes warnings, leaves out errors and overridden flags', () => {
    const plan = {
      ...withoutAssumedEquivalents(samplePlan),
      flags: [
        flag({ flag_id: 'w', type: 'credit_shortfall', course_id: null, message: 'Spring 2030 is light.' }),
        flag({ flag_id: 'e', type: 'broken_prerequisite', severity: 'error' }),
        flag({ flag_id: 'o', overridden: true }),
      ],
    } as Plan
    const checks = buildChecks(plan)
    expect(checks).toEqual([{ title: '', text: 'Spring 2030 is light.', kind: 'warning' }])
  })
})

describe('buildChecks: assumed equivalents and the minor credit note', () => {
  const course = (code: string, title: string) => ({ course_id: `c-${code}`, code, title, credits: 3, status: 'planned' as const })
  const withCourses = (codes: [string, string][], programs: string[], total = 142): Plan => ({
    ...samplePlan,
    flags: [],
    student: { ...samplePlan.student, programs },
    summary: { ...samplePlan.summary, total_credits: total, total_credits_required: 131 },
    semesters: [{ ...samplePlan.semesters[0], courses: codes.map(([c, t]) => course(c, t)) }],
  })

  it('asks the student to confirm a course the data treats as the same as another', () => {
    const checks = buildChecks(withCourses([['MNGN310', 'Earth Materials']], ['mining-bs']))
    const item = checks.find((c) => c.title === 'Earth Materials')!
    expect(item.kind).toBe('confirm')
    expect(item.text).toContain('GEOL310')
    expect(item.text).toMatch(/^Counted as the same course as GEOL310; confirm with your advisor./)
    expect(buildChecks(withCourses([['MATH111', 'Calculus']], ['mining-bs'])).some((c) => c.kind === 'confirm')).toBe(false)
  })

  it('says a minor adds about 9 credits beyond the degree, with this plan\'s numbers', () => {
    const checks = buildChecks(withCourses([['MATH111', 'Calculus']], ['mining-bs', 'biology-minor']))
    const note = checks.find((c) => c.title === 'Credits')!
    expect(note.kind).toBe('info')
    expect(note.text).toContain('A minor adds about 9 credits beyond your degree')
    expect(note.text).toContain('142 credits')
    expect(note.text).toContain('131')
    expect(buildChecks(withCourses([['MATH111', 'Calculus']], ['mining-bs'])).some((c) => c.title === 'Credits')).toBe(false)
  })
})

describe('readExplanation', () => {
  // what the assistant really wrote in a real run (CS General Track, 2026-11-24), shortened
  const real = [
    'It totals 128 of the 128 required credits across all 8 semesters, with no errors, warnings or open exceptions. No semester goes over 18 credits.',
    '',
    '**Order of courses**',
    '- **Spring 2027 to Spring 2028:** the first-year core (MATH111, CSCI128), then CSCI200 and CSCI210.',
    '- **Fall 2028:** CSCI220 and CSCI341.',
    '',
    '**Choices I made** (you can change any of these)',
    '- **Computer Science electives (18 credits):** CSCI403 and CSCI445. I first tried CSCI422, but it needs CSCI262, so I swapped it.',
    '- **First-year requirement:** I used HASS100 and EDNS151 rather than the honors pair.',
    '',
    '**Things to check with your advisor**',
    "- The catalog lists MATH334's corequisite oddly; I planned only MATH213, and the checker accepted it.",
    '- The data does not include rules such as requiring one elective at the 400 level, so confirm the final plan with your advisor.',
  ].join('\n')

  it('keeps the choices, in plain words, with course titles instead of numbers where the course is in the plan', () => {
    const { choices } = readExplanation(real, samplePlan)
    const text = JSON.stringify(choices)
    expect(text).toContain('Data Base Management and Web Programming') // CSCI403 and CSCI445
    expect(text).toContain('Nature and Human Values and Cornerstone - Design I') // HASS100 and EDNS151
    expect(text).toContain('CSCI422') // not in the plan: kept as written
    expect(text).not.toMatch(/It totals|no errors|goes over/)
    expect(text).not.toContain('you can change any of these')
  })

  it('drops the semester-by-semester rundown, which the board already shows', () => {
    const text = JSON.stringify(readExplanation(real, samplePlan))
    expect(text).not.toContain('Spring 2027 to Spring 2028')
    expect(text).not.toContain('Order of courses')
  })

  it('moves the advisor notes to the things to check, and drops a note that is only about the tools', () => {
    const { checks } = readExplanation(real, samplePlan)
    expect(checks).toHaveLength(1) // the MATH334 note is about what "the checker" accepted, not advice for a student
    expect(checks[0]).toContain('confirm the final plan with your advisor')
    expect(checks.join(' ')).not.toContain('corequisite') // not even half of the dropped note
  })

  it('drops the exception list (the flags show it) and the sentences about the tools', () => {
    const text = 'The plan meets every requirement. `check_plan` reports `requirements_met: true`.\n\n**Exceptions you need to decide.** Decide.\n- **MATH111** needs a note\n\nI put the electives in year two.'
    const { choices, checks } = readExplanation(text, samplePlan)
    expect(choices).toEqual([{ type: 'p', text: 'I put the electives in year two.' }])
    expect(checks).toEqual([])
  })

  it('passes plain text and ordinary lists through', () => {
    expect(readExplanation('Plain explanation of the plan.', samplePlan).choices).toEqual([{ type: 'p', text: 'Plain explanation of the plan.' }])
    expect(readExplanation('- first choice\n- second choice', samplePlan).choices).toEqual([{ type: 'ul', items: ['first choice', 'second choice'] }])
  })
})
