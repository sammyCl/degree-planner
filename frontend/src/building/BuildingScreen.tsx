import { useEffect, useState } from 'react'
import type { AgentRequest } from '../types.ts'
import { PROGRAMS, shortName } from '../setup/validate.ts'
import './BuildingScreen.css'

interface Props {
  request: AgentRequest
  /** stop waiting; the backend may still finish the run in the background */
  onCancel: () => void
}

const clock = (seconds: number): string => `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`

/** Shown while the agent works, which can take minutes: what was asked for, a running clock and a way out. */
export function BuildingScreen({ request, onCancel }: Props) {
  const [seconds, setSeconds] = useState(0)
  useEffect(() => {
    const id = setInterval(() => setSeconds((s) => s + 1), 1000)
    return () => clearInterval(id)
  }, [])

  const names = request.student.programs.map((id) => shortName(PROGRAMS.find((p) => p.id === id)?.name ?? id))
  return (
    <main className="building" aria-busy="true">
      <div className="building-card">
        <div className="orbit" aria-hidden="true">
          <i />
          <i />
          <i />
        </div>
        <h2>Building your plan</h2>
        <p className="building-sub">
          The planning assistant is choosing your courses and checking every prerequisite. This can take a few minutes, so
          keep this page open.
        </p>
        <dl className="building-facts">
          <div>
            <dt>Program</dt>
            <dd>{names.join(', ')}</dd>
          </div>
          <div>
            <dt>Starting</dt>
            <dd>{request.start_term}</dd>
          </div>
          <div>
            <dt>Semesters</dt>
            <dd>{request.semesters}</dd>
          </div>
        </dl>
        <p className="building-clock" role="timer" aria-label="Time spent so far">
          {clock(seconds)}
        </p>
        <button type="button" className="btn" onClick={onCancel}>
          Cancel
        </button>
      </div>
    </main>
  )
}
