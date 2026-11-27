import { useState } from 'react'
import { buildPdfDocument, type PdfInput } from './pdfContent.ts'

interface Props extends PdfInput {
  /** the element that holds the flowchart */
  board: HTMLElement | null
  /** the plan on screen is still being checked, so it cannot be downloaded yet */
  waiting?: boolean
}

type Kind = 'pdf' | 'image'

const NAMES: Record<Kind, { button: string; busy: string; failed: string }> = {
  image: { button: 'Download flowchart', busy: 'Making image...', failed: 'The image could not be made. Try again.' },
  pdf: { button: 'Download PDF', busy: 'Making PDF...', failed: 'The PDF could not be made. Try again.' },
}

/** The plan as it stands on screen, as files the student can keep or send: a PDF, or a picture of the flowchart. */
export function Downloads({ board, waiting, ...input }: Props) {
  const [busy, setBusy] = useState<Kind | null>(null)
  const [failed, setFailed] = useState<Kind | null>(null)

  const download = async (kind: Kind) => {
    const content = buildPdfDocument(input) // taken now, so a change made while the library loads is not mixed in
    setBusy(kind)
    setFailed(null)
    try {
      if (kind === 'pdf') {
        const { renderPdf } = await import('./pdfFile.ts')
        renderPdf(content).save(content.fileName)
      } else {
        if (!board) throw new Error('No flowchart to draw')
        const { makeBoardImage, saveFile } = await import('./boardImage.ts')
        saveFile(await makeBoardImage(board, content), content.fileName.replace(/\.pdf$/, '.png'))
      }
    } catch {
      setFailed(kind)
    } finally {
      setBusy(null)
    }
  }

  return (
    <span className="download">
      {failed && (
        <span className="download-error" role="alert">
          {NAMES[failed].failed}
        </span>
      )}
      {(['image', 'pdf'] as const).map((kind) => (
        <button key={kind} type="button" className="download-btn" onClick={() => download(kind)} disabled={busy !== null || waiting}>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M12 4v11M7 11l5 5 5-5M5 20h14" />
          </svg>
          {busy === kind ? NAMES[kind].busy : NAMES[kind].button}
        </button>
      ))}
    </span>
  )
}
