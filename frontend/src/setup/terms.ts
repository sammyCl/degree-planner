// Semester labels, ported from the backend's semester_labels() (agent/request_models.py) so the setup page
// can show the same terms the agent will plan into. Keep the two in step.

export type Season = 'Fall' | 'Spring' | 'Summer'
export const SEASONS: Season[] = ['Fall', 'Spring', 'Summer']

export function startTerm(season: Season, year: number): string {
  return `${season} ${year}`
}

export function semesterLabels(season: Season, year: number, count: number, includeSummers: boolean): string[] {
  const labels: string[] = []
  let s = season
  let y = year
  for (let i = 0; i < count; i++) {
    labels.push(`${s} ${y}`)
    if (s === 'Fall') {
      s = 'Spring'
      y += 1
    } else if (s === 'Spring' && includeSummers) {
      s = 'Summer'
    } else {
      s = 'Fall' // Spring without summers, or Summer: Fall of the same year (a Summer start is always kept)
    }
  }
  return labels
}

/** The next Fall or Spring after `today`: Sep to Dec starts next Spring, Jan to Aug starts that Fall. */
export function defaultStart(today: Date = new Date()): { season: Season; year: number } {
  const month = today.getMonth() + 1
  const year = today.getFullYear()
  return month >= 9 ? { season: 'Spring', year: year + 1 } : { season: 'Fall', year }
}
