// What the chat panel sends and how it reads a suggestion. The chatbot only proposes: these helpers decide whether a
// proposal still fits the board on screen, and say its changes in words.
import { displayCode } from '../setup/transcript.ts'
import type { ChatMessage, ChatRequest, Override, Plan, PlanChange } from '../types.ts'
import { indexPlan } from './graph.ts'

/** The backend's limits (docs/chat-format.md). */
export const MESSAGE_MAX = 4000
const MESSAGES_MAX = 40
const OVERRIDES_MAX = 50

/** The exceptions already accepted on this plan. Read from the plan itself, so undoing a change takes them back too. */
export function overridesOf(plan: Plan): Override[] {
  const index = indexPlan(plan)
  const found = new Map<string, Override>()
  for (const f of plan.flags) {
    if (!f.overridden || f.type !== 'exception_claimed' || !f.course_id) continue
    const code = index.courses.get(f.course_id)?.code
    if (code) found.set(code, { type: 'exception_claimed', code })
  }
  return [...found.values()].slice(0, OVERRIDES_MAX)
}

export const chatRequest = (plan: Plan, messages: ChatMessage[]): ChatRequest => ({
  plan,
  overrides: overridesOf(plan),
  // past the limit the oldest are dropped
  messages: messages.slice(-MESSAGES_MAX).map((m) => ({ role: m.role, text: m.text.slice(0, MESSAGE_MAX) })),
})

/** Which courses sit in which semester, and which exceptions are accepted: two plans with the same one look the same. */
export function boardKey(plan: Plan): string {
  const semesters = plan.semesters
    .filter((s) => s.courses.length > 0) // an empty semester added or removed changes nothing a suggestion touches
    .map((s) => `${s.label}:${s.courses.map((c) => c.code).sort().join(',')}`)
  const accepted = overridesOf(plan)
    .map((o) => o.code)
    .sort()
  return `${semesters.join(';')}|${accepted.join(',')}`
}

export function changeText(change: PlanChange): string {
  const code = displayCode(change.code)
  if (change.kind === 'add') return `Add ${code} to ${change.to_label}`
  if (change.kind === 'remove') return `Remove ${code} from ${change.from_label}`
  return `Move ${code} from ${change.from_label} to ${change.to_label}`
}
