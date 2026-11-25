// TypeScript shape of the plan JSON. Mirrors docs/plan-format.md (owner: Midhat); keep the two in sync.

export interface CompletedCourse {
  code: string
  credits: number
  term: string // "transfer", "aplcredit", or a semester label
  transfer_from: string | null
}

export interface PlannedCourse {
  course_id: string
  code: string
  title: string
  credits: number
  status: 'planned' | 'completed'
}

export interface Semester {
  semester_id: string
  label: string
  courses: PlannedCourse[]
  total_credits: number
}

export interface PrerequisiteEdge {
  from: string
  to: string
}

export type FlagType =
  | 'broken_prerequisite'
  | 'credit_shortfall'
  | 'requirement_unmet'
  | 'double_count_exceeded'
  | 'exception_claimed'

export interface Flag {
  flag_id: string
  type: FlagType
  severity: 'error' | 'warning'
  course_id: string | null
  message: string
  overridable: boolean
  overridden: boolean
}

/** Whether one requirement group of one program is met (computed by the backend's validator). */
export interface RequirementStatus {
  program_id: string
  group_id: string
  label: string
  kind: 'all' | 'choose_credits' | 'requirement'
  met: boolean
  credits_required: number | null
  credits_earned: number | null
  missing_count: number
}

/** One requirement group a planned course fills (computed by the backend's validator). */
export interface CountsToward {
  program_id: string
  group_id: string
  label: string
}

export interface Plan {
  plan_id: string | null
  student: {
    degree_level: string
    programs: string[]
    catalog_year: string
    completed_courses: CompletedCourse[]
  }
  semesters: Semester[]
  prerequisite_edges: PrerequisiteEdge[]
  flags: Flag[]
  summary: {
    total_credits: number
    total_credits_required: number
    requirements_met: boolean
  }
  /** course_id to the groups it fills; a planned course missing from here fills no group. Absent on older plans. */
  counts_toward?: Record<string, CountsToward[]>
  /** every requirement group of every program, and whether the plan meets it. Absent on older plans. */
  requirement_status?: RequirementStatus[]
}

// What the backend's POST /plans/submit-setup takes (docs/agent-request-format.md, owner: Midhat and Samantha).
export interface Override {
  type: 'exception_claimed'
  code: string
}

export interface AgentRequest {
  student: Plan['student']
  semesters: number
  start_term: string
  include_summers: boolean
  overrides: Override[]
}

// What POST /plans/submit-setup returns (docs/agent-request-format.md).
export interface Usage {
  input_tokens: number
  output_tokens: number
  steps: number
}

export interface AgentResponse {
  status: 'ok' | 'cannot_work'
  /** null only when the agent never proposed a plan */
  plan: Plan | null
  /** what the plan does and any choices the agent made, written for the student */
  explanation: string
  /** why the agent could not finish a valid plan; empty when status is "ok" */
  problems: string[]
  usage: Usage
}
