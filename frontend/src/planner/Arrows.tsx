import { useCallback, useLayoutEffect, useState } from 'react'
import type { Plan } from '../types.ts'
import type { PlanIndex } from './graph.ts'

interface Props {
  plan: Plan
  index: PlanIndex
  /** the element that holds the columns; arrows are positioned relative to it */
  container: HTMLElement | null
  cardEls: Map<string, HTMLElement>
  hotEdges: Set<number>
  /** edges whose target has an open broken-prerequisite flag are drawn red and dashed */
  brokenTargets: Set<string>
  /** changes when something moves the cards without changing the plan (completed courses shown or hidden) */
  layoutKey?: unknown
}

interface Path {
  k: number
  d: string
  bad: boolean
}

/** Curved arrows between prerequisite and dependent course, measured from where the cards actually are. */
export function Arrows({ plan, index, container, cardEls, hotEdges, brokenTargets, layoutKey }: Props) {
  const [paths, setPaths] = useState<Path[]>([])
  const [size, setSize] = useState({ w: 0, h: 0 })

  const measure = useCallback(() => {
    if (!container) return
    const box = container.getBoundingClientRect()
    const out: Path[] = []
    plan.prerequisite_edges.forEach((e, k) => {
      const a = cardEls.get(e.from)
      const b = cardEls.get(e.to)
      if (!a || !b) return
      const A = a.getBoundingClientRect()
      const B = b.getBoundingClientRect()
      const sa = index.semesterOf.get(e.from) ?? 0
      const sb = index.semesterOf.get(e.to) ?? 0
      const ay = A.top - box.top + A.height / 2
      const by = B.top - box.top + B.height / 2
      let d: string
      if (sa === sb) {
        // same column: loop out to the right and back
        const x = A.right - box.left
        const bend = 26 + Math.min(40, Math.abs(by - ay) / 6)
        d = `M${x},${ay} C${x + bend},${ay} ${x + bend},${by} ${x + 3},${by}`
      } else if (sa < sb) {
        const x1 = A.right - box.left
        const x2 = B.left - box.left - 2
        const dx = Math.max(24, (x2 - x1) * 0.5)
        d = `M${x1},${ay} C${x1 + dx},${ay} ${x2 - dx},${by} ${x2},${by}`
      } else {
        // a prerequisite placed after its course: draw backwards
        const x1 = A.left - box.left
        const x2 = B.right - box.left + 2
        const dx = Math.max(24, (x1 - x2) * 0.5)
        d = `M${x1},${ay} C${x1 - dx},${ay} ${x2 + dx},${by} ${x2},${by}`
      }
      out.push({ k, d, bad: sa >= sb && brokenTargets.has(e.to) })
    })
    setPaths(out)
    // Sized from the columns, not the container's scroll size: that includes this layer itself, so the board could
    // never shrink again (after completed courses are folded away, it kept their height as empty space).
    let w = 0
    let h = 0
    for (const child of Array.from(container.children)) {
      if (child.tagName.toLowerCase() === 'svg') continue
      const r = child.getBoundingClientRect()
      w = Math.max(w, r.right - box.left)
      h = Math.max(h, r.bottom - box.top)
    }
    setSize({ w: Math.ceil(w), h: Math.ceil(h) })
  }, [plan, index, container, cardEls, brokenTargets])

  useLayoutEffect(() => {
    if (!container) return
    const first = requestAnimationFrame(measure) // after the cards have been laid out
    const onResize = () => measure()
    window.addEventListener('resize', onResize)
    const observer = typeof ResizeObserver === 'function' ? new ResizeObserver(onResize) : null
    observer?.observe(container)
    // web fonts change text height, so measure again when they have loaded
    document.fonts?.ready.then(measure)
    return () => {
      cancelAnimationFrame(first)
      window.removeEventListener('resize', onResize)
      observer?.disconnect()
    }
  }, [measure, container, layoutKey])

  return (
    <svg className="arrows" width={size.w} height={size.h} aria-hidden="true">
      <defs>
        {[
          ['mk', 'var(--arrow)'],
          ['mk-bad', 'var(--err)'],
          ['mk-hot', 'var(--acc-bright)'],
        ].map(([id, fill]) => (
          <marker key={id} id={id} viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto-start-reverse">
            <path d="M0,0L8,4L0,8z" fill={fill} />
          </marker>
        ))}
      </defs>
      {paths.map((p) => {
        const hot = hotEdges.has(p.k)
        const marker = p.bad ? 'mk-bad' : hot ? 'mk-hot' : 'mk'
        return (
          <path
            key={p.k}
            className={`edge${p.bad ? ' bad' : ''}${hot ? ' hot' : ''}`}
            d={p.d}
            markerEnd={`url(#${marker})`}
          />
        )
      })}
    </svg>
  )
}
