import { useState } from 'react'
import { Markdown } from './markdown.tsx'

interface Props {
  explanation?: string
  /** why the assistant could not finish a valid plan; its last attempt is still drawn */
  problems?: string[]
}

/** Longer than this and the explanation starts collapsed behind "Show more". */
const COLLAPSE_OVER_CHARS = 320

/** What the planning assistant says about its plan, and any problems it could not solve. */
export function AssistantNote({ explanation, problems = [] }: Props) {
  const [expanded, setExpanded] = useState(false)
  if (!explanation && problems.length === 0) return null
  const long = (explanation?.length ?? 0) > COLLAPSE_OVER_CHARS

  return (
    <section className="assistant-note" aria-label="About this plan">
      {problems.length > 0 && (
        <div className="note-problems" role="alert">
          <b>The assistant could not finish a valid plan.</b> This is its last attempt; check the flagged courses.
          <ul>
            {problems.map((p, i) => (
              <li key={i}>{p}</li>
            ))}
          </ul>
        </div>
      )}
      {explanation && (
        <div className="note-explanation">
          <b>About this plan</b>
          <div className={long && !expanded ? 'note-text clamped' : 'note-text'}>
            <Markdown source={explanation} />
          </div>
          {long && (
            <button type="button" className="link" onClick={() => setExpanded((e) => !e)}>
              {expanded ? 'Show less' : 'Show more'}
            </button>
          )}
        </div>
      )}
    </section>
  )
}
