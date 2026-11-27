import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { samplePlan } from '../samplePlan.ts'
import type { Plan } from '../types.ts'
import { fixArrowStyles, headingLines, isPartOfPicture, sharpness } from './boardImage.ts'
import { buildPdfDocument } from './pdfContent.ts'
import { printable, renderPdf } from './pdfFile.ts'
import { PlannerPage } from './PlannerPage.tsx'

const saved = vi.hoisted(() => vi.fn())
vi.mock('./pdfFile.ts', async (original) => {
  const real = await original<typeof import('./pdfFile.ts')>()
  return {
    ...real,
    renderPdf: vi.fn((content: Parameters<typeof real.renderPdf>[0]) => {
      const pdf = real.renderPdf(content)
      pdf.save = saved
      return pdf
    }),
  }
})

const pictured = vi.hoisted(() => ({ toCanvas: vi.fn() }))
vi.mock('html-to-image', () => pictured)

const day = new Date(2026, 10, 27)
const withDone: Plan = {
  ...samplePlan,
  student: {
    ...samplePlan.student,
    completed_courses: [
      { code: 'FREE1XX-1', credits: 3, term: 'transfer', transfer_from: 'University of Colorado Denver' },
      { code: 'MATH111', credits: 4, term: 'aplcredit', transfer_from: null, in_progress: true },
    ],
  },
}

describe('buildPdfDocument', () => {
  it('lists every semester and course of the plan, in order', () => {
    const doc = buildPdfDocument({ plan: samplePlan }, day)
    expect(doc.semesters.map((t) => t.heading.replace(/ \(.*/, ''))).toEqual(samplePlan.semesters.map((s) => s.label))
    expect(doc.semesters.flatMap((t) => t.rows.map((r) => r[0]))).toEqual(
      samplePlan.semesters.flatMap((s) => s.courses.map((c) => c.code)),
    )
    expect(doc.details).toContain('Downloaded 2026-11-27')
    expect(doc.fileName).toMatch(/^degree-plan-[a-z0-9-]+-fall-2026\.pdf$/)
    const fresh = { ...samplePlan, student: { ...samplePlan.student, completed_courses: [] } }
    expect(buildPdfDocument({ plan: fresh }, day).completed).toBeNull()
  })

  it('puts open errors first and leaves accepted ones out', () => {
    const errors = samplePlan.flags.filter((f) => f.severity === 'error')
    const doc = buildPdfDocument({ plan: samplePlan }, day)
    expect(doc.alerts[0].heading).toBe(`This plan still has ${errors.length} problems to fix`)
    const accepted = { ...samplePlan, flags: samplePlan.flags.map((f) => ({ ...f, overridden: true })) }
    expect(buildPdfDocument({ plan: accepted }, day).alerts).toEqual([])
  })

  it('shows completed courses in board order, with placeholders written plainly', () => {
    const done = buildPdfDocument({ plan: withDone }, day).completed!
    expect(done.heading).toBe('Completed courses (7 credits)')
    expect(done.rows.map((r) => r[0])).toEqual(['MATH111', 'FREE 1XX'])
    expect(done.rows[0][3]).toBe('AP credit, in progress')
    expect(done.rows[1][3]).toBe('Transfer credit (University of Colorado Denver)')
  })

  it('includes the checklist and the notes for the advisor', () => {
    const doc = buildPdfDocument({ plan: samplePlan, checks: ['Ask about **field session**.'] }, day)
    expect(doc.requirements.at(-1)!.heading).toBe('Whole plan')
    expect(doc.notes.at(-1)!.items).toEqual(['Ask about field session.'])
  })
})

describe('renderPdf', () => {
  it('writes characters the PDF font lacks in plain form', () => {
    expect(printable('A → B — “ok” ≥ 3 Łódź 中')).toBe('A -> B - "ok" >= 3 ?ódz ?')
  })

  it('makes a PDF holding the courses, with numbered pages', () => {
    const out = renderPdf(buildPdfDocument({ plan: samplePlan }, day))
    const raw = out.output()
    expect(raw.startsWith('%PDF-')).toBe(true)
    expect(out.getNumberOfPages()).toBeGreaterThan(1)
    for (const c of samplePlan.semesters[0].courses) expect(raw).toContain(c.code)
    expect(raw).toContain(`Page 1 of ${out.getNumberOfPages()}`)
  })
})

describe('Download PDF button', () => {
  beforeEach(() => saved.mockReset())
  const slow = { timeout: 10000 } // the PDF library is loaded on the first click

  /** The button waits for the completed courses to be labelled (here the check fails at once, with no backend). */
  const clickDownload = async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('no backend')))
    render(<PlannerPage plan={samplePlan} onBack={() => {}} />)
    const button = screen.getByRole('button', { name: 'Download PDF' })
    await waitFor(() => expect(button).toBeEnabled())
    fireEvent.click(button)
  }
  afterEach(() => vi.unstubAllGlobals())

  it('saves the plan on screen as a PDF', async () => {
    await clickDownload()
    await waitFor(() => expect(saved).toHaveBeenCalledWith(expect.stringMatching(/^degree-plan-.*\.pdf$/)), slow)
  }, 15000)

  it('says so when the PDF cannot be made', async () => {
    saved.mockImplementationOnce(() => {
      throw new Error('blocked')
    })
    await clickDownload()
    expect(await screen.findByText('The PDF could not be made. Try again.', {}, slow)).toHaveAttribute('role', 'alert')
  }, 15000)
})

describe('flowchart image', () => {
  it('heads the picture with the program, the credits and any open problems', () => {
    const lines = headingLines(buildPdfDocument({ plan: samplePlan }, day))
    expect(lines[0].text).toBe('Bachelor of Science in Computer Science (General Track)')
    expect(lines.at(-1)).toMatchObject({ text: 'This plan still has 2 problems to fix', tone: 'error' })
  })

  it('leaves the edit buttons out', () => {
    const el = (name: string) => Object.assign(document.createElement('div'), { className: name })
    expect(isPartOfPicture(el('add-between'))).toBe(false)
    expect(isPartOfPicture(el('sem add-end'))).toBe(false)
    expect(isPartOfPicture(el('sem'))).toBe(true)
  })

  it('keeps a very long plan within what a browser can draw', () => {
    expect(sharpness(3000, 900)).toBe(2)
    expect(sharpness(20000, 900)).toBeLessThanOrEqual(0.8)
  })

  it('styles the arrows for the copy, then puts the page back', () => {
    const board = document.createElement('div')
    board.innerHTML = '<svg class="arrows"><path style="opacity: 0.5" /><path /></svg>'
    const [first, second] = Array.from(board.querySelectorAll('path'))
    const restore = fixArrowStyles(board)
    restore()
    expect(first.getAttribute('style')).toBe('opacity: 0.5')
    expect(second.hasAttribute('style')).toBe(false)
  })

  it('has its own button, and says so when the picture cannot be made', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new TypeError('no backend')))
    pictured.toCanvas.mockRejectedValue(new Error('blocked'))
    render(<PlannerPage plan={samplePlan} onBack={() => {}} />)
    const button = screen.getByRole('button', { name: 'Download flowchart' })
    await waitFor(() => expect(button).toBeEnabled())
    fireEvent.click(button)
    expect(await screen.findByText('The image could not be made. Try again.', {}, { timeout: 10000 })).toHaveAttribute('role', 'alert')
    expect(pictured.toCanvas).toHaveBeenCalledWith(screen.getByTestId('board'), expect.anything())
    expect(screen.getByTestId('board')).not.toHaveClass('exporting')
    vi.unstubAllGlobals()
  }, 15000)
})
