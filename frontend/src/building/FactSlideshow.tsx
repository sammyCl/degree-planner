import { useCallback, useEffect, useRef, useState } from 'react'
import { FACT_INTERVAL_MS, type Fact } from './facts.ts'

interface Props {
  facts: Fact[]
  /** how long each fact stays before the next slides in, in milliseconds */
  intervalMs?: number
  /** which fact to start on; a random one by default so a repeat visit does not always open the same way */
  startAt?: number
}

/** After the student moves the slides themselves, wait this long before moving on by itself again. */
export const PAUSE_AFTER_USER_MS = 15000

const reducedMotion = () => typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches

/**
 * A row of facts that slides sideways. It moves on by itself, and the student can scroll or swipe it, or use the arrows
 * and dots, to go back to one; after that it waits a while before moving on by itself.
 */
export function FactSlideshow({ facts, intervalMs = FACT_INTERVAL_MS, startAt }: Props) {
  const [index, setIndex] = useState(() => startAt ?? Math.floor(Math.random() * facts.length))
  const track = useRef<HTMLDivElement>(null)
  const pausedUntil = useRef(0)
  const scrolling = useRef(false) // true while the page itself is scrolling the track

  const scrollToIndex = useCallback((i: number, smooth: boolean) => {
    const el = track.current
    if (!el) return
    scrolling.current = true
    el.scrollTo?.({ left: i * el.clientWidth, behavior: smooth && !reducedMotion() ? 'smooth' : 'auto' })
    setTimeout(() => (scrolling.current = false), 700)
  }, [])

  const go = useCallback(
    (i: number, byUser: boolean) => {
      const next = (i + facts.length) % facts.length
      if (byUser) pausedUntil.current = Date.now() + PAUSE_AFTER_USER_MS
      setIndex(next)
      scrollToIndex(next, true)
    },
    [facts.length, scrollToIndex],
  )

  // open on the starting fact without an animation
  useEffect(() => {
    scrollToIndex(index, false)
    // only on the first render
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    if (facts.length < 2) return
    const id = setInterval(() => {
      if (Date.now() < pausedUntil.current) return
      setIndex((i) => {
        const next = (i + 1) % facts.length
        scrollToIndex(next, true)
        return next
      })
    }, intervalMs)
    return () => clearInterval(id)
  }, [facts.length, intervalMs, scrollToIndex])

  /** The student scrolled or swiped the track: follow them, and stop moving on by ourselves for a while. */
  const onScroll = () => {
    const el = track.current
    if (!el || scrolling.current || el.clientWidth === 0) return
    pausedUntil.current = Date.now() + PAUSE_AFTER_USER_MS
    setIndex(Math.round(el.scrollLeft / el.clientWidth))
  }

  return (
    <div className="facts" aria-roledescription="carousel" aria-label="Facts about Mines degrees">
      <div className="facts-row">
        <button type="button" className="facts-arrow" aria-label="Previous fact" onClick={() => go(index - 1, true)}>
          &#8249;
        </button>
        <div className="facts-track" ref={track} onScroll={onScroll} tabIndex={0}>
          {facts.map((f, i) => (
            <figure
              key={f.topic}
              className={i === index ? 'fact-slide on' : 'fact-slide'}
              aria-roledescription="slide"
              aria-label={`${i + 1} of ${facts.length}`}
              aria-hidden={i !== index}
            >
              <figcaption>{f.topic}</figcaption>
              <p>{f.text}</p>
            </figure>
          ))}
        </div>
        <button type="button" className="facts-arrow" aria-label="Next fact" onClick={() => go(index + 1, true)}>
          &#8250;
        </button>
      </div>
      <div className="facts-dots">
        {facts.map((f, i) => (
          <button
            key={f.topic}
            type="button"
            className={i === index ? 'on' : ''}
            aria-label={`Show fact ${i + 1}: ${f.topic}`}
            aria-current={i === index}
            onClick={() => go(i, true)}
          />
        ))}
      </div>
    </div>
  )
}
