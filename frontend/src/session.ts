// Keeps the student's setup and plan while the tab is open, so a reload does not lose them. sessionStorage on purpose:
// it is cleared when the tab is closed, so completed courses do not stay behind on a shared computer. Nothing here is
// sent anywhere.
import { readPlan } from './api.ts'
import type { SetupForm } from './setup/validate.ts'
import type { AgentResponse } from './types.ts'

const KEY = 'dp-session'
const VERSION = 1

export interface Session {
  screen: 'setup' | 'planner'
  form?: SetupForm
  /** the latest plan, with the student's changes */
  response?: AgentResponse
}

const isForm = (value: unknown): value is SetupForm => {
  const form = value as SetupForm | undefined
  return !!form && typeof form.level === 'string' && [form.addOnIds, form.completed, form.files].every(Array.isArray)
}

/** What was saved, leaving out anything that no longer has the right shape. */
export function loadSession(): Session {
  try {
    const saved = JSON.parse(sessionStorage.getItem(KEY) ?? 'null')
    if (!saved || saved.version !== VERSION) return { screen: 'setup' }
    const form = isForm(saved.form) ? saved.form : undefined
    let response: AgentResponse | undefined
    try {
      if (saved.response) response = { ...saved.response, plan: readPlan(saved.response.plan) }
    } catch {
      response = undefined
    }
    return { screen: saved.screen === 'planner' && response ? 'planner' : 'setup', form, response }
  } catch {
    return { screen: 'setup' } // storage blocked, or not ours
  }
}

export function saveSession(session: Session): void {
  try {
    sessionStorage.setItem(KEY, JSON.stringify({ version: VERSION, ...session }))
  } catch {
    // storage blocked or full: the page works, a reload just starts over
  }
}
