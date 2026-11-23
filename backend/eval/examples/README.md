# Eval examples

The five examples from the proposal (EVAL.md), as files the local eval reads (`uv run eval-examples`, from `backend/`). Example 5 lives in `private/`, which git ignores; ask Samantha for a copy.

Each file has:

- `id`, `name`, `difficulty`
- `request`: an agent request, exactly as the backend sends it (`docs/agent-request-format.md`)
- `also_must`: checks on the agent's plan, on top of the validator returning `ok`. Each check has a `type`, its fields, and an optional `why` saying where the rule comes from.

An example passes only if the validator says `ok`, every `also_must` check holds, and the adversarial checker (live Mines websites) finds no blocking problem. Example 5 also needs Sammy's review.

## Check types

Semesters are named by their labels (`"Fall 2029"`). `from` and `through` are inclusive and optional (leave them out for every semester).

| type | fields | holds when |
|---|---|---|
| `max_semester_credits` | `limit`, `from`, `through` | no semester in the range has more than `limit` credits |
| `course_in_semester` | `code`, `semester` | `code` is planned in `semester` |
| `not_planned` | `codes` | none of `codes` is planned |
| `completed_not_planned` | | no course in the request's `completed_courses` is planned again |
| `planned_credits` | `equals` | the planned (not completed) credits add up to `equals` |
| `in_every_semester` | `code` | `code` is planned in every semester |
| `count_planned` | `codes`, `exactly` | exactly `exactly` of `codes` are planned |
| `credits_from` | `codes`, `through`, `equals` or `max` | the credits of `codes` planned up to `through` equal `equals` (or are at most `max`) |
| `minor_unshared_credits` | `minor`, `major`, `min` | at least `min` of the credits that fill the minor do not also fill a requirement of `major` other than free electives |
| `flowchart_match` | `flowchart`, `tolerance`, `min_matched` | at least `min_matched` of the flowchart's courses are planned within `tolerance` semesters of their flowchart semester |
| `review_required` | `by` | a person's verdict is recorded for the run (the eval waits for it) |
