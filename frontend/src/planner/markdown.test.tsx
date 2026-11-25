import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { Markdown } from './markdown.tsx'
import { parseBlocks } from './parseMarkdown.ts'

describe('parseBlocks', () => {
  it('splits paragraphs on blank lines and joins wrapped lines', () => {
    expect(parseBlocks('One line\nstill one.\n\nSecond.')).toEqual([
      { type: 'p', text: 'One line still one.' },
      { type: 'p', text: 'Second.' },
    ])
  })

  it('reads bullet lists, even right after a paragraph with no blank line', () => {
    expect(parseBlocks('**Exceptions.** Decide each.\n- **MATH111** needs a note\n- CSCI478 too\n  and more\n\nDone.')).toEqual([
      { type: 'p', text: '**Exceptions.** Decide each.' },
      { type: 'ul', items: ['**MATH111** needs a note', 'CSCI478 too and more'] },
      { type: 'p', text: 'Done.' },
    ])
  })

  it('returns nothing for empty text', () => {
    expect(parseBlocks('  \n\n')).toEqual([])
  })
})

describe('Markdown', () => {
  it('renders bold and code as elements, not as raw markers', () => {
    render(<Markdown source={'The plan has **130 credits** and `requirements_met`.\n- first\n- second'} />)
    expect(screen.getByText('130 credits').tagName).toBe('STRONG')
    expect(screen.getByText('requirements_met').tagName).toBe('CODE')
    expect(screen.getAllByRole('listitem')).toHaveLength(2)
    expect(screen.queryByText(/\*\*/)).not.toBeInTheDocument()
  })

  it('never turns text into HTML', () => {
    const { container } = render(<Markdown source={'<img src=x onerror=alert(1)> and <b>bold</b>'} />)
    expect(container.querySelector('img')).toBeNull()
    expect(container.querySelector('b')).toBeNull()
    expect(container).toHaveTextContent('<img src=x onerror=alert(1)> and <b>bold</b>')
  })
})
