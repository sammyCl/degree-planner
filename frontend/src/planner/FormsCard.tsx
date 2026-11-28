import { useState } from 'react'
import type { Plan } from '../types.ts'
import { formsFor, type Form } from './forms.ts'

function FormItem({ form, because }: { form: Form; because?: string }) {
  const [open, setOpen] = useState(!!because) // a form the plan calls for is shown in full
  return (
    <li className={because ? 'form-item needed' : 'form-item'}>
      <button type="button" className="form-name" aria-expanded={open} onClick={() => setOpen((o) => !o)}>
        {form.name}
        <svg className={open ? 'chev open' : 'chev'} width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M9 6l6 6-6 6" />
        </svg>
      </button>
      <p className="form-why">{because ?? form.when}</p>
      {open && (
        <p className="form-todo">
          {form.todo}{' '}
          {form.url && (
            <a href={form.url} target="_blank" rel="noreferrer noopener">
              Registrar forms page<span className="sr-only"> for the {form.name} (opens in a new tab)</span>
            </a>
          )}
        </p>
      )}
    </li>
  )
}

/** "Forms": what the plan calls for, and the rest behind a click. */
export function FormsCard({ plan }: { plan: Plan }) {
  const [all, setAll] = useState(false)
  const { needed, others } = formsFor(plan)
  return (
    <div className="about-card c-forms">
      <h3>Forms</h3>
      {needed.length > 0 ? (
        <ul className="form-list">
          {needed.map((f) => (
            <FormItem key={f.id} form={f} because={f.because} />
          ))}
        </ul>
      ) : (
        <p className="about-none">Nothing in your plan calls for a form that we know of.</p>
      )}
      <button type="button" className="link more-btn" aria-expanded={all} onClick={() => setAll((a) => !a)}>
        {all ? 'Hide other forms' : `See ${others.length} ${needed.length ? 'other forms' : 'forms you might need'}`}
      </button>
      {all && (
        <ul className="form-list">
          {others.map((f) => (
            <FormItem key={f.id} form={f} />
          ))}
        </ul>
      )}
    </div>
  )
}
