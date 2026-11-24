import type { ReactNode } from 'react'
import { parseBlocks } from './parseMarkdown.ts'

// Renders the blocks from parseMarkdown.ts.
// The assistant writes its explanation with a little markdown (**bold**, `code`, "- " bullets). This renders just that,
// as React elements, never as HTML, so nothing the model writes can inject markup.

function renderInline(text: string): ReactNode[] {
  return text.split(/(\*\*[^*]+\*\*|`[^`]+`)/).map((part, i) => {
    if (part.startsWith('**') && part.endsWith('**') && part.length > 4) return <strong key={i}>{part.slice(2, -2)}</strong>
    if (part.startsWith('`') && part.endsWith('`') && part.length > 2) return <code key={i}>{part.slice(1, -1)}</code>
    return part
  })
}

export function Markdown({ source }: { source: string }) {
  return (
    <>
      {parseBlocks(source).map((b, i) =>
        b.type === 'p' ? (
          <p key={i}>{renderInline(b.text)}</p>
        ) : (
          <ul key={i}>
            {b.items.map((item, j) => (
              <li key={j}>{renderInline(item)}</li>
            ))}
          </ul>
        ),
      )}
    </>
  )
}
