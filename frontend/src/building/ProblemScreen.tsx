import './BuildingScreen.css'

interface Props {
  title: string
  message: string
  /** reasons the assistant gave, when it could not build a plan */
  problems?: string[]
  onRetry?: () => void
  onBack: () => void
}

/** Shown when no plan came back: the backend or agent was unavailable, the request was rejected, or no plan was possible. */
export function ProblemScreen({ title, message, problems = [], onRetry, onBack }: Props) {
  return (
    <main className="building">
      <div className="building-card problem" role="alert">
        <div className="problem-icon" aria-hidden="true">
          <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M12 3l10 18H2z" />
            <path d="M12 10v4m0 3h.01" />
          </svg>
        </div>
        <h2>{title}</h2>
        <p className="building-sub">{message}</p>
        {problems.length > 0 && (
          <ul className="problem-list">
            {problems.map((p, i) => (
              <li key={i}>{p}</li>
            ))}
          </ul>
        )}
        <div className="problem-actions">
          {onRetry && (
            <button type="button" className="btn primary" onClick={onRetry}>
              Try again
            </button>
          )}
          <button type="button" className="btn" onClick={onBack}>
            Back to setup
          </button>
        </div>
      </div>
    </main>
  )
}
