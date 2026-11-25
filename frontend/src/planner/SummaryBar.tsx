import { useEffect, useRef, useState } from 'react'
import type { Flag, Plan } from '../types.ts'
import { flagCounts, flagKind } from './graph.ts'
import { useCountUp } from './useCountUp.ts'

const R = 19
const CIRCUMFERENCE = 2 * Math.PI * R

const WarnIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M12 3l10 18H2z" />
    <path d="M12 10v4m0 3h.01" />
  </svg>
)
const InfoIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <circle cx="12" cy="12" r="9" />
    <path d="M12 8v5m0 3h.01" />
  </svg>
)
const CheckIcon = () => (
  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M5 12l5 5L20 7" />
  </svg>
)

const MENU_NAMES = { error: 'Errors', warning: 'Warnings', confirm: 'To confirm' } as const
type FlagKind = keyof typeof MENU_NAMES

interface Props {
  plan: Plan
  programName: string
  onSelectFlag: (flag: Flag) => void
  /** true while the backend re-checks the plan after the student changed it */
  checking?: boolean
}

export function SummaryBar({ plan, programName, onSelectFlag, checking }: Props) {
  const { total_credits: total, total_credits_required: required } = plan.summary
  const { errors, warnings, confirm } = flagCounts(plan.flags)
  const shown = useCountUp(total)
  const [ready, setReady] = useState(false)
  // which list is open: only the flags of the badge that was clicked
  const [menu, setMenu] = useState<FlagKind | null>(null)
  const menuRef = useRef<HTMLDivElement>(null)

  // Start the ring empty, then let CSS animate it to the real value.
  useEffect(() => {
    const frame = requestAnimationFrame(() => setReady(true))
    return () => cancelAnimationFrame(frame)
  }, [])

  useEffect(() => {
    if (!menu) return
    const onDown = (e: MouseEvent) => !menuRef.current?.contains(e.target as Node) && setMenu(null)
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setMenu(null)
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [menu])

  const toggle = (kind: FlagKind) => setMenu((m) => (m === kind ? null : kind))
  const listed = menu ? plan.flags.filter((f) => flagKind(f) === menu) : []
  const progress = required > 0 ? Math.min(1, total / required) : 0
  return (
    <div className="bar">
      <div className="prog" title="Credits planned plus completed, out of the degree total">
        <svg className="ring" viewBox="0 0 46 46" aria-hidden="true">
          <circle className="ring-bg" cx="23" cy="23" r={R} />
          <circle
            className="ring-fg"
            cx="23"
            cy="23"
            r={R}
            strokeDasharray={CIRCUMFERENCE}
            strokeDashoffset={ready ? CIRCUMFERENCE * (1 - progress) : CIRCUMFERENCE}
          />
        </svg>
        <div>
          <div className="prog-credits" data-testid="credit-total">
            {Math.round(shown)} / {required}
          </div>
          <div className="prog-sub">credits</div>
        </div>
      </div>
      <span className="sep" />
      <div className="prog-title">
        <b>{programName}</b>
        <span>Catalog {plan.student.catalog_year}</span>
      </div>
      <span className="sep" />
      <div className="flags-dd" ref={menuRef}>
        <button
          type="button"
          className={errors ? 'badge e' : 'badge ok'}
          aria-expanded={menu === 'error'}
          aria-haspopup="true"
          onClick={() => toggle('error')}
        >
          {errors ? <WarnIcon /> : <CheckIcon />}
          {errors ? `${errors} error${errors === 1 ? '' : 's'}` : 'No errors'}
        </button>
        {warnings > 0 && (
          <button type="button" className="badge w" aria-expanded={menu === 'warning'} aria-haspopup="true" onClick={() => toggle('warning')}>
            <InfoIcon />
            {warnings} warning{warnings === 1 ? '' : 's'}
          </button>
        )}
        {confirm > 0 && (
          <button type="button" className="badge c" aria-expanded={menu === 'confirm'} aria-haspopup="true" onClick={() => toggle('confirm')}>
            <InfoIcon />
            {confirm} to confirm
          </button>
        )}
        {menu && (
          <div className="flags-menu" role="menu" aria-label={MENU_NAMES[menu]}>
            {listed.length === 0 && <div className="flags-none">{menu === 'error' ? 'No errors.' : 'Nothing here.'}</div>}
            {listed.map((f) => (
              <button
                key={f.flag_id}
                type="button"
                role="menuitem"
                className={`flag ${{ error: 'e', warning: 'w', confirm: 'c' }[flagKind(f)]}${f.overridden ? ' done' : ''}`}
                onClick={() => {
                  setMenu(null)
                  onSelectFlag(f)
                }}
              >
                <span className="flag-ic">{flagKind(f) === 'error' ? <WarnIcon /> : <InfoIcon />}</span>
                <span>
                  <b>{flagTitle(f)}</b>
                  <span>{f.message}</span>
                </span>
              </button>
            ))}
          </div>
        )}
      </div>
      {checking && (
        <span className="checking" role="status">
          <i aria-hidden="true" />
          Checking your change...
        </span>
      )}
      <span className="grow" />
      <div className="legend" aria-hidden="true">
        <span>
          <i /> prerequisite
        </span>
        <span>
          <i className="bad" /> out of order
        </span>
      </div>
    </div>
  )
}

const TITLES: Record<string, string> = {
  broken_prerequisite: 'Prerequisite out of order',
  credit_shortfall: 'Credit load',
  requirement_unmet: 'Requirement not met',
  double_count_exceeded: 'Too many shared courses',
  exception_claimed: 'To confirm',
}
const flagTitle = (f: Flag): string => TITLES[f.type] ?? 'Needs attention'
