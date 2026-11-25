import { act, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { BuildingScreen } from './BuildingScreen.tsx'
import { FACTS } from './facts.ts'
import type { AgentRequest } from '../types.ts'

const request: AgentRequest = {
  student: { degree_level: 'bachelor', programs: ['cs-bs-general-track'], catalog_year: '2026-2027', completed_courses: [] },
  semesters: 8,
  start_term: 'Fall 2026',
  include_summers: false,
  overrides: [],
}

beforeEach(() => vi.useFakeTimers())
afterEach(() => vi.useRealTimers())

const visibleFact = () => document.querySelector('.fact.on figcaption')?.textContent

describe('FACTS', () => {
  it('has a topic and text for each fact, with no repeats', () => {
    expect(FACTS.length).toBeGreaterThanOrEqual(8)
    for (const f of FACTS) {
      expect(f.topic.trim()).not.toBe('')
      expect(f.text.trim().length).toBeGreaterThan(40)
    }
    expect(new Set(FACTS.map((f) => f.topic)).size).toBe(FACTS.length)
    expect(new Set(FACTS.map((f) => f.text)).size).toBe(FACTS.length)
  })
})

describe('BuildingScreen', () => {
  it('says what is being built and no longer shows a clock', () => {
    render(<BuildingScreen request={request} onCancel={vi.fn()} factStart={0} />)
    expect(screen.getByRole('heading', { name: 'Building your plan' })).toBeInTheDocument()
    expect(screen.getByText(/Computer Science \(General Track\).*starting Fall 2026.*8 semesters/)).toBeInTheDocument()
    expect(screen.queryByRole('timer')).not.toBeInTheDocument()
  })

  it('shows one fact at a time and moves to the next on its own', () => {
    render(<BuildingScreen request={request} onCancel={vi.fn()} factStart={0} />)
    expect(document.querySelectorAll('.fact.on')).toHaveLength(1)
    expect(visibleFact()).toBe(FACTS[0].topic)
    act(() => vi.advanceTimersByTime(6500))
    expect(visibleFact()).toBe(FACTS[1].topic)
    act(() => vi.advanceTimersByTime(6500))
    expect(visibleFact()).toBe(FACTS[2].topic)
  })

  it('wraps around to the first fact after the last', () => {
    render(<BuildingScreen request={request} onCancel={vi.fn()} factStart={FACTS.length - 1} />)
    expect(visibleFact()).toBe(FACTS[FACTS.length - 1].topic)
    act(() => vi.advanceTimersByTime(6500))
    expect(visibleFact()).toBe(FACTS[0].topic)
  })

  it('hides the facts that are not showing from screen readers', () => {
    render(<BuildingScreen request={request} onCancel={vi.fn()} factStart={0} />)
    const hidden = document.querySelectorAll('.fact[aria-hidden="true"]')
    expect(hidden).toHaveLength(FACTS.length - 1)
  })

  it('cancels', () => {
    const onCancel = vi.fn()
    render(<BuildingScreen request={request} onCancel={onCancel} factStart={0} />)
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(onCancel).toHaveBeenCalledTimes(1)
  })
})
