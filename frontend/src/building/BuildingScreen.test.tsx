import { act, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { BuildingScreen } from './BuildingScreen.tsx'
import { FACT_INTERVAL_MS, FACTS } from './facts.ts'
import { PAUSE_AFTER_USER_MS } from './FactSlideshow.tsx'
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

const visibleFact = () => document.querySelector('.fact-slide.on figcaption')?.textContent

describe('FACTS', () => {
  it('has a topic and text for each fact, with no repeats', () => {
    expect(FACTS.length).toBeGreaterThanOrEqual(8)
    for (const f of FACTS) {
      expect(f.topic.trim()).not.toBe('')
      expect(f.text.trim().length).toBeGreaterThan(30)
      expect(f.text.length).toBeLessThanOrEqual(110) // brief: about one short sentence
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

  it('moves to the next fact on its own', () => {
    render(<BuildingScreen request={request} onCancel={vi.fn()} factStart={0} />)
    expect(document.querySelectorAll('.fact-slide.on')).toHaveLength(1)
    expect(visibleFact()).toBe(FACTS[0].topic)
    act(() => vi.advanceTimersByTime(FACT_INTERVAL_MS))
    expect(visibleFact()).toBe(FACTS[1].topic)
    act(() => vi.advanceTimersByTime(FACT_INTERVAL_MS))
    expect(visibleFact()).toBe(FACTS[2].topic)
  })

  it('wraps around to the first fact after the last', () => {
    render(<BuildingScreen request={request} onCancel={vi.fn()} factStart={FACTS.length - 1} />)
    act(() => vi.advanceTimersByTime(FACT_INTERVAL_MS))
    expect(visibleFact()).toBe(FACTS[0].topic)
  })

  it('lets the student go back and forward with the arrows', () => {
    render(<BuildingScreen request={request} onCancel={vi.fn()} factStart={2} />)
    fireEvent.click(screen.getByRole('button', { name: 'Previous fact' }))
    expect(visibleFact()).toBe(FACTS[1].topic)
    fireEvent.click(screen.getByRole('button', { name: 'Next fact' }))
    fireEvent.click(screen.getByRole('button', { name: 'Next fact' }))
    expect(visibleFact()).toBe(FACTS[3].topic)
  })

  it('jumps to a fact from its dot', () => {
    render(<BuildingScreen request={request} onCancel={vi.fn()} factStart={0} />)
    fireEvent.click(screen.getByRole('button', { name: `Show fact 5: ${FACTS[4].topic}` }))
    expect(visibleFact()).toBe(FACTS[4].topic)
  })

  it('stops moving on by itself for a while after the student picks a fact', () => {
    render(<BuildingScreen request={request} onCancel={vi.fn()} factStart={0} />)
    fireEvent.click(screen.getByRole('button', { name: 'Previous fact' }))
    const chosen = visibleFact()
    act(() => vi.advanceTimersByTime(FACT_INTERVAL_MS * 1.5))
    expect(visibleFact()).toBe(chosen) // still on the one they went back to
    act(() => vi.advanceTimersByTime(PAUSE_AFTER_USER_MS))
    expect(visibleFact()).not.toBe(chosen) // then it carries on
  })

  it('hides the facts that are not showing from screen readers', () => {
    render(<BuildingScreen request={request} onCancel={vi.fn()} factStart={0} />)
    expect(document.querySelectorAll('.fact-slide[aria-hidden="true"]')).toHaveLength(FACTS.length - 1)
  })

  it('cancels', () => {
    const onCancel = vi.fn()
    render(<BuildingScreen request={request} onCancel={onCancel} factStart={0} />)
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }))
    expect(onCancel).toHaveBeenCalledTimes(1)
  })
})
