import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { samplePlan } from '../samplePlan.ts'
import type { ChatRequest, ChatResponse, Plan } from '../types.ts'
import { boardKey, changeText, chatRequest, overridesOf } from './chat.ts'
import { movePlanned } from './graph.ts'
import { PlannerPage } from './PlannerPage.tsx'

const plan: Plan = { ...samplePlan, student: { ...samplePlan.student, completed_courses: [] } }
const moved = movePlanned(plan, plan.semesters[0].courses[0].course_id, 1)
const code = plan.semesters[0].courses[0].code

const answer = (over: Partial<ChatResponse> = {}): ChatResponse => ({
  reply: 'I can move it.\n- one change',
  proposed_plan: moved,
  changes: [{ kind: 'move', code, from_label: plan.semesters[0].label, to_label: plan.semesters[1].label }],
  accepted_overrides: [],
  still_open: [],
  open_exceptions: [],
  problems: [],
  ...over,
})

const reply = (status: number, body: unknown) => ({ ok: status < 400, status, json: async () => body }) as Response

/** A backend that answers the chat with `chat` and hands every checked plan straight back. */
function backend(chat: () => Response | Promise<Response>) {
  const sent: ChatRequest[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init: RequestInit) => {
      if (url.endsWith('/chat')) {
        sent.push(JSON.parse(init.body as string))
        return chat()
      }
      return reply(200, JSON.parse(init.body as string))
    }),
  )
  return sent
}

const openChat = () => {
  render(<PlannerPage plan={plan} onBack={vi.fn()} />)
  fireEvent.click(screen.getByRole('button', { name: 'Ask the assistant' }))
  return screen.getByRole('region', { name: 'Planning assistant' })
}
const say = (text: string) => {
  fireEvent.change(screen.getByRole('textbox', { name: 'Message the assistant' }), { target: { value: text } })
  fireEvent.click(screen.getByRole('button', { name: 'Send' }))
}
const inSemester = (label: string) => within(screen.getByRole('region', { name: label })).queryByRole('button', { name: new RegExp(`^${code} `) })

afterEach(() => vi.unstubAllGlobals())

describe('chat helpers', () => {
  it('sends the exceptions accepted on the plan, and only the newest 40 messages', () => {
    const course = plan.semesters[0].courses[0]
    const flagged: Plan = {
      ...plan,
      flags: [{ flag_id: 'e', type: 'exception_claimed', severity: 'warning', course_id: course.course_id, message: 'x', overridable: true, overridden: true }],
    }
    expect(overridesOf(flagged)).toEqual([{ type: 'exception_claimed', code: course.code }])
    expect(boardKey(flagged)).not.toBe(boardKey({ ...flagged, flags: [] }))
    const many = Array.from({ length: 45 }, (_, i) => ({ role: 'student' as const, text: `m${i}` }))
    const request = chatRequest(flagged, many)
    expect(request.messages).toHaveLength(40)
    expect(request.messages[0].text).toBe('m5')
  })

  it('says each change in words', () => {
    expect(changeText({ kind: 'add', code: 'CSCI403', from_label: null, to_label: 'Fall 2027' })).toBe('Add CSCI403 to Fall 2027')
    expect(changeText({ kind: 'remove', code: 'CSCI403', from_label: 'Fall 2027', to_label: null })).toBe('Remove CSCI403 from Fall 2027')
  })
})

describe('ChatPanel', () => {
  it('sends the board and the message, shows the reply, and changes nothing until Apply', async () => {
    const sent = backend(() => reply(200, answer()))
    const chat = openChat()
    say('Move it later')
    const card = await within(chat).findByRole('group', { name: 'Suggested change' })
    expect(within(chat).getByText(/I can move it/).textContent).toBe('I can move it.\n- one change')
    expect(card).toHaveTextContent(`Move ${code} from ${plan.semesters[0].label} to ${plan.semesters[1].label}`)
    expect(sent[0].messages).toEqual([{ role: 'student', text: 'Move it later' }])
    expect(sent[0].plan.semesters[0].courses[0].code).toBe(code)
    expect(inSemester(plan.semesters[0].label)).toBeInTheDocument()

    fireEvent.click(within(card).getByRole('button', { name: 'Apply' }))
    expect(inSemester(plan.semesters[1].label)).toBeInTheDocument()
    expect(await within(card).findByText(/Applied/)).toBeInTheDocument()
    // Undo takes it back, and the suggestion can be applied again
    fireEvent.click(screen.getByRole('button', { name: 'Undo' }))
    expect(inSemester(plan.semesters[0].label)).toBeInTheDocument()
    expect(await within(card).findByRole('button', { name: 'Apply' })).toBeInTheDocument()
  })

  it('remembers a suggestion was applied after the plan changes again', async () => {
    backend(() => reply(200, answer()))
    const chat = openChat()
    say('Move it')
    const card = await within(chat).findByRole('group', { name: 'Suggested change' })
    fireEvent.click(within(card).getByRole('button', { name: 'Apply' }))
    await within(card).findByText(/^Applied/)
    const dataTransfer = { setData: vi.fn(), effectAllowed: '', dropEffect: '' }
    const column = screen.getByRole('region', { name: plan.semesters[2].label })
    fireEvent.dragStart(inSemester(plan.semesters[1].label)!, { dataTransfer })
    fireEvent.dragOver(column, { dataTransfer })
    fireEvent.drop(column, { dataTransfer })
    fireEvent.click(screen.getByRole('button', { name: 'Close the assistant' }))
    fireEvent.click(screen.getByRole('button', { name: 'Ask the assistant' }))
    expect(screen.getByText('You applied this. Your plan has changed since.')).toBeInTheDocument()
  })

  it('does not apply a suggestion to a board that has changed since', async () => {
    backend(() => reply(200, answer({ proposed_plan: movePlanned(plan, plan.semesters[0].courses[0].course_id, 2) })))
    const chat = openChat()
    say('Move it')
    const card = await within(chat).findByRole('group', { name: 'Suggested change' })
    // the student drags the course somewhere else first
    const dataTransfer = { setData: vi.fn(), effectAllowed: '', dropEffect: '' }
    const column = screen.getByRole('region', { name: plan.semesters[1].label })
    fireEvent.dragStart(inSemester(plan.semesters[0].label)!, { dataTransfer })
    fireEvent.dragOver(column, { dataTransfer })
    fireEvent.drop(column, { dataTransfer })
    expect(await within(card).findByText(/Your plan changed/)).toBeInTheDocument()
    expect(within(card).queryByRole('button', { name: 'Apply' })).not.toBeInTheDocument()
  })

  it('keeps the conversation when closed, and sends it with the next message', async () => {
    const sent = backend(() => reply(200, answer({ reply: 'Sure.', proposed_plan: null, changes: [] })))
    openChat()
    say('First')
    await screen.findByText('Sure.')
    fireEvent.click(screen.getByRole('button', { name: 'Close the assistant' }))
    fireEvent.click(screen.getByRole('button', { name: 'Ask the assistant' }))
    expect(screen.getByText('Sure.')).toBeInTheDocument()
    say('Second')
    await waitFor(() => expect(sent).toHaveLength(2))
    expect(sent[1].messages.map((m) => m.role)).toEqual(['student', 'assistant', 'student'])
  })

  it.each([
    [503, 'The assistant is not available right now.'],
    [500, 'The assistant could not answer.'],
    [422, "The assistant can't work with this plan yet. x"],
    [502, "Can't reach the server"],
  ])('puts the message back and says why after a %i', async (status, words) => {
    backend(() => (status === 502 ? ({ ok: false, status, json: async () => Promise.reject(new Error('x')) }) as unknown as Response : reply(status, { detail: 'x' })))
    openChat()
    say('Hello')
    expect(await screen.findByRole('alert')).toHaveTextContent(words)
    expect(screen.getByRole('textbox', { name: 'Message the assistant' })).toHaveValue('Hello')
  })

  it('can be stopped while it thinks', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(
        (_url: string, init: RequestInit) =>
          new Promise((_resolve, reject) => init.signal!.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')))),
      ),
    )
    openChat()
    say('Hello')
    fireEvent.click(await screen.findByRole('button', { name: 'Stop' }))
    await waitFor(() => expect(screen.queryByRole('button', { name: 'Stop' })).not.toBeInTheDocument())
    expect(screen.getByRole('textbox', { name: 'Message the assistant' })).toHaveValue('Hello')
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('says so when the assistant stopped early', async () => {
    backend(() => reply(200, answer({ proposed_plan: null, changes: [], problems: ['step limit'] })))
    openChat()
    say('Hello')
    expect(await screen.findByText(/nothing changed/)).toBeInTheDocument()
  })
})
