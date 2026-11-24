import { useEffect, useState } from 'react'

const reducedMotion = () => typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches

/** Counts from 0 up to `target` once, easing out. With reduced motion it just returns the target. */
export function useCountUp(target: number, durationMs = 900): number {
  const reduced = reducedMotion()
  const [value, setValue] = useState(0)
  useEffect(() => {
    if (reduced) return
    let frame = 0
    const start = performance.now()
    const step = (now: number) => {
      const k = Math.min(1, (now - start) / durationMs)
      setValue(target * (1 - Math.pow(1 - k, 3)))
      if (k < 1) frame = requestAnimationFrame(step)
    }
    frame = requestAnimationFrame(step)
    return () => cancelAnimationFrame(frame)
  }, [target, durationMs, reduced])
  return reduced ? target : value
}
