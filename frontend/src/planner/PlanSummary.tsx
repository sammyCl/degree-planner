import { useMemo, useState } from 'react'
import type { Plan } from '../types.ts'
import { Markdown } from './markdown.tsx'
import { buildChecklist, buildChecks, readExplanation } from './summary.ts'

interface Props {
  plan: Plan
  /** what the planning assistant wrote about the plan */
  explanation?: string
}

const Tick = ({ ok }: { ok: boolean }) => (
  <svg className={ok ? 'req-icon ok' : 'req-icon bad'} width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    {ok ? <path d="M5 12l5 5L20 7" /> : <path d="M6 6l12 12M18 6L6 18" />}
  </svg>
)

/** A short summary of the plan under the board: what is met, what to look at, and what the assistant chose. */
export function PlanSummary({ plan, explanation }: Props) {
  // starts closed under the board, so the flowchart is what the student sees first
  const [open, setOpen] = useState(false)
  const checklist = useMemo(() => buildChecklist(plan), [plan])
  const checks = useMemo(() => buildChecks(plan), [plan])
  const notes = useMemo(() => (explanation ? readExplanation(explanation, plan) : { choices: [], checks: [] }), [explanation, plan])
  const choices = notes.choices

  return (
    <section className="about" aria-label="About this plan">
      <div className="about-head">
        <h2>About this plan</h2>
        <button type="button" className="link" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
          {open ? 'Hide' : 'Show'}
        </button>
      </div>
      {open && (
        <div className="about-grid">
          <div className="about-card c-req">
            <h3>Degree requirements</h3>
            {checklist.map((section) => (
              <div className="req-section" key={section.title}>
                <div className="req-title">{section.title}</div>
                <ul className="req-list">
                  {section.rows.map((row) => (
                    <li key={row.name} className={`req-row ${row.met ? 'met' : 'unmet'}`}>
                      <Tick ok={row.met} />
                      <span className={`req-dot cat-${row.category}`} aria-hidden="true" />
                      <span className="req-name">{row.name}</span>
                      {row.detail && <span className="req-detail">{row.detail}</span>}
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>

          <div className="about-card c-check">
            <h3>Things to check</h3>
            {checks.length === 0 && notes.checks.length === 0 ? (
              <p className="about-none">
                <Tick ok /> Nothing needs your attention.
              </p>
            ) : (
              <ul className="check-list">
                {checks.map((item, i) => (
                  <li key={i} className={`check-item ${item.kind}`}>
                    {item.title && <b>{item.title}</b>} {item.text}
                  </li>
                ))}
                {notes.checks.map((text, i) => (
                  <li key={`note-${i}`} className="check-item note">
                    {text}
                  </li>
                ))}
              </ul>
            )}
          </div>

          {choices.length > 0 && (
            <div className="about-card c-choice">
              <h3>Choices I made</h3>
              <div className="choice-text">
                <Markdown source={choices.map((b) => (b.type === 'p' ? b.text : b.items.map((i) => `- ${i}`).join('\n'))).join('\n\n')} />
              </div>
            </div>
          )}
        </div>
      )}
    </section>
  )
}
