import type { Plan } from './types.ts'
import samplePlanJson from './samplePlan.json'

// Hand-written plan to build the planner page against until the backend returns real plans.
// Eight semesters of a Computer Science BS, real catalog courses and prerequisites, with deliberate
// flags: a broken prerequisite (CSCI400 in the same semester as CSCI306), a credit shortfall, and unmet
// total credits. It is test data, not an official degree plan.
export const samplePlan = samplePlanJson as Plan
