# Agent Plan: Samantha Clapp

Part: the Sonnet 5.5 agent (plan, check, revise loop), its tools, chatbot logic for electives and exceptions, and the evaluation of the five examples (including the GitHub Actions eval, cost numbers, EVAL.md). Also data slice D1: bachelor's degrees and course catalog entries.

Master plan: [MASTER-PLAN.md](MASTER-PLAN.md). Status marks, priorities and how Claude uses this file are explained there.

## Done means (from the proposal)

- On each of the five examples, the agent returns a plan that passes the validator.
- One command runs all five examples and prints how many passed.

## Waiting on others

| I need | From | For | Needed by |
|---|---|---|---|
| Common data format | Midhat B1 | D1 | Nov 13 |
| Plan JSON format | Midhat B2 | A1, A4 | Nov 13 |
| Lookups (course, program, forms) | Midhat B5 | A2 | Nov 17 |
| Validator | Midhat B6 | A3 | Nov 18 |
| Master's and combined data | Midhat D2b | A7 (Examples 2, 3, 5) | Nov 18 |
| Minors, ASIs, forms data | Abdallah D3b | A7 (Examples 4, 5) | Nov 18 |
| UI request format for chat | Abdallah F9 | A5 | Nov 19 |

Until B5 and B6 exist, build the agent against stub tools that return the sample data from B1, so the loop can be tested.

## Tasks

### Week 1: Nov 9-13 (foundations)

| ID | Task | Priority | Due | Needs | Status |
|---|---|---|---|---|---|
| A1 | Define what the backend sends the agent (student inputs, completed courses, semesters wanted) and what the agent returns (plan in B2 format + explanation); share with Midhat | P0 | Nov 13 | | [ ] |
| M2 | Write up the five examples in the repo: exact inputs, "right output" per the proposal, and where they live. Examples are in EVAL.md; add machine-readable input files | P0 | Nov 13 | | [ ] |
| D1a | Data: list the bachelor's degrees and courses needed for Examples 1, 4, 5 (CS General Track, AMS, CS BS with transfer credits and Thorson's honors) and the Mining BS for Example 3 | P0 | Nov 13 | M2 | [ ] |
| M3 | Lead the catalog-source decision (Mines catalog pages, scrape vs. export vs. give the agent pages) | P0 | Nov 13 | | [ ] |

### Week 2: Nov 16-20 (first end-to-end)

| ID | Task | Priority | Due | Needs | Status |
|---|---|---|---|---|---|
| D1b | Data: collect the bachelor's degrees and course catalog entries for the examples into the B1 format | P0 | Nov 18 | B1, D1a | [ ] |
| A2 | Agent tools: `search_catalog`, `get_prerequisites`, `get_program_requirements`, `get_forms`, each with clear descriptions and error returns, wrapping the backend lookups. Start with stubs | P0 | Nov 17 | B2, B5 (stubs first) | [ ] |
| A3 | `check_plan` tool calling the backend validator, returning flags the agent can act on | P0 | Nov 18 | B6 (stub first) | [ ] |
| A4 | Agent loop: plan, check, revise, with a step limit and a clear "cannot work" answer; system prompt covers: student stays in the loop, never invent courses not in the data. First target: Example 1 gives a valid plan | P0 | Nov 19 | A2, A3 | [ ] |
| A5 | Chat endpoint logic: the student asks for electives or applies a granted exception; the agent returns a reply and an updated plan. API key from environment only, never in git | P2 | Nov 19 | A4, B7 | [ ] |
| A6 | Exception handling: placement/instructor-approval exceptions the student says they were granted; show a warning and let the student override (DECISIONS) | P2 | Nov 20 | A5 | [ ] |
| A7 | **Eval runner**: one command runs all five examples, checks each plan with the validator and the "also must" requirements in EVAL.md, and prints how many passed. Saves token counts per run | P0 | Nov 20 | A4, M2 | [ ] |
| M6 | Integration day (Nov 20): agent plans Example 1 through the real backend | P0 | Nov 20 | A4 | [ ] |

### Week 3: Nov 23-25 (evaluation and user trial)

| ID | Task | Priority | Due | Needs | Status |
|---|---|---|---|---|---|
| A8 | Run all five examples several times, record pass counts and token counts per task. Raw numbers only; no guessing | P0 | Nov 25 | A7, D1b, D2b, D3b | [ ] |
| A9 | Fix agent failures the eval shows (prompt, tool descriptions, tool errors) or hand backend/data problems to Midhat/Abdallah by name | P0 | Nov 25 | A8 | [ ] |
| A10 | Watch the user trial with the team; note what the agent got wrong in the user's eyes (Example 5 is judged by Sammy) | P0 | Nov 24 | M6, M7 | [ ] |
| D1c | Spot-check five random courses/requirements from a teammate's slice against the Mines catalog | P1 | Nov 25 | D2b or D3b | [ ] |

### Week 4: Nov 30 - Dec 3 (finish)

| ID | Task | Priority | Due | Needs | Status |
|---|---|---|---|---|---|
| A11 | Baseline for the claim: the simpler approach the agent is compared against (team picks it in M8), run on the same five examples | P0 | Nov 30 | M8 | [ ] |
| A12 | GitHub Actions workflow that runs the eval on push and shows the numbers; API key stored as a repository secret (never in the repo) | P0 | Dec 1 | A7 | [ ] |
| A13 | Cost: from the token counts in A8, cost of one task and of 10,000 requests/day, with the arithmetic shown, for EVAL.md | P0 | Dec 2 | A8 | [ ] |
| A14 | Threat-model input from the agent side: private data (transcripts), untrusted content (scraped pages, user text), external communication (what can the agent send out?), and mitigations | P0 | Dec 2 | M9 | [ ] |
| A15 | Fill EVAL.md numbers, run links, and cost with the team; the team writes the claim and judgments | P0 | Dec 2 | A8, A11, A12, A13 | [ ] |
| A16 | Draft DECISIONS.md entries for agent choices (model, tool set, step limit). Team writes the judgments; Claude does not | P1 | Dec 1 | | [ ] |
| A17 | Write my section of the README and prepare my part of the presentation and likely questions | P0 | Dec 2 | | [ ] |

## If I run short, cut in this order

1. A5, A6 chatbot and exception handling (DECISIONS: chatbot first)
2. Example 5 as a "judged by Sammy" stretch if it does not pass; report it honestly
3. Example 3 (combined credits) if data is not there

Never cut A2-A4, A7, A8: they are the core path and the course-required eval.

## Notes and decisions

- (none yet)

## Status log

- 2026-11-12: Plan created. Nothing started.
