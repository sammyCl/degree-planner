// Splits the assistant's small markdown (paragraphs and "- " bullets) into blocks. Pure, so it is easy to test.

export type Block = { type: 'p'; text: string } | { type: 'ul'; items: string[] }

const BULLET = /^\s*[-*]\s+(.*)$/

export function parseBlocks(source: string): Block[] {
  const blocks: Block[] = []
  let paragraph: string[] = []
  let list: string[] | null = null
  const endParagraph = () => {
    if (paragraph.length) blocks.push({ type: 'p', text: paragraph.join(' ') })
    paragraph = []
  }
  const endList = () => {
    if (list) blocks.push({ type: 'ul', items: list })
    list = null
  }
  for (const raw of source.split('\n')) {
    const line = raw.trim()
    const bullet = BULLET.exec(raw)
    if (bullet) {
      endParagraph()
      list = [...(list ?? []), bullet[1].trim()]
    } else if (line === '') {
      endParagraph()
      endList()
    } else if (list) {
      list[list.length - 1] += ` ${line}` // a wrapped bullet continues the previous item
    } else {
      paragraph.push(line)
    }
  }
  endParagraph()
  endList()
  return blocks
}
