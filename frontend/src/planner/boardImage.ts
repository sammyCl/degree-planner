// The flowchart as a picture: the board exactly as it is on screen (all semesters, also those scrolled out of view,
// with their arrows), under a short heading. Made in the browser and loaded only when asked for.
import { toCanvas } from 'html-to-image'
import type { PdfDocument } from './pdfContent.ts'

const PAD = 28
/** room on the right for an arrow that loops out of the last column */
const LOOP = 44
/** the widest and largest picture every browser can still make */
const MAX_SIDE = 16000
const MAX_AREA = 60_000_000

/** Buttons that only make sense on the live page. */
const CONTROLS = ['add-between', 'add-end', 'sem-remove']

export const isPartOfPicture = (node: Node): boolean =>
  !(node instanceof Element && CONTROLS.some((name) => node.classList.contains(name)))

/** Twice the screen size so small text stays sharp, less for a plan too long for that. */
export const sharpness = (width: number, height: number): number =>
  Math.min(2, MAX_SIDE / Math.max(width, height), Math.sqrt(MAX_AREA / (width * height)))

/** How much of the board the columns fill (the add buttons at the end are not part of the picture). */
function boardSize(board: HTMLElement): { width: number; height: number } {
  const box = board.getBoundingClientRect()
  let width = 0
  let height = 0
  for (const child of Array.from(board.children)) {
    if (child.tagName.toLowerCase() === 'svg' || !isPartOfPicture(child)) continue
    const r = child.getBoundingClientRect()
    width = Math.max(width, r.right - box.left)
    height = Math.max(height, r.bottom - box.top)
  }
  return { width: Math.ceil(width) + LOOP, height: Math.ceil(height) + 8 }
}

export interface Heading {
  text: string
  size: number
  bold?: boolean
  tone: 'ink' | 'muted' | 'error'
}

/** The lines above the flowchart, so a picture sent on its own still says whose plan it is and what is wrong with it. */
export function headingLines(content: PdfDocument): Heading[] {
  const [first, ...rest] = content.details
  return [
    { text: first ?? content.title, size: 20, bold: true, tone: 'ink' },
    ...rest.map((text): Heading => ({ text, size: 13, tone: 'muted' })),
    { text: content.credits, size: 14, bold: true, tone: 'ink' },
    ...content.alerts.map((a): Heading => ({ text: a.heading, size: 14, bold: true, tone: 'error' })),
  ]
}

const LINE_STYLES = ['fill', 'stroke', 'stroke-width', 'stroke-dasharray', 'stroke-linecap', 'opacity']

/**
 * The copy loses the stylesheet's rules for the arrows (they would be filled in solid black), so each line and arrow
 * head carries its own style while the picture is taken. Returns what puts the page back.
 */
export function fixArrowStyles(board: HTMLElement): () => void {
  const shapes = Array.from(board.querySelectorAll<SVGElement>('svg.arrows path'))
  const before = shapes.map((shape) => shape.getAttribute('style'))
  const wanted = shapes.map((shape) => {
    const styles = getComputedStyle(shape)
    return LINE_STYLES.map((name) => [name, styles.getPropertyValue(name)] as const).filter(([, value]) => value)
  })
  shapes.forEach((shape, i) => wanted[i].forEach(([name, value]) => shape.style.setProperty(name, value)))
  return () =>
    shapes.forEach((shape, i) => {
      const style = before[i]
      if (style === null) shape.removeAttribute('style')
      else shape.setAttribute('style', style)
    })
}

export async function makeBoardImage(board: HTMLElement, content: PdfDocument): Promise<Blob> {
  // the cards slide in when the page opens: switch that off, or the copy is taken before they appear
  board.classList.add('exporting')
  let restore = () => {}
  try {
    restore = fixArrowStyles(board)
    const { width, height } = boardSize(board)
    const lines = headingLines(content)
    const top = PAD + lines.reduce((sum, l) => sum + l.size * 1.5, 0) + 16
    const fullWidth = Math.max(width + PAD * 2, 760)
    const fullHeight = top + height + 52
    const ratio = sharpness(fullWidth, fullHeight)
    const chart = await toCanvas(board, {
      width,
      height,
      pixelRatio: ratio,
      filter: isPartOfPicture,
      style: { margin: '0' },
    })

    const picture = document.createElement('canvas')
    picture.width = Math.round(fullWidth * ratio)
    picture.height = Math.round(fullHeight * ratio)
    const g = picture.getContext('2d')
    if (!g) throw new Error('This browser cannot draw the picture')
    g.scale(ratio, ratio)

    const styles = getComputedStyle(board)
    const color = (name: string, fallback: string) => styles.getPropertyValue(name).trim() || fallback
    const tones = { ink: styles.color || '#191e28', muted: color('--mut', '#5f6978'), error: color('--err', '#a51e1e') }
    g.fillStyle = color('--bg', '#ffffff')
    g.fillRect(0, 0, fullWidth, fullHeight)
    g.textBaseline = 'top'
    const write = (line: Heading, y: number) => {
      g.font = `${line.bold ? 600 : 400} ${line.size}px Inter, system-ui, sans-serif`
      g.fillStyle = tones[line.tone]
      g.fillText(line.text, PAD, y)
    }
    let y = PAD
    for (const line of lines) {
      write(line, y)
      y += line.size * 1.5
    }
    g.drawImage(chart, PAD, top, width, height)
    write({ text: content.footer, size: 12, tone: 'muted' }, top + height + 18)

    return await new Promise<Blob>((resolve, reject) =>
      picture.toBlob((blob) => (blob ? resolve(blob) : reject(new Error('The picture is empty'))), 'image/png'),
    )
  } finally {
    restore()
    board.classList.remove('exporting')
  }
}

export function saveFile(blob: Blob, fileName: string): void {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = fileName
  link.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
