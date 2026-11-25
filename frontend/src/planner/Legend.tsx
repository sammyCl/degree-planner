import { useEffect, useRef, useState } from 'react'

const LABELS: { cat: string; tag: string; text: string }[] = [
  { cat: 'core', tag: 'Core', text: 'Required for your degree (also when a minor uses it too)' },
  { cat: 'elective', tag: 'Elective', text: 'An elective of your major: tech, focus area, track' },
  { cat: 'free', tag: 'Free elective', text: 'Any course you like' },
  { cat: 'cas', tag: 'CAS / S&W', text: 'Culture & Society, Success & Wellness' },
  { cat: 'minor', tag: 'Minor core', text: 'Counts only for a minor (or ASI); Minor elective works the same way' },
  { cat: 'extra', tag: 'Extra', text: 'Counts toward no requirement' },
]

const SUBJECTS: { name: string; color: string }[] = [
  { name: 'CSCI', color: 'var(--sub-csci)' },
  { name: 'MATH', color: 'var(--sub-math)' },
  { name: 'PHGN', color: 'var(--sub-phgn)' },
  { name: 'CHGN', color: 'var(--sub-chgn)' },
  { name: 'other', color: 'var(--sub-other)' },
]

/** A small "Key" button that opens a short guide to the card labels, dot colours and warnings. Closed by default. */
export function Legend() {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!open) return
    const onDown = (e: MouseEvent) => !ref.current?.contains(e.target as Node) && setOpen(false)
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && setOpen(false)
    document.addEventListener('mousedown', onDown)
    document.addEventListener('keydown', onKey)
    return () => {
      document.removeEventListener('mousedown', onDown)
      document.removeEventListener('keydown', onKey)
    }
  }, [open])

  return (
    <div className="key-wrap" ref={ref}>
      <button type="button" className="key-btn" aria-expanded={open} aria-haspopup="dialog" onClick={() => setOpen((o) => !o)}>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <circle cx="12" cy="12" r="9" />
          <path d="M12 11v5m0-8h.01" />
        </svg>
        Key
      </button>
      {open && (
        <div className="key-pop" role="dialog" aria-label="Colour and label key">
          <div className="key-sec">Label on a card</div>
          {LABELS.map((l) => (
            <div className="key-row" key={l.tag}>
              <span className={`card-tag cat-${l.cat}`}>{l.tag}</span>
              <span>{l.text}</span>
            </div>
          ))}
          <div className="key-sec">Dot colour is the subject</div>
          <div className="key-dots">
            {SUBJECTS.map((s) => (
              <span key={s.name}>
                <i style={{ background: s.color }} /> {s.name}
              </span>
            ))}
          </div>
          <div className="key-sec">Card outline</div>
          <div className="key-row">
            <i className="key-swatch err" />
            <span>Red: needs attention, such as a prerequisite out of order</span>
          </div>
          <div className="key-row">
            <i className="key-swatch warn" />
            <span>Amber: check this</span>
          </div>
          <div className="key-row">
            <i className="key-swatch dashed" />
            <span>Dashed strip under a course: its lab, taken with it. They move as one.</span>
          </div>
          <div className="key-sec">Semester bar</div>
          <div className="key-row">
            <i className="key-swatch low" />
            <span>Amber: under 12 credits (not counted for Summer)</span>
          </div>
          <div className="key-row">
            <i className="key-swatch high" />
            <span>Red: over 19 credits</span>
          </div>
        </div>
      )}
    </div>
  )
}
