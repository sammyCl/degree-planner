import { useEffect, useState } from 'react'
import { FACT_INTERVAL_MS, type Fact } from './facts.ts'

interface Props {
  facts: Fact[]
  /** how long each fact stays, in milliseconds */
  intervalMs?: number
  /** which fact to start on; a random one by default so a repeat visit does not always open the same way */
  startAt?: number
}

/** One fact at a time that cross-fades to the next. All facts sit in the same spot, so the box never jumps in size. */
export function FactSlideshow({ facts, intervalMs = FACT_INTERVAL_MS, startAt }: Props) {
  const [index, setIndex] = useState(() => startAt ?? Math.floor(Math.random() * facts.length))
  useEffect(() => {
    if (facts.length < 2) return
    const id = setInterval(() => setIndex((i) => (i + 1) % facts.length), intervalMs)
    return () => clearInterval(id)
  }, [facts.length, intervalMs])

  return (
    <div className="facts">
      <div className="facts-stage">
        {facts.map((f, i) => (
          <figure key={f.topic} className={i === index ? 'fact on' : 'fact'} aria-hidden={i !== index}>
            <figcaption>{f.topic}</figcaption>
            <p>{f.text}</p>
          </figure>
        ))}
      </div>
      <div className="facts-dots" aria-hidden="true">
        {facts.map((f, i) => (
          <i key={f.topic} className={i === index ? 'on' : ''} />
        ))}
      </div>
    </div>
  )
}
