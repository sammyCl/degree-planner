// Draws a PdfDocument (pdfContent.ts) with jsPDF. Loaded only when the student asks for the download, so the library
// does not slow down the page. The file is made in the browser; nothing about the plan is sent anywhere to make it.
import { jsPDF } from 'jspdf'
import { autoTable } from 'jspdf-autotable'
import type { PdfDocument, PdfNotes, PdfTable } from './pdfContent.ts'

const MARGIN = 48
const NAVY: [number, number, number] = [11, 38, 84]
const GREY: [number, number, number] = [95, 105, 120]
const RED: [number, number, number] = [165, 30, 30]
const INK: [number, number, number] = [25, 30, 40]

const PLAIN: Record<string, string> = {
  '‘': "'", '’': "'", '“': '"', '”': '"', '–': '-', '—': '-', '•': '-',
  '…': '...', '→': '->', '≤': '<=', '≥': '>=', '−': '-', ' ': ' ',
}

/** The PDF's built-in font only has Latin letters: anything else is written the nearest plain way. */
export function printable(text: string): string {
  return Array.from(text, (ch) => {
    if (PLAIN[ch]) return PLAIN[ch]
    if (ch.charCodeAt(0) <= 0xff) return ch
    const base = ch.normalize('NFKD').replace(/[̀-ͯ]/g, '')
    return Array.from(base).every((c) => c.charCodeAt(0) <= 0xff) ? base : '?'
  }).join('')
}

export function renderPdf(content: PdfDocument): jsPDF {
  const pdf = new jsPDF({ unit: 'pt', format: 'letter' })
  const width = pdf.internal.pageSize.getWidth()
  const bottom = pdf.internal.pageSize.getHeight() - MARGIN
  const usable = width - MARGIN * 2
  let y = MARGIN

  /** Start a new page unless `height` still fits on this one. */
  const room = (height: number) => {
    if (y + height <= bottom) return
    pdf.addPage()
    y = MARGIN
  }

  const write = (text: string, size: number, color = INK, bold = false, indent = 0) => {
    pdf.setFont('helvetica', bold ? 'bold' : 'normal')
    pdf.setFontSize(size)
    pdf.setTextColor(...color)
    for (const line of pdf.splitTextToSize(printable(text), usable - indent) as string[]) {
      room(size * 1.35)
      pdf.setPage(pdf.getNumberOfPages())
      y += size * 1.35
      pdf.text(line, MARGIN + indent, y)
    }
  }

  const section = (title: string) => {
    room(90) // never leave a section title alone at the foot of a page
    y += 14
    write(title, 13, NAVY, true)
    y += 4
  }

  const table = (t: PdfTable) => {
    room(70)
    y += 8
    write(t.heading, 10.5, INK, true)
    autoTable(pdf, {
      startY: y + 5,
      margin: { left: MARGIN, right: MARGIN, top: MARGIN, bottom: MARGIN },
      head: [t.columns.map(printable)],
      body: t.rows.map((r) => r.map(printable)),
      theme: 'grid',
      rowPageBreak: 'avoid',
      styles: { font: 'helvetica', fontSize: 8.5, cellPadding: 3.5, textColor: INK, lineColor: [210, 215, 225], lineWidth: 0.5 },
      headStyles: { fillColor: [235, 239, 246], textColor: NAVY, fontStyle: 'bold' },
      // the same widths in every table, so the columns line up down the page
      columnStyles: Object.fromEntries(
        t.columns.map((name, i) => [
          i,
          name === 'Course' ? { cellWidth: 72 } : name === 'Credits' ? { cellWidth: 42, halign: 'right' as const } : name === 'Status' ? { cellWidth: 56 } : name === 'Counts as' || name === 'From' ? { cellWidth: 104 } : {},
        ]),
      ),
    })
    y = (pdf as jsPDF & { lastAutoTable: { finalY: number } }).lastAutoTable.finalY
  }

  const list = (notes: PdfNotes, color = INK) => {
    room(50)
    y += 8
    write(notes.heading, 10.5, color, true)
    for (const item of notes.items) write(`- ${item}`, 9, INK, false, 8)
  }

  write(content.title, 20, NAVY, true)
  for (const line of content.details) write(line, 10, GREY)
  y += 4
  write(content.credits, 11, INK, true)
  for (const alert of content.alerts) list(alert, RED)

  if (content.completed) {
    section('Already completed')
    table(content.completed)
  }
  section('Semester by semester')
  content.semesters.forEach(table)
  section('Degree requirements')
  content.requirements.forEach(table)
  if (content.notes.length) {
    section('Notes')
    content.notes.forEach((n) => list(n))
  }

  const pages = pdf.getNumberOfPages()
  for (let page = 1; page <= pages; page++) {
    pdf.setPage(page)
    pdf.setFont('helvetica', 'normal')
    pdf.setFontSize(8)
    pdf.setTextColor(...GREY)
    pdf.text(content.footer, MARGIN, bottom + 24)
    pdf.text(`Page ${page} of ${pages}`, width - MARGIN, bottom + 24, { align: 'right' })
  }
  return pdf
}
