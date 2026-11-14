# Plan format

The JSON shape for a student's degree plan: what the agent returns, what the planner page draws, and what the validator reads and writes flags onto.
A full example is in [plan-format.sample.json](plan-format.sample.json).

This is a different thing from the [data format](data-format.md): the data format describes the catalog (courses and programs as they exist), this format describes one student's arrangement of courses from that catalog into semesters.

## Plan

| Field | Type | Required | Notes |
|---|---|---|---|
| `plan_id` | string \| null | no | `null` for an unsaved draft; set once the plan store assigns one |
| `student` | Student | yes | see below |
| `semesters` | array of Semester | yes | in order |
| `prerequisite_edges` | array of Edge | yes | see below; drives the arrows on the planner page |
| `flags` | array of Flag | yes | validator output; `[]` if the plan is clean |
| `summary` | Summary | yes | `{"total_credits": number, "total_credits_required": number, "requirements_met": boolean}` |

### Student

| Field | Type | Required | Notes |
|---|---|---|---|
| `degree_level` | string | yes | `bachelor`, `master`, `phd`, `combined`, `minor`, `asi` |
| `programs` | array of program_id | yes | from the data format; more than one for a combined degree or a major+minor |
| `catalog_year` | string | yes | |
| `completed_courses` | array of CompletedCourse | yes | `[]` if none. `{"code": string, "credits": number, "term": "transfer" \| "aplcredit" \| a semester label, "transfer_from": string \| null}` |

## Semester

| Field | Type | Required | Notes |
|---|---|---|---|
| `semester_id` | string | yes | stable within the plan, e.g. `"sem-1"` |
| `label` | string | yes | e.g. `"Fall 2026"`, shown as the column header |
| `courses` | array of PlannedCourse | yes | |
| `total_credits` | number | yes | sum of this semester's courses, computed by the backend so the frontend never has to |

### Planned course

A course placed in a specific semester. It has its own id, separate from the catalog `code`, because drag-and-drop and the prerequisite edges need to point at *this placement*, not just the course in the abstract (the same course could in principle appear as a plan or re-take in two semesters).

| Field | Type | Required | Notes |
|---|---|---|---|
| `course_id` | string | yes | unique within the plan, e.g. `"sem-1-csci200"` |
| `code` | string | yes | catalog course code |
| `title` | string | yes | denormalized from the catalog so the frontend does not need a second lookup to render a box |
| `credits` | number | yes | |
| `status` | string | yes | `planned` or `completed` |

## Prerequisite edge

One arrow on the planner page: course `to` lists course `from` as a prerequisite, and both are placed somewhere in this plan.

| Field | Type | Required | Notes |
|---|---|---|---|
| `from` | course_id | yes | the prerequisite |
| `to` | course_id | yes | the course that needs it |

The validator computes these from the data format's `prerequisites` expression resolved against where each course actually landed; the frontend only draws them, it does not recompute the logic.

## Flag

What the validator found wrong, attached to a specific course placement so the frontend can highlight the right box.

| Field | Type | Required | Notes |
|---|---|---|---|
| `flag_id` | string | yes | |
| `type` | string | yes | `broken_prerequisite`, `credit_shortfall`, `requirement_unmet`, `double_count_exceeded`, `exception_claimed` |
| `severity` | string | yes | `error` (the plan is invalid) or `warning` (needs the student's attention but is not by itself invalid, e.g. a claimed exception) |
| `course_id` | course_id \| null | yes | `null` for a plan-wide flag like `requirement_unmet` |
| `message` | string | yes | shown to the student as-is |
| `overridable` | boolean | yes | true for `exception_claimed`, per DECISIONS.md: show a warning and let the student override rather than hard-block |
| `overridden` | boolean | yes | set by the student via the frontend; the validator does not clear the flag, it just stops counting it as an error once `overridden` is true |

## What drag-and-drop does with this

Moving a course is: take the plan JSON, move one `PlannedCourse` from one semester's `courses` array to another's, call the validator (`check_plan`) with the result, and replace `prerequisite_edges` and `flags` with what comes back. The frontend never computes a flag itself.
