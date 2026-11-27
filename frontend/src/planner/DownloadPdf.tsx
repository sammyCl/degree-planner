import { useState } from 'react'
import { buildPdfDocument, type PdfInput } from './pdfContent.ts'

interface Props extends PdfInput {
  /** the plan on screen is still being checked, so it cannot be downloaded yet */
  waiting?: boolean
}

/** "Download PDF": the plan as it stands on screen, as a file the student can keep or send to an advisor. */
export function DownloadPdf({ waiting, ...input }: Props) {
  const [busy, setBusy] = useState(false)
  const [failed, setFailed] = useState(false)

  const download = async () => {
    const content = buildPdfDocument(input) // taken now, so a change made while the library loads is not mixed in
    setBusy(true)
    setFailed(false)
    try {
      const { renderPdf } = await import('./pdfFile.ts')
      renderPdf(content).save(content.fileName)
    } catch {
      setFailed(true)
    } finally {
      setBusy(false)
    }
  }

  return (
    <span className="download">
      {failed && (
        <span className="download-error" role="alert">
          The PDF could not be made. Try again.
        </span>
      )}
      <button type="button" className="download-pdf" onClick={download} disabled={busy || waiting}>
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M12 4v11M7 11l5 5 5-5M5 20h14" />
        </svg>
        {busy ? 'Making PDF...' : 'Download PDF'}
      </button>
    </span>
  )
}
