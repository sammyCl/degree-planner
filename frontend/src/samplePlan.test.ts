import { describe, expect, it } from 'vitest'
import { samplePlan } from './samplePlan.ts'

describe('sample plan fixture', () => {
  const ids = samplePlan.semesters.flatMap((s) => s.courses.map((c) => c.course_id))

  it('has unique course ids', () => {
    expect(new Set(ids).size).toBe(ids.length)
  })

  it('has semester totals that match their courses', () => {
    for (const s of samplePlan.semesters) {
      expect(s.total_credits).toBe(s.courses.reduce((sum, c) => sum + c.credits, 0))
    }
  })

  it('has edges and flags that point at courses in the plan', () => {
    for (const e of samplePlan.prerequisite_edges) {
      expect(ids).toContain(e.from)
      expect(ids).toContain(e.to)
    }
    for (const f of samplePlan.flags) {
      if (f.course_id !== null) expect(ids).toContain(f.course_id)
    }
  })

  it('draws prerequisite arrows forward in time except the deliberate broken one', () => {
    const semOf = (id: string) => samplePlan.semesters.findIndex((s) => s.courses.some((c) => c.course_id === id))
    const broken = samplePlan.prerequisite_edges.filter((e) => semOf(e.from) >= semOf(e.to))
    expect(broken).toEqual([{ from: 'sem-5-csci306', to: 'sem-5-csci400' }])
    expect(samplePlan.flags.some((f) => f.type === 'broken_prerequisite' && f.course_id === 'sem-5-csci400')).toBe(true)
  })

  it('has a summary that adds the completed courses to the planned credits', () => {
    const planned = samplePlan.semesters.reduce((sum, s) => sum + s.total_credits, 0)
    const done = samplePlan.student.completed_courses.reduce((sum, c) => sum + c.credits, 0)
    expect(samplePlan.summary.total_credits).toBe(planned + done)
  })
})
