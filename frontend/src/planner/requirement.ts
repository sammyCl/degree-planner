// A corequisite rule in words (docs/data-format.md, "Requirement expressions"), for the course details.
import type { Requirement } from '../types.ts'

/** "MATH213 or MATH223", "CBEN210 and (CBEN200 or CBEN201)", or the rule's own words for an exception. */
export function describeRequirement(rule: Requirement, nested = false): string {
  if (rule.type === 'course') return rule.code
  if (rule.type === 'exception') return rule.label
  const parts = rule.of.map((part) => describeRequirement(part, true))
  const joined = parts.join(rule.type === 'AND' ? ' and ' : ' or ')
  return nested && parts.length > 1 ? `(${joined})` : joined
}
