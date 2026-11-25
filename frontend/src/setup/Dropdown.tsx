import { useId, useMemo, useRef, useState } from 'react'

export interface DropdownOption {
  value: string
  label: string
}

interface Props {
  options: DropdownOption[]
  value: string
  onChange: (value: string) => void
  /** Accessible name when there is no visible <label htmlFor={id}>. */
  label?: string
  id?: string
  placeholder?: string
  /** Typing filters the list (used for the long program lists). */
  searchable?: boolean
  invalid?: boolean
  describedBy?: string
  ref?: React.Ref<HTMLInputElement>
}

/** A custom dropdown with the same look as the minors/ASIs picker: boxed field, solid menu, keyboard support. */
export function Dropdown({ options, value, onChange, label, id, placeholder, searchable, invalid, describedBy, ref }: Props) {
  const listId = useId()
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [highlight, setHighlight] = useState(0)
  const input = useRef<HTMLInputElement | null>(null)
  // the field is ours and the caller's (for focusing it on an error), so both refs get it
  const setInput = (el: HTMLInputElement | null) => {
    input.current = el
    if (typeof ref === 'function') ref(el)
    else if (ref) (ref as React.MutableRefObject<HTMLInputElement | null>).current = el
  }

  const selected = options.find((o) => o.value === value)
  const shown = useMemo(() => {
    const q = query.trim().toLowerCase()
    return searchable && q ? options.filter((o) => o.label.toLowerCase().includes(q)) : options
  }, [options, query, searchable])
  const active = Math.min(highlight, Math.max(0, shown.length - 1))

  const openMenu = () => {
    if (!open) setHighlight(Math.max(0, shown.findIndex((o) => o.value === value)))
    setOpen(true)
  }
  const close = () => {
    setOpen(false)
    setQuery('')
  }
  const choose = (o: DropdownOption) => {
    onChange(o.value)
    close()
  }
  const move = (to: number) => {
    const next = Math.min(Math.max(to, 0), shown.length - 1)
    setHighlight(next)
    document.getElementById(`${listId}-${next}`)?.scrollIntoView?.({ block: 'nearest' })
  }

  const onKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      if (!open) openMenu()
      else move(active + 1)
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      if (!open) openMenu()
      else move(active - 1)
    } else if (e.key === 'Enter') {
      if (open) {
        e.preventDefault() // do not submit the form while choosing
        if (shown[active]) choose(shown[active])
      }
    } else if (e.key === ' ' && !searchable) {
      e.preventDefault()
      if (open && shown[active]) choose(shown[active])
      else openMenu()
    } else if (e.key === 'Escape') {
      close()
    } else if (e.key === 'Tab') {
      close()
    }
  }

  return (
    <div className="dd">
      <div
        className={invalid ? 'dd-box invalid' : 'dd-box'}
        onMouseDown={(e) => {
          // a press on the arrow or the padding (not the text field itself) opens and closes it too
          if (e.target === input.current) return
          e.preventDefault()
          input.current?.focus()
          if (open) close()
          else openMenu()
        }}
      >
        <input
          ref={setInput}
          id={id}
          role="combobox"
          aria-label={label}
          aria-expanded={open}
          aria-controls={listId}
          aria-autocomplete={searchable ? 'list' : 'none'}
          aria-activedescendant={open && shown[active] ? `${listId}-${active}` : undefined}
          aria-invalid={invalid || undefined}
          aria-describedby={describedBy}
          autoComplete="off"
          readOnly={!searchable}
          placeholder={placeholder}
          value={open && searchable ? query : (selected?.label ?? '')}
          onChange={(e) => {
            setQuery(e.target.value)
            setHighlight(0)
            setOpen(true)
          }}
          onClick={() => (open && !searchable ? close() : openMenu())}
          onBlur={close}
          onKeyDown={onKeyDown}
        />
        <span className="dd-chevron" aria-hidden="true" />
      </div>
      {open && (
        <div className="menu" id={listId} role="listbox" aria-label={label}>
          {shown.length === 0 && <div className="menu-empty">No matches</div>}
          {shown.map((o, i) => (
            <div
              key={o.value}
              id={`${listId}-${i}`}
              role="option"
              aria-selected={o.value === value}
              className={`menu-item${i === active ? ' hl' : ''}${o.value === value ? ' sel' : ''}`}
              onMouseDown={(e) => {
                e.preventDefault() // keep focus in the field so the menu does not close before the choice lands
                choose(o)
              }}
              onMouseEnter={() => setHighlight(i)}
            >
              {o.label}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
