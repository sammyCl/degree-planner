// The newer backend fields on the planner page: flag types, course descriptions and corequisites, certificates.
import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import { samplePlan } from '../samplePlan.ts'
import type { Flag, Plan } from '../types.ts'
import { courseLabel } from './courseLabel.ts'
import { flagKind } from './graph.ts'
import { PlannerPage } from './PlannerPage.tsx'
import { describeRequirement } from './requirement.ts'
import { buildChecks } from './summary.ts'

const flag = (type: Flag['type'], course_id: string | null, message: string): Flag => ({
  flag_id: type,
  type,
  severity: 'warning',
  course_id,
  message,
  overridable: false,
  overridden: false,
})

describe('describeRequirement', () => {
  it('reads courses, AND, OR and exceptions in words', () => {
    const c = (code: string) => ({ type: 'course' as const, code })
    expect(describeRequirement({ type: 'OR', of: [c('MATH213'), c('MATH223')] })).toBe('MATH213 or MATH223')
    expect(describeRequirement({ type: 'AND', of: [c('CBEN210'), { type: 'OR', of: [c('CBEN200'), c('CBEN201')] }] })).toBe(
      'CBEN210 and (CBEN200 or CBEN201)',
    )
    expect(describeRequirement({ type: 'exception', label: 'instructor consent' })).toBe('instructor consent')
  })
})

describe('the newer flags', () => {
  const stale = flag('stale_program_year', null, 'Some ASI is not in the 2026-2027 catalog data; using 2025-2026.')

  it('shows an assumed equivalent as something to confirm, and titles both new types', () => {
    const equivalent = flag('assumed_equivalent', 'sem-1-csci128', 'CSCI128 stands in for X here. Confirm with your advisor.')
    expect(flagKind(equivalent)).toBe('confirm')
    expect(flagKind(stale)).toBe('warning')
    render(<PlannerPage plan={{ ...samplePlan, flags: [equivalent, stale] }} onBack={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: '1 to confirm' }))
    expect(screen.getByRole('menu')).toHaveTextContent('Confirm equivalent course')
    fireEvent.click(screen.getByRole('button', { name: '1 warning' }))
    expect(screen.getByRole('menu')).toHaveTextContent('Older catalog data')
  })

  it('does not repeat the older-catalog warning in Things to check, or note an equivalent the validator flagged', () => {
    const course = samplePlan.semesters.flatMap((s) => s.courses).find((x) => x.code === 'CSCI303')!
    const notes = (flags: Flag[]) => buildChecks({ ...samplePlan, flags })
    expect(notes([stale]).some((n) => n.text.includes('2025-2026'))).toBe(false)
    expect(notes([]).filter((n) => n.title === course.title)).toHaveLength(1) // the page's own note
    const flagged = notes([flag('assumed_equivalent', course.course_id, 'CSCI303 stands in for DSCI403 here.')])
    expect(flagged.filter((n) => n.title === course.title).map((n) => n.text)).toEqual(['CSCI303 stands in for DSCI403 here.'])
  })
})

describe('course details', () => {
  const long = `This course covers many things. ${'More about the course. '.repeat(20)}The very end.`
  const plan: Plan = {
    ...samplePlan,
    semesters: samplePlan.semesters.map((s) => ({
      ...s,
      courses: s.courses.map((c) =>
        c.code === 'CSCI128' ? { ...c, description: long, corequisites: { type: 'course' as const, code: 'MATH111' } } : c,
      ),
    })),
  }
  const open = (code: string) => fireEvent.click(screen.getByRole('button', { name: new RegExp(`^${code} `) }))

  it('shows the description shortened with the rest behind a button, and the corequisite', () => {
    render(<PlannerPage plan={plan} onBack={vi.fn()} />)
    open('CSCI128')
    const dialog = screen.getByRole('dialog')
    expect(dialog).toHaveTextContent('This course covers many things.')
    expect(dialog).not.toHaveTextContent('The very end.')
    expect(within(dialog).getByText('Take with, or before')).toBeInTheDocument()
    expect(dialog.querySelector('.pop-coreq')).toHaveTextContent('MATH111')
    fireEvent.click(within(dialog).getByRole('button', { name: 'Read more' }))
    expect(dialog).toHaveTextContent('The very end.')
  })

  it('shows neither for a course without them', () => {
    render(<PlannerPage plan={samplePlan} onBack={vi.fn()} />)
    open('CSCI128')
    expect(screen.queryByRole('button', { name: 'Read more' })).not.toBeInTheDocument()
    expect(screen.queryByText('Take with, or before')).not.toBeInTheDocument()
  })
})

describe('certificate courses', () => {
  it('are labelled like a minor, with the certificate named', () => {
    const plan: Plan = {
      ...samplePlan,
      counts_toward: { x: [{ program_id: 'data-science-certificate', group_id: 'required', label: 'Core' }] },
    }
    expect(courseLabel(plan, 'x')).toEqual({ primary: 'Certificate core' })
  })
})
