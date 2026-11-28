import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import formsData from '../../../data/json/forms-policies.json'
import { samplePlan } from '../samplePlan.ts'
import { PROGRAMS } from '../setup/validate.ts'
import type { Plan } from '../types.ts'
import { FORMS, formsFor } from './forms.ts'
import { buildPdfDocument } from './pdfContent.ts'
import { PlannerPage } from './PlannerPage.tsx'

const withStudy: Plan = {
  ...samplePlan,
  semesters: samplePlan.semesters.map((s, i) =>
    i === 0 ? { ...s, courses: [...s.courses, { course_id: 'x', code: 'CSCI499', title: 'Independent Study', credits: 3, status: 'planned' }] } : s,
  ),
}

describe('forms', () => {
  it('covers every form in the data, with the same links (data/json/forms-policies.json)', () => {
    const data = formsData as { forms: { form_id: string; url?: string }[] }
    // policies are rules, not forms; the residency petition is about tuition, not the degree plan
    const real = data.forms.filter((f) => !f.form_id.startsWith('policy-') && f.form_id !== 'graduate-residency-petition')
    expect(FORMS.map((f) => f.id).sort()).toEqual(real.map((f) => f.form_id).sort())
    for (const f of real) expect(FORMS.find((x) => x.id === f.form_id)!.url).toBe(f.url)
  })

  it('picks out what the plan calls for, and says why', () => {
    expect(formsFor(samplePlan).needed).toEqual([])
    const minor = PROGRAMS.find((p) => p.level === 'minor')!
    const both = { ...withStudy, student: { ...withStudy.student, programs: [...withStudy.student.programs, minor.id] } }
    const { needed, others } = formsFor(both)
    expect(needed.map((f) => f.id)).toEqual(['independent-study-credit', 'minor-declaration'])
    expect(needed[0].because).toBe(`Your plan has CSCI499 in ${samplePlan.semesters[0].label}.`)
    expect(needed.length + others.length).toBe(FORMS.length)
  })

  it('leaves undergraduate forms out for a graduate student', () => {
    const master = { ...samplePlan, student: { ...samplePlan.student, degree_level: 'master' } }
    expect(formsFor(master).others.map((f) => f.id)).toEqual(['independent-study-credit', 'course-substitution', 'decline-ap-ib-transfer-credit'])
  })

  it('shows them on the planner page, the others behind a click', () => {
    render(<PlannerPage plan={withStudy} onBack={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: 'Show' }))
    expect(screen.getByText(/Turn it in to the Registrar by Census Day/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Registrar forms page/ })).toHaveAttribute('rel', 'noreferrer noopener')
    expect(screen.queryByText('Course Substitution Form')).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /See \d+ other forms/ }))
    fireEvent.click(screen.getByRole('button', { name: 'Course Substitution Form' }))
    expect(screen.getByText(/Get it from the Registrar's Office/)).toBeInTheDocument()
  })

  it('puts the forms the plan calls for in the PDF', () => {
    const notes = buildPdfDocument({ plan: withStudy }).notes
    expect(notes.find((n) => n.heading === 'Forms your plan needs')!.items[0]).toMatch(/^Independent Study Credit Form: Your plan has CSCI499/)
    expect(buildPdfDocument({ plan: samplePlan }).notes.some((n) => n.heading === 'Forms your plan needs')).toBe(false)
  })
})
