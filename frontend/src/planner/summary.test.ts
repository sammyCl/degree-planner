import { describe, expect, it } from 'vitest'
import { samplePlan } from '../samplePlan.ts'
import type { Plan, RequirementStatus } from '../types.ts'
import { buildChecklist, buildChecks, extractChoices } from './summary.ts'

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

describe('buildChecks', () => {
  const flag = (over: object) => ({ flag_id: 'f', type: 'exception_claimed', severity: 'warning', course_id: 'sem-1-csci128', message: 'CSCI128 relies on a claimed exception (instructor consent); confirm it still applies.', overridable: true, overridden: false, ...over })

  it('names the course by title and says what to confirm, without the number', () => {
    const plan = { ...samplePlan, flags: [flag({})] } as Plan
    expect(buildChecks(plan)).toEqual([
      { title: 'Computer Science for STEM', text: 'needs instructor consent; confirm it still applies', kind: 'confirm' },
    ])
  })

  it('includes warnings, leaves out errors and overridden flags', () => {
    const plan = {
      ...samplePlan,
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

describe('extractChoices', () => {
  // what the assistant really wrote in a real run
  const real = [
    'The plan meets every requirement. `check_plan` reports `requirements_met: true` with 130 of 130 credits, and every semester is at or under 18 credits.',
    '',
    "**Exceptions you need to decide.** The plan isn't final until you answer each one.",
    '- **MATH111** relies on a precalculus exception.',
    '- **CSCI478** relies on a prerequisite exception.',
    '',
    '**Choices I made.** I put the biology electives in the second year, and chose CBEN320 for the cell biology slot.',
    '',
    'I kept the summer free.',
  ].join('\n')

  it('keeps the choices and drops the tool talk and the exception list', () => {
    const blocks = extractChoices(real)
    const text = JSON.stringify(blocks)
    expect(text).toContain('I put the biology electives in the second year')
    expect(text).toContain('I kept the summer free.')
    expect(text).not.toMatch(/check_plan|requirements_met|Exceptions you need|MATH111/)
    expect(text).not.toContain('**Choices I made.**') // the panel already has that heading
  })

  it('shows nothing when the message only repeats the validation', () => {
    expect(extractChoices('The plan meets every requirement. `check_plan` says `requirements_met: true`.')).toEqual([])
  })

  it('passes plain text through', () => {
    expect(extractChoices('Plain explanation of the plan.')).toEqual([{ type: 'p', text: 'Plain explanation of the plan.' }])
  })

  it('keeps ordinary bullet lists', () => {
    expect(extractChoices('- first choice\n- second choice')).toEqual([{ type: 'ul', items: ['first choice', 'second choice'] }])
  })
})
