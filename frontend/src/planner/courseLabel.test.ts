import { describe, expect, it } from 'vitest'
import { samplePlan } from '../samplePlan.ts'
import type { Plan } from '../types.ts'
import { courseLabel, groupCategory } from './courseLabel.ts'

describe('groupCategory', () => {
  it.each([
    ['required', 'Core'],
    ['first-year-core', 'Core'],
    ['free-electives', 'Free elective'],
    ['focus-free', 'Free elective'],
    ['technical-electives', 'Tech elective'],
    ['con-technical', 'Tech elective'],
    ['cas-mid', 'CAS'],
    ['cas-400', 'CAS'],
    ['success-wellness', 'S&W'],
    ['cs-electives', 'CS elective'],
    ['ee-electives', 'EE elective'],
    ['mtgn-electives', 'Elective'],
    ['focus-circuits', 'Focus area'],
    ['track-engineering', 'Track'],
    ['something-unexpected', 'Requirement'],
  ])('%s is %s', (id, expected) => {
    expect(groupCategory(id)).toBe(expected)
  })
})

describe('courseLabel', () => {
  const degree = 'cs-bs-general-track'
  const plan = (counts: Plan['counts_toward']): Plan => ({ ...samplePlan, counts_toward: counts })
  const entry = (program_id: string, group_id: string) => ({ program_id, group_id, label: group_id })

  it('labels the real sample plan: core, free and CS electives, and an extra', () => {
    expect(courseLabel(samplePlan, 'sem-1-csci128')).toEqual({ primary: 'Core' })
    expect(courseLabel(samplePlan, 'sem-2-pagn101')).toEqual({ primary: 'Extra' }) // PAGN101 fills no group
    const labels = new Set(samplePlan.semesters.flatMap((s) => s.courses.map((c) => courseLabel(samplePlan, c.course_id)?.primary)))
    expect(labels).toEqual(new Set(['Core', 'Free elective', 'CS elective', 'Extra']))
  })

  it('says nothing when the plan carries no assignments', () => {
    expect(courseLabel({ ...samplePlan, counts_toward: undefined }, 'sem-1-csci128')).toBeNull()
    expect(courseLabel({ ...samplePlan, counts_toward: {} }, 'sem-1-csci128')).toBeNull()
  })

  it('says just Core when a course is core for the degree, whether or not it is also core for the minor', () => {
    const both = plan({ x: [entry('mining-bs', 'required'), entry('computer-science-minor', 'core')] })
    expect(courseLabel(both, 'x')).toEqual({ primary: 'Core', also: undefined })
  })

  it('shows a course that only fills a minor as Minor core or Minor elective, and an ASI the same way', () => {
    expect(courseLabel(plan({ x: [entry('computer-science-minor', 'core')] }), 'x')).toEqual({ primary: 'Minor core' })
    expect(courseLabel(plan({ x: [entry('computer-science-minor', 'electives')] }), 'x')).toEqual({ primary: 'Minor elective' })
    expect(courseLabel(plan({ x: [entry('aerospace-engineering-asi', 'core')] }), 'x')).toEqual({ primary: 'ASI core' })
  })

  it('shows both uses when one course counts for the degree and a minor', () => {
    const both = plan({ x: [entry(degree, 'cs-electives'), entry('computer-science-minor', 'core')] })
    expect(courseLabel(both, 'x')).toEqual({ primary: 'CS elective', also: 'Minor' })
    // the order the backend lists them in does not matter
    const reversed = plan({ x: [entry('computer-science-minor', 'core'), entry(degree, 'cs-electives')] })
    expect(courseLabel(reversed, 'x')).toEqual({ primary: 'CS elective', also: 'Minor' })
  })
})
