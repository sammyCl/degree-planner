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
| Plan format | **Plan JSON format**: semesters, courses in each, credits, prerequisite edges, validator flags. Used by the frontend, agent and validator | P0 | Nov 13 | | [x] |
| Graduate list | Data: list the master's, combined and PhD programs needed for Examples 2, 3, 5 (EE master's, Mining BS+MS, non-thesis CS master's Project Track) and their combined-credit rules | P0 | Nov 13 | Five examples | [x] |
| Stack decision | Lead the stack decision (language version, web framework, database); update CLAUDE.md Stack and Commands sections | P0 | Nov 13 | | [x] |

### Week 2: Nov 16-20 (first end-to-end)

| Name | Task | Priority | Due | Needs | Status |
|---|---|---|---|---|---|
| Backend scaffold | Project scaffold and database set up; one command to start the API; tests run with one command | P0 | Nov 16 | Stack decision | [x] |
| Graduate data | Data: collect the master's/combined/PhD programs for the examples into the Data format format | P0 | Nov 18 | Data format, Graduate list | [x] |
| Data loader | **Data loader**: one command loads and refreshes all collected data into the database; reports errors per file | P0 | Nov 17 | Data format, Backend scaffold | [x] |
| Lookups | Lookups: course -> credits and prerequisites; program (and catalog year) -> required courses and elective groups; forms for a course. Agent tools wrap these | P0 | Nov 17 | Data loader | [x] |
| Plan validator | **Plan validator** (rules code, no LLM): prerequisites in order, credit totals, all program requirements met, requirement overlap/double counting, transfer credits. Returns flags in the Plan format format. Test with a deliberately broken prerequisite | P0 | Nov 18 | Plan format, Lookups | [x] |
| API endpoints | API endpoints: submit setup -> call agent -> return plan; check a move (drag and drop) -> validator; save/load plan in the plan store | P0 | Nov 18 | Plan format, Backend scaffold, Plan validator | [~] |
| Transcript parser | Transcript parser: uploaded file becomes a list of completed courses; plus transfer credits. Needs a decision on file format (e.g. PDF or CSV) with the team. Never commit real transcripts | P1 | Nov 19 | Data format, Backend scaffold | [x] |
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

- Graduate program data (`data/json/graduate-programs.json`) simplifies two things the data format can't cleanly express, written down here so a teammate can revisit them: (1) EE's M.S. core is track-specific in the real catalog (Antennas/Wireless, Information/Systems, Power/Energy each have their own required-plus-choose-one-or-more structure); I modeled it as one `choose_credits` group over the union of all three tracks' courses, credits_required 12, rather than modeling tracks as separate programs. (2) The combined programs' `total_credits_required` (`mining-bs-ms-combined` 152, `cs-bs-ms-combined` 154) is computed from the bachelor's totals in `docs/data-format.sample.json` (128, 130) since the real `mining-bs`/`cs-bs-general-track` entries aren't in `data/json/` yet; recompute both once Samantha's/Abdallah's real bachelor's data lands.

## Status log

- 2026-11-12: Plan created. Nothing started.
- 2026-11-13: Stack decision done: Python 3.12, `uv`, FastAPI, SQLite. Recorded in DECISIONS.md and CLAUDE.md's Stack section.
- 2026-11-13: Data format done: schema doc and sample file at `docs/data-format.md` and `docs/data-format.sample.json` (courses with AND/OR prerequisites, program requirement groups, combined/double-counted credits, forms). Pending push/PR to actually share with the team.
- 2026-11-13: Plan format done: schema doc and sample file at `docs/plan-format.md` and `docs/plan-format.sample.json` (semesters, per-placement course ids, prerequisite edges, validator flags with override support). Sample includes a deliberately broken prerequisite. Pending push/PR to actually share with the team.
- 2026-11-13: Backend scaffold done: `backend/` is a uv project (Python 3.12, FastAPI, SQLite). `uv sync` installs, `uv run uvicorn degree_planner_backend.main:app --reload` starts the API, `uv run pytest` runs tests (1 passing, checks the DB connection via `/health`). Commands recorded in CLAUDE.md and README.md. Pending push/PR.
- 2026-11-17: Data loader done: Pydantic models for the data format (`degree_planner_backend/models.py`), SQLite schema and `refresh_database()` (`db.py`, `data_loader.py`), and a `load-data [dir]` command (default `data/`) that clears and reloads courses/programs/forms, reporting validation errors per file without aborting the rest. 5 tests passing, including an end-to-end load of `docs/data-format.sample.json`. Pending push/PR.
- 2026-11-17: Lookups done: `degree_planner_backend/lookups.py` adds `get_course`/`get_prerequisites`/`get_program`/`get_program_requirements`/`search_catalog`/`get_forms` over the loaded SQLite data, resolving catalog year automatically and raising `NotFoundError`/`AmbiguousLookupError` when a course or program is missing or spans multiple catalog years. 14 tests passing (9 new). Pending push/PR.
- 2026-11-17: Plan validator done: `degree_planner_backend/plan_models.py` (Pydantic models for the plan format) and `degree_planner_backend/validator.py`'s `check_plan(connection, plan)` (rules code, no LLM) check prerequisite order, credit totals, "all"/"choose_credits" program requirements, double-counted credits against each program's cap, and claimed exceptions (flagged as an overridable warning, never silently passed); it recomputes `prerequisite_edges`, `flags`, and `summary` and carries forward any flag the student already overrode. 19 tests passing (5 new), including the sample plan's deliberately broken CSCI400 prerequisite. Pending push/PR.
- 2026-11-17: API endpoints in progress: `POST /plans/check` (drag-and-drop re-validation via the validator) and the plan store (`degree_planner_backend/plan_store.py`'s `save_plan`/`load_plan`, wired up as `POST /plans`, `PUT /plans/{plan_id}`, `GET /plans/{plan_id}`) are done and tested (26 tests passing, 7 new). `/health` now goes through the same `get_db` dependency so tests can override it. Still need: submit-setup -> call agent -> return plan, which is blocked on Samantha's Agent request format and Agent loop. Pending push/PR.
- 2026-11-17: Transcript parser done: file-format decision (Midhat) is CSV and PDF. `degree_planner_backend/transcript_parser.py`'s `parse_transcript_csv` reads our own `code,credits,term,transfer_from` CSV; `parse_transcript_pdf` extracts text (via `pypdf`, new dependency) and reads semester/transfer/AP-credit headings followed by course lines, pulling the course code and the last decimal-point number on the line as credits. Both return `CompletedCourse` rows for the plan format. 34 tests passing (8 new), using only synthetic transcript data, never a real one. Pending push/PR.
- 2026-11-19: API endpoints gained `POST /transcripts/parse`: takes an uploaded `.csv` or `.pdf` transcript file, runs it through the transcript parser, and returns the parsed `CompletedCourse` list (400 on an unrecognized extension or a parse error). Uses `python-multipart`, new dependency, for the file upload. This is what FRONTEND-PLAN.md's "Waiting on others" table calls the Transcript upload endpoint, due Nov 19; Abdallah's Transcript upload task (frontend) can wire up to it now. 38 tests passing (4 new). Still need for API endpoints: submit-setup -> call agent -> return plan, blocked on Samantha's Agent request format and Agent loop. Pending push/PR.
- 2026-11-20: Graduate list and Graduate data done: `data/json/graduate-programs.json` has the master's and combined programs for Examples 2, 3, 5, read from the real catalog PDFs in `data/Graduate Programs/` (Electrical Engineering, Mining Engineering, Computer Science, Combined Undergraduate-Graduate Degree Programs). `ee-ms` (30 credits: seminar, 12-credit core, 18-credit technical electives), `mining-ms` (30 credits: 6-credit core choice, 1-credit seminar, 23-credit coursework) plus `mining-bs-ms-combined` (`combines` mining-bs and mining-ms), `cs-ms-non-thesis-project-track` (30 credits: core, 6-credit CSCI700 project, 18-credit electives) plus `cs-bs-ms-combined`. Both master's programs in a combined degree cap double-counted credits at 6, the real Mines combined-program policy (not the sample fixture's 12). Two simplifications are written down in Notes and decisions above. 42 tests passing (4 new); loaded cleanly against the real `data/` directory alongside Abdallah's minors/ASIs/forms data (69 programs total). Pending push/PR.
- 2026-11-21: Re-opened as PR #21: the original PR #17 merged into `backend/transcript-upload-endpoint` after that branch had already been merged into `main` via PR #16, so the graduate program data never actually reached `main` despite showing "Merged" on GitHub. Re-applied cleanly onto current `main` with no conflicts. Both combined programs (`mining-bs-ms-combined`, `cs-bs-ms-combined`) correctly warn in `get_program_requirements` that their bachelor's components aren't loaded yet (Samantha's Bachelor's data); documented as an expected, temporary warning in `test_program_every_real_program_is_clean`. 491 tests passing.
- 2026-11-21: Fixed BUG-034: `create_plan`/`update_plan` (`POST /plans`, `PUT /plans/{plan_id}`) now run `check_plan` before saving, so `flags`/`summary` are always backend-computed, never trusted from the client; this closes the same override-forging path BUG-024/032 closed for `POST /plans/check`, just reachable through the plan store instead. `check_plan` itself needed to stop crashing on a program or `combines` component that isn't loaded yet (uncaught `NotFoundError`, same treatment as an unknown course). Also marked BUG-024 and BUG-032 Fixed in `bugs.txt` (done in PR #19, never updated there). 490 tests passing (3 new). Pending push/PR.
- 2026-11-21: Graduate data expanded past the five examples (user's explicit call, past the original scope and the plan's own cut-first order): converted all 31 remaining graduate department PDFs in `data/Graduate Programs/` (51 more master's/PhD programs, 56 total in `data/json/graduate-programs.json`), using 6 parallel sub-agents against the schema and conventions the first 5 programs established, then merged and validated together. Caught and fixed along the way: two course codes that didn't exist in the catalog (`CCUS598`, `SPRS598B` -> `SPRS598`); one `choose_credits` group with `credits_required: 0` that `get_program_requirements` correctly flagged as bad data (Civil/Environmental Engineering PhD's either/or 0-credit seminar, removed rather than force-fit); confirmed "Engineering, Design and Society" needs no separate entry (it's the same program as `humanitarian-engineering-ms`, already converted, not a second missing department). Also used the PR #20 schema additions to mark the three PR #18 open questions (credit ranges, grade minimums, OR corequisites) resolved in `data/CONFLICT-LOG.md`, even though the underlying `courses.json` values aren't individually backfilled. Decisions and skips (standalone certificates out of scope, tracks collapsed into one group same as `ee-ms`, a few departments' secondary tracks/degrees skipped for time) are written up in `data/CONFLICT-LOG.md`'s new "Graduate program data" section. 496 tests passing (6 new/updated); loads cleanly against the real `data/` directory (120 programs total). Pending push/PR.
