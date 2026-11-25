/** A small plan assembling itself: columns are semesters, blocks are courses dropping into place, then it starts over. */
export function PlanAnimation() {
  const columns = [3, 4, 3, 4, 2]
  return (
    <div className="plan-anim" aria-hidden="true">
      {columns.map((blocks, c) => (
        <div className="pa-col" key={c} style={{ ['--c' as string]: c }}>
          {Array.from({ length: blocks }, (_, b) => (
            <i key={b} style={{ ['--b' as string]: b }} />
          ))}
        </div>
      ))}
    </div>
  )
}
