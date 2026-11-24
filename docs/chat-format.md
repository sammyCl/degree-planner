# Chat format

What the planner page sends the chatbot with each message, and what the chatbot sends back.
Endpoint: `POST /plans/chat` (coming in the chat logic work; the format is fixed first so the chatbot panel can be built against it).
Pydantic models: `backend/src/degree_planner_backend/agent/chat_models.py`.
Samples: [chat-request.sample.json](chat-request.sample.json) and [chat-response.sample.json](chat-response.sample.json); the flag text and token counts in the response sample are illustrative, not real validator output or measured usage.

The plan is the one in the [plan format](plan-format.md), and `Override` and `Usage` are the ones in the [agent request format](agent-request-format.md), reused rather than copied.

## How a conversation works

The backend keeps no chat state. The planner page holds the conversation and sends all of it, with the plan on the board and the overrides the student already chose, every time the student sends a message.

The chatbot never changes the board itself. When the student asks for a change (swap an elective, move a course to another semester) or says they were granted an exception, the reply carries a proposed plan and a list of what it changes. The page shows the changes with an Apply button; on Apply it puts `proposed_plan` on the board and adds `accepted_overrides` to its overrides. Saving works as it does today (`POST /plans` or `PUT /plans/{plan_id}`).

## Request

| Field | Type | Required | Notes |
|---|---|---|---|
| `plan` | Plan | yes | the board as it is now, after any drag and drop. Its semester labels are the only ones the chatbot may use. The backend rebuilds and validates it, so its `flags` and `summary` are not trusted |
| `overrides` | array of Override | no | flags the student already overrode; `[]` if none, at most 50. Duplicates are dropped |
| `messages` | array of ChatMessage | yes | the conversation, oldest first, 1 to 40 messages; the last one must be the student's. Past 40, drop the oldest |

Unknown top-level fields (next to `plan`, `overrides` and `messages`) and unknown fields inside a message or an override are rejected. Unknown fields inside `plan` are currently accepted and ignored, because the plan format's models (`plan_models.py`) do not forbid them.

The plan's semesters must:
- each have a label like `"Fall 2026"` (season, one space, four ASCII digits), with no label twice;
- be in calendar order, earliest first (Spring, then Summer, then Fall of a year), because the validator checks prerequisites in list order;
- number at most 18 for `bachelor`, `combined`, `minor` and `asi`, and 15 for `master` and `phd` (the same limits as the agent request);
- each hold at most 12 courses with status `planned` (the chat tools' limit; `completed` rows do not count);
- hold only course codes like `CSCI101` (cleaned up first, so `"csci 101"` is fine; `"Calc I"` is not).

### ChatMessage

| Field | Type | Required | Notes |
|---|---|---|---|
| `role` | string | yes | `student` or `assistant` (send the chatbot's earlier `reply` back as `assistant`) |
| `text` | string | yes | at most 4,000 characters, with visible text (spaces and invisible characters alone do not count) |

The student's text is untrusted: the chatbot reads it as what the student said, never as instructions that change its rules. A student saying "I was granted an exception for CSCI400" is how an exception gets accepted, which is why accepting one is always shown to the student and never applied without Apply.

## Response

| Field | Type | Required | Notes |
|---|---|---|---|
| `reply` | string | yes | the chatbot's message, shown in the panel; at most 4,000 characters, with visible text |
| `proposed_plan` | Plan \| null | no | the plan with the proposed changes and accepted exceptions, rebuilt and validated by the backend. `null` when nothing is proposed: a question answered, a question asked back, or a run that stopped |
| `changes` | array of PlanChange | no | everything Apply changes on the board: `proposed_plan` compared with the request's plan as sent, worked out by the backend, at most 30. See "What Apply removes" below |
| `accepted_overrides` | array of Override | no | exceptions the student said were granted, which the chatbot accepted; today only `exception_claimed` |
| `still_open` | array of string | no | error flag messages still open in `proposed_plan`, so a change that breaks something is shown, not hidden. A proposal does not have to pass the validator: the student may want the change anyway |
| `open_exceptions` | array of string | no | course codes in `proposed_plan` whose exception the student has not decided yet (`exception_claimed` warnings not overridden), so the panel can ask about each one; an exception is a warning, so it is not in `still_open` |
| `problems` | array of string | no | why the run stopped early (step limit, timeout, error); then there is no proposal |
| `usage` | Usage | yes | token counts, as in the agent response |

`still_open` and `problems` have at most 30 entries of at most 600 characters each.

Rules the model checks:
- `proposed_plan` is present exactly when `changes` or `accepted_overrides` is not empty.
- `still_open` and `open_exceptions` are empty when there is no `proposed_plan`.
- An exception is only in `accepted_overrides` while its course is in `proposed_plan`.
- `problems` is not empty only when there is no `proposed_plan`.

### PlanChange

| Field | Type | Notes |
|---|---|---|
| `kind` | string | `add`, `remove` or `move` |
| `code` | string | catalog course code, cleaned up like the agent tools do (`"csci 400"` becomes `"CSCI400"`) |
| `from_label` | string \| null | where the course was: set for `remove` and `move`, `null` for `add` |
| `to_label` | string \| null | where it goes: set for `add` and `move`, `null` for `remove` |

Replacing one course with another shows as a `remove` and an `add`.

### What Apply removes

`proposed_plan` is rebuilt by the backend, so it holds only the courses the validator keeps: courses with status `completed`, courses not in the catalog, and a second copy of a course that may not repeat are left out. Apply would take those off the board, so they are listed in `changes` as `remove`, next to the chatbot's own edits, and nothing disappears without a change shown. Whether there is a proposal at all depends only on the chatbot's edits: a reply whose edits cancel out has no `proposed_plan`, even when the board holds such a course.

## What the chatbot may and may not do

- It may move, add, remove and replace courses, but only in the request's semesters and only with courses in the catalog data.
- It may accept an `exception_claimed` flag when the student says the exception was granted. It cannot accept any other flag type.
- A course substitution (an advisor letting course Y count for required course X) cannot be accepted here yet: the chatbot points the student to the form for it and leaves the flag open.

## Read-only once checked

`ChatRequest`, `ChatMessage`, `PlanChange` and `ChatResponse` are frozen, and their lists are tuples, as in the agent request format. Build a new model instead of changing one, and do not use `model_copy(update=...)` on them, since it skips validation.
