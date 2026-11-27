// The planning assistant beside the board (POST /plans/chat). The backend keeps no chat state, so the conversation lives
// here. A reply may suggest changes; the board only changes when the student clicks Apply.
import { useEffect, useRef, useState, type FormEvent } from 'react'
import { ApiError, sendChat } from '../api.ts'
import type { ChatMessage, ChatResponse, Plan } from '../types.ts'
import { boardKey, changeText, chatRequest, MESSAGE_MAX } from './chat.ts'
import { flagKind, isOpen } from './graph.ts'
import { plainAlert } from './plainFlags.ts'
import './ChatPanel.css'

interface Props {
  plan: Plan
  /** the board is being re-checked, so a suggestion cannot be applied this moment */
  busy: boolean
  onApply: (next: Plan) => void
}

interface Suggestion {
  response: ChatResponse
  plan: Plan
  /** the board the suggestion was made for */
  base: string
}

type Entry = ChatMessage & { suggestion?: Suggestion; stopped?: string[] }

const STARTERS = ['Suggest a different free elective', 'Make my busiest semester lighter', 'What do I need to check with my advisor?']

function SuggestionCard({ suggestion, current, busy, onApply }: { suggestion: Suggestion; current: string; busy: boolean; onApply: (next: Plan) => void }) {
  const { response, plan, base } = suggestion
  const applied = current === boardKey(plan)
  const outdated = !applied && current !== base
  const problems = plan.flags.filter((f) => isOpen(f) && flagKind(f) === 'error')
  return (
    <div className="chat-change" role="group" aria-label="Suggested change">
      <b>Suggested change</b>
      <ul>
        {response.changes.map((c, i) => (
          <li key={i}>{changeText(c)}</li>
        ))}
        {response.accepted_overrides.map((o) => (
          <li key={o.code}>Mark {o.code} as approved</li>
        ))}
      </ul>
      {problems.length > 0 && (
        <div className="chat-warn">
          <b>
            After this change, {problems.length} {problems.length === 1 ? 'problem is' : 'problems are'} left:
          </b>
          <ul>
            {problems.slice(0, 4).map((f) => (
              <li key={f.flag_id}>{plainAlert(f).text}</li>
            ))}
            {problems.length > 4 && <li>and {problems.length - 4} more</li>}
          </ul>
        </div>
      )}
      {response.open_exceptions.length > 0 && (
        <p className="chat-ask">
          Still to check: {response.open_exceptions.join(', ')}. If you already have approval, tell me.
        </p>
      )}
      {applied ? (
        <p className="chat-state" role="status">
          Applied. Use Undo on the board to take it back.
        </p>
      ) : outdated ? (
        <p className="chat-state">Your plan changed since this suggestion. Ask again.</p>
      ) : (
        <button type="button" className="btn primary" disabled={busy} onClick={() => onApply(plan)}>
          Apply
        </button>
      )}
    </div>
  )
}

export function ChatPanel({ plan, busy, onApply }: Props) {
  const [open, setOpen] = useState(false)
  const [entries, setEntries] = useState<Entry[]>([])
  const [draft, setDraft] = useState('')
  const [waiting, setWaiting] = useState(false)
  const [failed, setFailed] = useState<string | null>(null)
  const request = useRef<AbortController | null>(null)
  const log = useRef<HTMLDivElement>(null)
  const input = useRef<HTMLTextAreaElement>(null)
  const launcher = useRef<HTMLButtonElement>(null)
  const current = boardKey(plan)

  useEffect(() => () => request.current?.abort(), []) // leaving the page stops a reply in flight
  useEffect(() => {
    if (open) input.current?.focus()
  }, [open])
  useEffect(() => {
    if (log.current) log.current.scrollTop = log.current.scrollHeight
  }, [entries, waiting, open])

  const close = () => {
    setOpen(false)
    requestAnimationFrame(() => launcher.current?.focus())
  }

  const send = async (text: string) => {
    const said = text.trim()
    if (!said || waiting) return
    const history: Entry[] = [...entries, { role: 'student', text: said }]
    const abort = new AbortController()
    request.current = abort
    setEntries(history)
    setDraft('')
    setFailed(null)
    setWaiting(true)
    const base = boardKey(plan)
    try {
      const response = await sendChat(chatRequest(plan, history), abort.signal)
      if (abort.signal.aborted) return
      setEntries([
        ...history,
        {
          role: 'assistant',
          text: response.reply,
          suggestion: response.proposed_plan ? { response, plan: response.proposed_plan, base } : undefined,
          stopped: response.problems,
        },
      ])
    } catch (error) {
      // the message goes back in the box, so nothing the student typed is lost
      setEntries(entries)
      setDraft(said)
      if (abort.signal.aborted) return
      setFailed(
        error instanceof ApiError && error.kind === 'network'
          ? error.message
          : error instanceof ApiError && error.kind === 'agent_unavailable'
            ? 'The assistant is not available right now. Try again in a few minutes.'
            : 'The assistant could not answer. Try again.',
      )
    } finally {
      if (request.current === abort) setWaiting(false)
    }
  }

  const submit = (e: FormEvent) => {
    e.preventDefault()
    void send(draft)
  }

  if (!open)
    return (
      <button ref={launcher} type="button" className="chat-launch" onClick={() => setOpen(true)}>
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M21 12a8 8 0 01-11.5 7.2L4 21l1.8-5.5A8 8 0 1121 12z" />
        </svg>
        Ask the assistant
        {waiting && <i className="chat-dot" aria-label="working" />}
      </button>
    )

  return (
    <section className="chat" aria-label="Planning assistant" onKeyDown={(e) => e.key === 'Escape' && close()}>
      <div className="chat-head">
        <div>
          <b>Planning assistant</b>
          <span>It suggests changes. You decide.</span>
        </div>
        <button type="button" className="chat-close" aria-label="Close the assistant" onClick={close}>
          &times;
        </button>
      </div>
      <div className="chat-log" ref={log} role="log" aria-live="polite">
        {entries.length === 0 && !waiting && (
          <div className="chat-empty">
            <p>Ask me to swap an elective, move a course, or tell me about an approval you were given.</p>
            {STARTERS.map((s) => (
              <button key={s} type="button" className="chat-starter" onClick={() => void send(s)}>
                {s}
              </button>
            ))}
          </div>
        )}
        {entries.map((m, i) => (
          <div key={i} className={`chat-msg ${m.role}`}>
            {/* plain text: the backend takes the markdown out, and its line breaks are kept */}
            <p className="chat-text">{m.text}</p>
            {m.stopped && m.stopped.length > 0 && <p className="chat-ask">I stopped before finishing, so nothing changed. Try asking again.</p>}
            {m.suggestion && <SuggestionCard suggestion={m.suggestion} current={current} busy={busy} onApply={onApply} />}
          </div>
        ))}
        {waiting && (
          <div className="chat-wait" role="status">
            <span className="chat-typing" aria-hidden="true">
              <i />
              <i />
              <i />
            </span>
            Thinking. This can take a minute.
            <button type="button" className="link" onClick={() => request.current?.abort()}>
              Stop
            </button>
          </div>
        )}
      </div>
      {failed && (
        <p className="chat-error" role="alert">
          {failed}
        </p>
      )}
      <form className="chat-form" onSubmit={submit}>
        <textarea
          ref={input}
          aria-label="Message the assistant"
          placeholder="Type your question..."
          rows={2}
          maxLength={MESSAGE_MAX}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
              e.preventDefault()
              void send(draft)
            }
          }}
        />
        <button type="submit" className="btn primary" disabled={waiting || !draft.trim()}>
          Send
        </button>
      </form>
    </section>
  )
}
