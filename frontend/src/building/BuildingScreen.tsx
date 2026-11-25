import type { AgentRequest } from '../types.ts'
import { PROGRAMS, shortName } from '../setup/validate.ts'
import { FACTS } from './facts.ts'
import { FactSlideshow } from './FactSlideshow.tsx'
import { PlanAnimation } from './PlanAnimation.tsx'
import './BuildingScreen.css'

interface Props {
  request: AgentRequest
  /** stop waiting; the backend may still finish the run in the background */
  onCancel: () => void
  /** which fact to open on (random when left out); only tests set it */
  factStart?: number
}

/** Shown while the agent works, which can take a minute or more: what was asked for, something to read, and a way out. */
export function BuildingScreen({ request, onCancel, factStart }: Props) {
  const names = request.student.programs.map((id) => shortName(PROGRAMS.find((p) => p.id === id)?.name ?? id))
  return (
    <main className="building" aria-busy="true">
      <div className="building-card">
        <PlanAnimation />
        <h2>Building your plan</h2>
        <p className="building-sub" role="status">
          The planning assistant is choosing your courses and checking every prerequisite. This can take a minute or more, so
          keep this page open.
        </p>
        <p className="building-for">
          {names.join(', ')} &middot; starting {request.start_term} &middot; {request.semesters} semesters
        </p>
        <FactSlideshow facts={FACTS} startAt={factStart} />
        <button type="button" className="btn" onClick={onCancel}>
          Cancel
        </button>
      </div>
    </main>
  )
}
