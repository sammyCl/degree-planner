import { useId, useMemo, useState } from 'react'
import { shortName, type ProgramOption } from './validate.ts'

interface Props {
  options: ProgramOption[]
  selected: string[]
  onChange: (ids: string[]) => void
}

/** Search box with chips: pick any number of minors and ASIs. */
export function AddOnPicker({ options, selected, onChange }: Props) {
  const listId = useId()
  const [query, setQuery] = useState('')
  const [open, setOpen] = useState(false)
  const [highlight, setHighlight] = useState(0)

  const byId = useMemo(() => new Map(options.map((o) => [o.id, o])), [options])
  const hits = useMemo(() => {
    const q = query.trim().toLowerCase()
    return options
      .filter((o) => !selected.includes(o.id) && (!q || shortName(o.name).toLowerCase().includes(q)))
      .slice(0, 8)
  }, [options, selected, query])

  const active = Math.min(highlight, Math.max(0, hits.length - 1))
  const add = (id: string) => {
    onChange([...selected, id])
    setQuery('')
    setHighlight(0)
    setOpen(true)
  }
  const remove = (id: string) => onChange(selected.filter((x) => x !== id))

  const onKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setOpen(true)
      setHighlight(Math.min(active + 1, hits.length - 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setHighlight(Math.max(active - 1, 0))
    } else if (e.key === 'Enter') {
      e.preventDefault()
      if (open && hits[active]) add(hits[active].id)
    } else if (e.key === 'Escape') {
      setOpen(false)
    } else if (e.key === 'Backspace' && !query && selected.length) {
      remove(selected[selected.length - 1])
    }
  }

  return (
    <div className="combo">
      <div className="chips">
        {selected.map((id) => {
          const o = byId.get(id)
          const name = o ? shortName(o.name) : id
          return (
            <span className="chip" key={id}>
              {name}
              <button type="button" aria-label={`Remove ${name}`} onClick={() => remove(id)}>
                &times;
              </button>
            </span>
          )
        })}
        <input
          role="combobox"
          aria-label="Search minors and ASIs"
          aria-expanded={open}
          aria-controls={listId}
          aria-autocomplete="list"
          aria-activedescendant={open && hits[active] ? `${listId}-${hits[active].id}` : undefined}
          placeholder={selected.length ? '' : 'Search minors and ASIs...'}
          autoComplete="off"
          value={query}
          onChange={(e) => {
            setQuery(e.target.value)
            setHighlight(0)
            setOpen(true)
          }}
          onFocus={() => setOpen(true)}
          onBlur={() => setOpen(false)}
          onKeyDown={onKeyDown}
        />
      </div>
      {open && (
        <div className="menu" id={listId} role="listbox" aria-label="Minors and ASIs">
          {hits.length === 0 && <div className="menu-empty">No matching minor or ASI</div>}
          {hits.map((o, i) => (
            <div
              key={o.id}
              id={`${listId}-${o.id}`}
              role="option"
              aria-selected={i === active}
              className={i === active ? 'menu-item hl' : 'menu-item'}
              onMouseDown={(e) => {
                e.preventDefault() // keep focus in the input so the menu does not close first
                add(o.id)
              }}
              onMouseEnter={() => setHighlight(i)}
            >
              {shortName(o.name)}
              <span className="menu-kind">{o.level === 'asi' ? 'ASI' : 'minor'}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
