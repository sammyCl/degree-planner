# Backend Plan: Midhat Sajad

Part: API (request router), database and data-loading pipeline, the common data format, the plan validator, transcript parser, plan store. Also data slice D2: master's and PhD programs, combined BS+MS rules.

Master plan: [MASTER-PLAN.md](MASTER-PLAN.md). Status marks, priorities and how Claude uses this file are explained there.

**This part blocks the other two.** B1 and B2 are due first; everyone else is waiting on them.

## Done means (from the proposal)

- One command loads and refreshes all collected data.
- Looking up a course returns its credits and prerequisites; looking up a program returns its required courses.
- A plan with a deliberately broken prerequisite is reported by the validator.
- An uploaded transcript becomes a list of completed courses.

## Waiting on others

| I need | From | For | Needed by |
|---|---|---|---|
| Bachelor's and course catalog data | Samantha D1 | B4, B5 | Nov 18 |
| Minors, ASIs, forms data | Abdallah D3b | B4, B5 | Nov 18 |
| Request format the agent needs (task + context in, plan + explanation out) | Samantha A1 | B2, B7 | Nov 13 |
| Request format the UI needs | Abdallah F2 | B2, B7 | Nov 13 |

## Tasks

### Week 1: Nov 9-13 (foundations, blocks the team)

| ID | Task | Priority | Due | Needs | Status |
|---|---|---|---|---|---|
| B1 | **Common data format**: schema for courses (code, title, credits, description, prerequisites incl. and/or and corequisites), program requirements (required courses, elective groups, credit minimums, catalog year), forms and policies. Written as a short doc plus a sample file; shared with the team | P0 | Nov 13 | M1 | [ ] |
| B2 | **Plan JSON format**: semesters, courses in each, credits, prerequisite edges, validator flags. Used by the frontend, agent and validator | P0 | Nov 13 | | [ ] |
| D2a | Data: list the master's, combined and PhD programs needed for Examples 2, 3, 5 (EE master's, Mining BS+MS, non-thesis CS master's Project Track) and their combined-credit rules | P0 | Nov 13 | M2 | [ ] |
| M1 | Lead the stack decision (language version, web framework, database); update CLAUDE.md Stack and Commands sections | P0 | Nov 13 | | [ ] |

### Week 2: Nov 16-20 (first end-to-end)

| ID | Task | Priority | Due | Needs | Status |
|---|---|---|---|---|---|
| B3 | Project scaffold and database set up; one command to start the API; tests run with one command | P0 | Nov 16 | M1 | [ ] |
| D2b | Data: collect the master's/combined/PhD programs for the examples into the B1 format | P0 | Nov 18 | B1, D2a | [ ] |
| B4 | **Data loader**: one command loads and refreshes all collected data into the database; reports errors per file | P0 | Nov 17 | B1, B3 | [ ] |
| B5 | Lookups: course -> credits and prerequisites; program (and catalog year) -> required courses and elective groups; forms for a course. Agent tools wrap these | P0 | Nov 17 | B4 | [ ] |
| B6 | **Plan validator** (rules code, no LLM): prerequisites in order, credit totals, all program requirements met, requirement overlap/double counting, transfer credits. Returns flags in the B2 format. Test with a deliberately broken prerequisite | P0 | Nov 18 | B2, B5 | [ ] |
| B7 | API endpoints: submit setup -> call agent -> return plan; check a move (drag and drop) -> validator; save/load plan in the plan store | P0 | Nov 18 | B2, B3, B6 | [ ] |
| B8 | Transcript parser: uploaded file becomes a list of completed courses; plus transfer credits. Needs a decision on file format (e.g. PDF or CSV) with the team. Never commit real transcripts | P1 | Nov 19 | B1, B3 | [ ] |
| B9 | Catalog scraper with scheduled refresh (can be a manual script first, scheduling later) | P1 | Nov 20 | B1, M3 | [ ] |
| M6 | Integration day (Nov 20): API serves the agent and frontend end to end | P0 | Nov 20 | B7 | [ ] |

### Week 3: Nov 23-25 (user trial)

| ID | Task | Priority | Due | Needs | Status |
|---|---|---|---|---|---|
| B10 | Make the API robust for the trial: input validation, clear error messages, timeouts when the agent is slow, logs | P0 | Nov 23 | M6 | [ ] |
| B11 | Handle examples' special rules in the validator (combined BS+MS shared credits, double counting, transfer credits, Independent Study credits) where the evaluation shows failures | P0 | Nov 25 | B6, A7 | [ ] |
| D2c | Spot-check five random courses/requirements from a teammate's slice against the Mines catalog | P1 | Nov 25 | D1 or D3b | [ ] |

### Week 4: Nov 30 - Dec 3 (finish)

| ID | Task | Priority | Due | Needs | Status |
|---|---|---|---|---|---|
| B12 | Fix backend problems from the user trial | P0 | Dec 1 | M7 | [ ] |
| B13 | Threat-model input from the backend side: file upload handling, what reaches the agent, scraped content as untrusted input, secrets handling (API key never in git) | P0 | Dec 2 | M9 | [ ] |
| B14 | Draft DECISIONS.md entries for backend choices (framework, database, validator as rules code, data format). Team writes the judgments; Claude does not | P1 | Dec 1 | | [ ] |
| B15 | Write my section of the README and prepare my part of the presentation and likely questions | P0 | Dec 2 | | [ ] |

## If I run short, cut in this order

1. D2 PhD programs (then other graduate data per DECISIONS.md if data is messy)
2. B9 scheduled scraper (keep a one-time loader)
3. B8 transcript parser, replaced by a typed list of completed courses

Never cut B1, B2, B4-B7: the other two parts depend on them.

## Notes and decisions

- (none yet)

## Status log

- 2026-11-12: Plan created. Nothing started.
