# Backend Plan: Midhat Sajad

Part: API (request router), database and data-loading pipeline, the common data format, the plan validator, transcript parser, plan store. Also data slice Graduate data: master's and PhD programs, combined BS+MS rules.

Master plan: [MASTER-PLAN.md](MASTER-PLAN.md). Status marks, priorities and how Claude uses this file are explained there.

**This part blocks the other two.** Data format and Plan format are due first; everyone else is waiting on them.

## Done means (from the proposal)

- One command loads and refreshes all collected data.
- Looking up a course returns its credits and prerequisites; looking up a program returns its required courses.
- A plan with a deliberately broken prerequisite is reported by the validator.
- An uploaded transcript becomes a list of completed courses.

## Waiting on others

| I need | From | For | Needed by |
|---|---|---|---|
| Bachelor's and course catalog data | Samantha Bachelor's data | Data loader, Lookups | Nov 18 |
| Minors, ASIs, forms data | Abdallah Minors data | Data loader, Lookups | Nov 18 |
| Request format the agent needs (task + context in, plan + explanation out) | Samantha Agent request format | Plan format, API endpoints | Nov 13 |
| Request format the UI needs | Abdallah Sample plan | Plan format, API endpoints | Nov 13 |

## Tasks

### Week 1: Nov 9-13 (foundations, blocks the team)

| Name | Task | Priority | Due | Needs | Status |
|---|---|---|---|---|---|
| Data format | **Common data format**: schema for courses (code, title, credits, description, prerequisites incl. and/or and corequisites), program requirements (required courses, elective groups, credit minimums, catalog year), forms and policies. Written as a short doc plus a sample file; shared with the team | P0 | Nov 13 | Stack decision | [x] |
| Plan format | **Plan JSON format**: semesters, courses in each, credits, prerequisite edges, validator flags. Used by the frontend, agent and validator | P0 | Nov 13 | | [ ] |
| Graduate list | Data: list the master's, combined and PhD programs needed for Examples 2, 3, 5 (EE master's, Mining BS+MS, non-thesis CS master's Project Track) and their combined-credit rules | P0 | Nov 13 | Five examples | [ ] |
| Stack decision | Lead the stack decision (language version, web framework, database); update CLAUDE.md Stack and Commands sections | P0 | Nov 13 | | [x] |

### Week 2: Nov 16-20 (first end-to-end)

| Name | Task | Priority | Due | Needs | Status |
|---|---|---|---|---|---|
| Backend scaffold | Project scaffold and database set up; one command to start the API; tests run with one command | P0 | Nov 16 | Stack decision | [ ] |
| Graduate data | Data: collect the master's/combined/PhD programs for the examples into the Data format format | P0 | Nov 18 | Data format, Graduate list | [ ] |
| Data loader | **Data loader**: one command loads and refreshes all collected data into the database; reports errors per file | P0 | Nov 17 | Data format, Backend scaffold | [ ] |
| Lookups | Lookups: course -> credits and prerequisites; program (and catalog year) -> required courses and elective groups; forms for a course. Agent tools wrap these | P0 | Nov 17 | Data loader | [ ] |
| Plan validator | **Plan validator** (rules code, no LLM): prerequisites in order, credit totals, all program requirements met, requirement overlap/double counting, transfer credits. Returns flags in the Plan format format. Test with a deliberately broken prerequisite | P0 | Nov 18 | Plan format, Lookups | [ ] |
| API endpoints | API endpoints: submit setup -> call agent -> return plan; check a move (drag and drop) -> validator; save/load plan in the plan store | P0 | Nov 18 | Plan format, Backend scaffold, Plan validator | [ ] |
| Transcript parser | Transcript parser: uploaded file becomes a list of completed courses; plus transfer credits. Needs a decision on file format (e.g. PDF or CSV) with the team. Never commit real transcripts | P1 | Nov 19 | Data format, Backend scaffold | [ ] |
| Catalog scraper | Catalog scraper with scheduled refresh (can be a manual script first, scheduling later) | P1 | Nov 20 | Data format, Catalog sources | [ ] |
| Integration day | Integration day (Nov 20): API serves the agent and frontend end to end | P0 | Nov 20 | API endpoints | [ ] |

### Week 3: Nov 23-25 (user trial)

| Name | Task | Priority | Due | Needs | Status |
|---|---|---|---|---|---|
| Trial-ready API | Make the API robust for the trial: input validation, clear error messages, timeouts when the agent is slow, logs | P0 | Nov 23 | Integration day | [ ] |
| Validator special rules | Handle examples' special rules in the validator (combined BS+MS shared credits, double counting, transfer credits, Independent Study credits) where the evaluation shows failures | P0 | Nov 25 | Plan validator, Eval runner | [ ] |
| Spot-check (Midhat) | Spot-check five random courses/requirements from a teammate's slice against the Mines catalog | P1 | Nov 25 | Bachelor's data or Minors data | [ ] |

### Week 4: Nov 30 - Dec 3 (finish)

| Name | Task | Priority | Due | Needs | Status |
|---|---|---|---|---|---|
| Backend fixes | Fix backend problems from the user trial | P0 | Dec 1 | User trial | [ ] |
| Backend threat model | Threat-model input from the backend side: file upload handling, what reaches the agent, scraped content as untrusted input, secrets handling (API key never in git) | P0 | Dec 2 | Threat model | [ ] |
| Backend decisions | Draft DECISIONS.md entries for backend choices (framework, database, validator as rules code, data format). Team writes the judgments; Claude does not | P1 | Dec 1 | | [ ] |
| Backend write-up | Write my section of the README and prepare my part of the presentation and likely questions | P0 | Dec 2 | | [ ] |

## If I run short, cut in this order

1. Graduate data PhD programs (then other graduate data per DECISIONS.md if data is messy)
2. Catalog scraper scheduled scraper (keep a one-time loader)
3. Transcript parser transcript parser, replaced by a typed list of completed courses

Never cut Data format, Plan format, Data loader, Lookups, Plan validator and API endpoints: the other two parts depend on them.

## Notes and decisions

- (none yet)

## Status log

- 2026-11-12: Plan created. Nothing started.
- 2026-11-13: Stack decision done: Python 3.12, `uv`, FastAPI, SQLite. Recorded in DECISIONS.md and CLAUDE.md's Stack section.
- 2026-11-13: Data format done: schema doc and sample file at `docs/data-format.md` and `docs/data-format.sample.json` (courses with AND/OR prerequisites, program requirement groups, combined/double-counted credits, forms). Pending push/PR to actually share with the team.
