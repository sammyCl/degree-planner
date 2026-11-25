# Agent request format

What the backend sends the agent loop when a student submits the setup page, and what the agent loop sends back.
Pydantic models: `backend/src/degree_planner_backend/agent/request_models.py`.
Samples: [agent-request.sample.json](agent-request.sample.json) and [agent-response.sample.json](agent-response.sample.json); the token counts in the response sample are illustrative, not measured.

The student and the plan are the ones in the [plan format](plan-format.md), reused rather than copied, so there is one definition of each.

## Request

| Field | Type | Required | Notes |
|---|---|---|---|
| `student` | Student | yes | from the plan format: degree level, programs, catalog year, completed courses (from the transcript parser or typed in) |
| `semesters` | integer | yes | how many semesters the student wants to finish in, summers included when `include_summers` is true. 1 to 18 for `bachelor`, `combined`, `minor` and `asi`; 1 to 15 for `master` and `phd` |
| `start_term` | string | yes | `"Fall 2026"`, `"Spring 2027"` or `"Summer 2027"`: the season, one space, a four-digit year (ASCII digits) from 2000 to 2500. Only the start year is limited, so later labels can run past 2500 |
| `include_summers` | boolean | no | `false` by default: plan Fall and Spring only |
| `overrides` | array of Override | no | flags the student already chose to override; `[]` if none, at most 50. Duplicates are dropped |

Unknown fields are rejected.
`semesters` must be a JSON integer and `include_summers` a JSON boolean: `"8"`, `8.0`, `true` for a number, or `"yes"` and `1` for a boolean are rejected rather than converted, because they mean the sender has a bug.

### Semester labels

The backend makes the labels from `start_term`, `semesters` and `include_summers` (`AgentRequest.semester_labels()`), so the model plans into fixed terms and never invents one.

- Without summers: Fall, Spring, Fall, ... (Fall 2026 is followed by Spring 2027, then Fall 2027).
- With summers: Fall, Spring, Summer, Fall, ... (Spring 2027 is followed by Summer 2027, then Fall 2027).
- A Summer start term is always kept, even without summers: Summer 2027, Fall 2027, Spring 2028.

### Override

| Field | Type | Required | Notes |
|---|---|---|---|
| `type` | string | yes | a flag type the student is allowed to override; today only `exception_claimed` (`OVERRIDABLE_FLAG_TYPES` in `agent/tools.py`). Any other type is rejected |
| `code` | string | yes | catalog course code of the flagged course, at most 20 characters; cleaned up like the agent tools do (`"mngn 501"` becomes `"MNGN501"`) and rejected if it is not a course code |

Overrides are keyed by course code, not `course_id`, so an override still applies after the agent moves the course to another semester.

### Not in the first version

Free-text notes from the student ("no Friday classes"). They come with Chat logic, and they are untrusted text going into the prompt, which goes in the threat model.

## Response

| Field | Type | Required | Notes |
|---|---|---|---|
| `status` | string | yes | `ok` or `cannot_work` |
| `plan` | Plan \| null | yes | from the plan format, with the validator's edges, flags and summary |
| `explanation` | string | yes | shown to the student: what the plan does and any choices the agent made; at most 4,000 characters, and it must have visible text (spaces, zero-width and other invisible characters alone do not count) |
| `problems` | array of string | yes | why it cannot work; `[]` when `status` is `ok`; at most 30 entries of at most 600 characters each (the same limits as the flags `check_plan` shows), each with visible text |
| `choices` | array of string | no, default `[]` | each choice the agent made where the requirements left it open (which elective fills a group, which semester a course went in), one per item, written for the student; at most 12 items of at most 500 characters, each with visible text |
| `notes` | array of string | no, default `[]` | each thing the student should confirm with their advisor or the department (an approval, a course offered only some terms, the catalog year a minor's requirements come from), same limits as `choices` |
| `usage` | Usage | yes | token counts for the eval and the cost numbers |

- `choices` and `notes` come from the agent's `submit_summary` tool, which it calls once after its last `check_plan`. They are empty when the agent did not call it, called it before a later `check_plan` (a changed plan clears the summary), or did not finish (timeout, step limit, error). `explanation` still holds the agent's whole message, so a page that does not read the two lists yet loses nothing.

- `ok`: `plan` is present, its `summary.requirements_met` is true, its `summary.total_credits` is at least `total_credits_required`, it has no open error flag, and `problems` is empty. An error counts as handled only when it is `overridden` and its type is one the student may override (today `exception_claimed`); the flag's own `overridable` field is not trusted (see BUG-032). An open `exception_claimed` warning is allowed: the planner page shows it and the student overrides it there.
- `cannot_work`: `problems` has at least one entry. `plan` is the agent's last attempt with its flags, so the planner page can still draw it and the student can fix it by hand; it is `null` only when the agent never proposed a plan (for example, a program that is not loaded).

The backend always rebuilds and validates the plan (`build_plan`, then the validator), so the plan in a response is never the model's output taken as is.
A response on its own cannot tell whether its plan answers the request (same student, the labels from `semester_labels()` in order); the Agent loop checks that before it returns.

## Read-only once checked

`AgentRequest`, `Override`, `AgentResponse` and `Usage` are frozen: a field cannot be changed after the model is built, and `overrides` and `problems` are tuples, so nothing can be appended. Build a new model instead of changing one. `model_copy(update=...)` skips validation in Pydantic, so do not use it on these models.

### Usage

All three are strict integers: `true`, `"500"` and `5.0` are rejected.

| Field | Type | Notes |
|---|---|---|
| `input_tokens` | integer | summed over every model call in the loop |
| `output_tokens` | integer | summed over every model call in the loop |
| `steps` | integer | model calls made, at most the loop's step limit; at least 1 whenever any tokens were used |

When saving a response to a file (for example in the eval runner), dump it with `model_dump_json(by_alias=True)`: without it, prerequisite edges are written as `from_` instead of the plan format's `from` (BUG-031). FastAPI already does this for responses.
