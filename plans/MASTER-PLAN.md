# Master Plan: Degree Planner (Group 9, P4)

The overall plan from today to the presentation. Each person's detailed plan is linked below; this file holds the milestones, the cross-part dependencies, and the order of work.

| Plan | Owner | File |
|---|---|---|
| Frontend | Abdallah Salhi | [FRONTEND-PLAN.md](FRONTEND-PLAN.md) |
| Backend, data format, validator | Midhat Sajad | [BACKEND-PLAN.md](BACKEND-PLAN.md) |
| Agent, tools, chatbot logic, evaluation | Samantha Clapp | [AGENT-PLAN.md](AGENT-PLAN.md) |

Source of truth for scope: the team proposal (submitted Fri Nov 6) and [README.md](../README.md). Course requirements: `projects/p4-full-stack-agent/README.md` in the course repo.

## How we and Claude use these plans

- Status marks: `[ ]` not started, `[~]` in progress, `[x]` done, `[!]` blocked (write who or what blocks it).
- Every task has an ID (F = frontend, B = backend, A = agent, D = data collection, M = whole team). **Needs** lists the IDs that must be done first, including tasks owned by someone else.
- Priority: **P0** = core path, the product does not work without it. **P1** = should have. **P2** = stretch, first to cut (see "What to cut first").
- Tick a box in the same commit or PR that finishes the task, and add a line to the status log at the bottom of your plan.
- Asking Claude "what should I work on next?" or "what am I waiting on?": Claude reads all four plans, finds your unchecked tasks whose **Needs** are all done, and lists them by priority and date. For tasks that are waiting, it names the task and the owner you are waiting on, and says what that person should do first.
- Claude only ticks a box when the team member says the task is done or the code and tests show it. It does not invent results, costs, or decisions (see [CLAUDE.md](../CLAUDE.md)).

## Timeline and milestones

Today is Thu Nov 12. Dates marked "target" are our own; the others come from the course schedule.

| Date | Milestone | Who |
|---|---|---|
| Fri Nov 13 | **M1** Repo set up (done), data format agreed, stack chosen, catalog sources chosen, five examples finalized, UI mockup | All |
| Fri Nov 20 | **M2** First end-to-end version (target): setup form -> backend -> agent -> plan drawn on the planner page | All |
| Tue Nov 24 | **M3** A real user tries it (target); optional dry run in lecture 25 | All |
| Wed Nov 25 | **M4** Five examples evaluated; first eval numbers in hand | Samantha leads |
| Thu Nov 26 - Fri Nov 27 | Thanksgiving, no work planned | |
| Tue Dec 1 | **M5** Lecture 26 (security and guardrails): threat model written afterwards | All |
| Wed Dec 2 | **M6** Feature freeze, demo recorded, README, DECISIONS, EVAL complete, repo public and clean | All |
| Thu Dec 3 or Tue Dec 8 | **M7** Presentation (day not yet recorded, confirm). Dec 8 is also the P4 due date | Each presents their own part |

### Week by week

**Nov 9-13: foundations**
- B1 data format and D slices start (blocks everything else).
- M-tasks: decide stack, catalog sources, finalize five examples, UI mockup (F1).

**Nov 16-20: first end-to-end**
- Data collection finishes for the examples' programs (D tasks).
- Backend: loader, lookups, validator, API (B tasks). Agent: tools and loop (A tasks). Frontend: both pages with stub data, then wired to the API (F tasks).
- Fri Nov 20: integration day, M2.

**Nov 23-25: user and evaluation**
- User trial Tue Nov 24, collect their feedback the same day.
- Run the five examples, record pass counts (A tasks), fix breaking bugs.

**Nov 30 - Dec 3: finish**
- Fix what the user found, cost numbers, threat model (after Dec 1 lecture), demo recording, docs, AI-assisted repo pass, presentation practice.

## Whole-team tasks

| ID | Task | Priority | Due | Needs | Status |
|---|---|---|---|---|---|
| M1 | Decide stack (Python version, package manager, web framework, frontend approach, database) and record in DECISIONS.md and CLAUDE.md. Gotcha: `uv run` fails in paths with a colon; this repo path has none | P0 | Nov 13 | | [ ] |
| M2 | Agree the five examples' exact inputs and "right output" and where they live in the repo (Samantha writes them up; everyone reviews) | P0 | Nov 13 | | [ ] |
| M3 | Choose catalog sources (Mines online catalog pages, department pages, forms) and decide scrape vs. export vs. giving the agent pages directly | P0 | Nov 13 | | [ ] |
| M4 | Write up the real-user conversation (who, role, what it costs them today, their words) and confirm Nov 20 and Nov 24 dates with the user | P0 | Nov 16 | | [ ] |
| M5 | Confirm which presentation day (Dec 3 or Dec 8) | P1 | Nov 16 | | [ ] |
| M6 | Integration day: run the whole path on Example 1, fix seams | P0 | Nov 20 | B5, B7, A4, F6 | [ ] |
| M7 | User trial, take notes, turn feedback into tasks in the three plans | P0 | Nov 24 | M6 | [ ] |
| M8 | Pick the one measured claim and baseline for EVAL.md (taught later in the course; team judgment) | P0 | Nov 25 | A7 | [ ] |
| M9 | Threat model: which lethal-trifecta parts we have (private data, untrusted content, external communication) and mitigations. Draft after lecture 26 | P0 | Dec 2 | | [ ] |
| M10 | Cost: one task and 10,000 requests/day, from real token counts measured in the eval | P0 | Dec 2 | A8 | [ ] |
| M11 | GitHub Actions workflow that runs the eval (agent owner builds, team reviews) | P0 | Dec 1 | A7 | [ ] |
| M12 | README, DECISIONS.md, EVAL.md filled in by the team, placeholders resolved; repo public, no secrets or real transcripts | P0 | Dec 2 | M8, M9, M10 | [ ] |
| M13 | Record the demo and link it in the README | P0 | Dec 2 | M6 | [ ] |
| M14 | AI-assisted pass over the repo that the instructor reviews; fix what it finds | P1 | Dec 2 | M12 | [ ] |
| M15 | Presentation: each person prepares their own part and Q&A. Optional dry run Nov 24 | P0 | Dec 2 | | [ ] |

## Cross-part dependencies

Read this when deciding who unblocks whom. Arrow means "must exist before".

| From | To | What | Needed by |
|---|---|---|---|
| Midhat B1 | Everyone | Common data format (schema for courses, prerequisites, program requirements, forms) | Nov 13. D tasks cannot start without it |
| Midhat B2 | Abdallah, Samantha | Plan JSON format (semesters, courses, flags) and request/response formats | Nov 13 |
| Midhat B6 | Abdallah F7, Samantha A3 | Validator and its flags | Nov 18 |
| Midhat B4, B5 | Samantha A2 | Lookup functions the agent tools wrap (course, program, forms) | Nov 17 |
| Midhat B7 | Abdallah F6 | API endpoints for setup submit and drag-check | Nov 18 |
| Samantha A5 | Abdallah F9 | Chat endpoint and reply format | Nov 19 |
| Samantha D1 | Samantha A7 | Bachelor's data for Examples 1, 4, 5 | Nov 20 |
| Midhat D2 | Samantha A7 | Master's and combined data for Examples 2, 3, 5 | Nov 20 |
| Abdallah D3 | Samantha A7 | Minor, ASI, forms data for Examples 4, 5 | Nov 20 |
| Samantha A7 | Everyone | Eval run and pass counts | Nov 25 |

## Critical path

B1 (data format) -> D1, D2, D3 (data) -> B4/B5 (lookups) -> A2 (tools) -> A4 (agent produces a plan) -> M6 (end to end) -> M7 (user trial) -> A7 (eval) -> M8, M10, M12 (docs) -> M13 (demo) -> M15 (present).

If B1 slips past Nov 14, M2 (Nov 20) is at risk. Everyone should check B1 first.

## What to cut first

From DECISIONS.md (team's current choices):
1. Chatbot (F9, A5, A6) is cut first if scope creeps.
2. If catalog data is messy: cut minors, ASIs/certifications, PhDs first.
3. Hidden prerequisite exceptions: show a warning and let the user override.

The proposal text lists different cut orders (one major and one minor only; then master's and 4+1; then drag and drop). **Open question for the team:** which order is final? Until decided, tasks tagged P2 are the cut candidates under DECISIONS.md.

## Risks to watch

| Risk | Early warning | Response |
|---|---|---|
| Messy catalog data (PDFs, changing pages) | D tasks take more than 1 day per program | Cut to fewer programs per the order above |
| Hidden prerequisite exceptions | Validator passes a plan the user says is wrong | Warning plus override (B6, F7) |
| Integration slips past Nov 20 | B7, A4 or F6 not done by Nov 18 | Stub data on the frontend, mock agent on the backend, per-part plans |
| Eval claim not ready | No pass counts by Nov 25 | A7 gets priority over polish |
| Thanksgiving break | | No tasks planned Nov 26-27; Nov 25 is the buffer |

## Status log

- 2026-11-12: Plans created from the proposal and README. No tasks started in these plans yet.
