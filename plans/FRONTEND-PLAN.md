# Frontend Plan: Abdallah Salhi

Part: setup page, planner page, flowchart with prerequisite arrows, drag and drop, transcript upload, plan download, chatbot panel (UI side). Also data slice Minors data: minors, ASIs, certifications, Independent Study and other forms, policies.

Master plan: [MASTER-PLAN.md](MASTER-PLAN.md). Status marks, priorities and how Claude uses this file are explained there.

## Done means (from the proposal)

- Filling in the setup form shows a flowchart.
- Dragging a course to another semester shows a broken-prerequisite flag.
- A transcript can be uploaded and the finished plan downloaded.

## Waiting on others

| I need | From | For | Needed by |
|---|---|---|---|
| Plan JSON format (semesters, courses, prerequisite edges, flags) | Midhat Plan format | Frontend scaffold, Setup page | Nov 13 |
| Common data format | Midhat Data format | Minors data | Nov 13 |
| API endpoints: submit setup, check a move | Midhat API endpoints | Connect setup to backend, Drag and drop | Nov 18 |
| Validator flag format | Midhat Plan validator | Drag and drop | Nov 18 |
| Transcript upload endpoint | Midhat Transcript parser | Transcript upload | Nov 19 |
| Chat endpoint and reply format | Samantha Chat logic | Chatbot panel | Nov 19 |

Until Plan format and API endpoints land, build against a hand-written sample plan JSON (Sample plan) so nothing blocks.

## Tasks

### Week 1: Nov 9-13 (foundations)

| Name | Task | Priority | Due | Needs | Status |
|---|---|---|---|---|---|
| UI mockup | UI mockup of both pages (setup, planner with chat panel) and review with team | P0 | Nov 13 | | [x] |
| Sample plan | Sample plan JSON (one degree, a few semesters, a deliberate broken prerequisite) to develop against; swap for the real format once Plan format exists | P0 | Nov 13 | | [x] |
| Minors list | Data: list which minors, ASIs, certifications and forms are needed for the five examples (CS minor, Geophysical Engineering minor, Independent Study Credit form, Thorson's honors program notes) | P0 | Nov 13 | Five examples | [x] |
| Stack decision | Join the stack decision (frontend framework, how it talks to the backend) | P0 | Nov 13 | | [x] |

### Week 2: Nov 16-20 (first end-to-end)

| Name | Task | Priority | Due | Needs | Status |
|---|---|---|---|---|---|
| Minors data | Data: collect the minors/ASIs/forms for the five examples into the agreed format | P0 | Nov 18 | Data format, Minors list | [x] |
| Frontend scaffold | Project scaffold in the repo, running locally, with run command added to CLAUDE.md and README | P0 | Nov 16 | Stack decision | [x] |
| Setup page | Page 1, setup form: degree level, major, optional minor/ASI, start year, number of semesters; validates inputs | P0 | Nov 17 | Frontend scaffold | [x] |
| Planner page | Page 2, planner: semester columns with course boxes (title, credits, description), electives shown, prerequisite arrows, rendering from sample plan JSON | P0 | Nov 18 | Sample plan, Frontend scaffold | [ ] |
| Connect setup to backend | Wire setup form to the backend and draw the returned plan | P0 | Nov 19 | Setup page, Planner page, Plan format, API endpoints | [x] |
| Drag and drop | Drag and drop: move a course to another semester, call the validator, show a broken-prerequisite flag on the course | P1 | Nov 20 | Planner page, Plan validator, API endpoints | [ ] |
| Transcript upload | Transcript/completed-courses upload on the setup page, wired to the backend; shows parsed courses so the student can correct them | P1 | Nov 20 | Setup page, Transcript parser | [ ] |
| Chatbot panel | Chatbot panel UI: message list, input, shows agent replies and applies plan changes it returns | P2 | Nov 20 | Connect setup to backend, Chat logic | [ ] |
| Plan download | Plan download (file format chosen with team, e.g. PDF or JSON) | P1 | Nov 20 | Planner page | [ ] |
| Integration day | Integration day (Nov 20): setup -> plan drawn for Example 1 | P0 | Nov 20 | Connect setup to backend | [ ] |

### Week 3: Nov 23-25 (user trial)

| Name | Task | Priority | Due | Needs | Status |
|---|---|---|---|---|---|
| Trial-ready UI | Get the UI ready for the user trial: clear errors, loading state while the agent works, nothing that crashes on bad input | P0 | Nov 23 | Integration day | [ ] |
| Frontend trial notes | Watch the user trial (Nov 24), note every point where they got confused | P0 | Nov 24 | Trial-ready UI, User trial | [ ] |
| UI feedback fixes | Turn the user's feedback into fixes for the UI and add them below | P0 | Nov 25 | Frontend trial notes | [ ] |
| Spot-check (Abdallah) | Spot-check five random courses/requirements from a teammate's slice against the Mines catalog (done-means for data) | P1 | Nov 25 | Bachelor's data or Graduate data | [ ] |

### Week 4: Nov 30 - Dec 3 (finish)

| Name | Task | Priority | Due | Needs | Status |
|---|---|---|---|---|---|
| Final UI fixes | Fix remaining UI problems from the user trial | P0 | Dec 1 | UI feedback fixes | [ ] |
| Frontend decisions | Draft DECISIONS.md entries for frontend choices (framework, flowchart library, download format). Team writes the judgments; Claude does not | P1 | Dec 1 | | [ ] |
| UI threat model | Threat-model input from the UI side: what the user can upload, what is displayed back (untrusted text from transcripts and agent replies, escaping) | P1 | Dec 2 | Threat model | [ ] |
| Frontend write-up | Write my section of the README and prepare my part of the presentation and likely questions | P0 | Dec 2 | | [ ] |
| Demo recording | Demo recording (UI driven by me) | P0 | Dec 2 | Integration day | [ ] |

## If I run short, cut in this order

1. Chatbot panel chatbot panel (needs Chat logic anyway)
2. Drag and drop drag and drop (the proposal ranks it second to cut)
3. Transcript upload transcript upload, replaced by a typed list of completed courses
4. Plan download download

Never cut Setup page, Planner page, Connect setup to backend: they are the core path.

## Notes and decisions

- (none yet)

## Status log

- 2026-11-12: Plan created. Nothing started.
- 2026-11-17: Minors list and Minors data done (Abdallah says done; data and tests show it). Minors, ASIs, forms and policies collected under data/ and converted to JSON (data/json/); conflicts and decisions in data/CONFLICT-LOG.md. Open: ASIs are from the 2025-2026 catalog, confirm for 2026-2027; course codes missing from the CSV for Samantha to check.
- 2026-11-17: Frontend scaffold done (code and tests show it): Vite + React + TypeScript in frontend/, /api proxied to the FastAPI backend, 2 passing tests, run commands in CLAUDE.md and README.md. Checked against Midhat's backend /health through the proxy.
- 2026-11-19: Sample plan done (code and tests show it): frontend/src/samplePlan.json in Midhat's plan format (8 semesters of CS BS, real catalog courses, prerequisite edges, 3 deliberate flags), typed in src/types.ts, 5 integrity tests. Note: docs/plan-format.sample.json has wrong titles for CSCI306 and CSCI400 (catalog: Software Engineering, Principles of Programming Languages) for Midhat to fix.
- 2026-11-19: UI mockup done and merged to main (PR #13, you said it is done): docs/ui-mockup.html, static mockup of the setup page and planner page with a scripted chat panel. Team review is by the PR; layout, wording and colors can still change. Real chat replies need Samantha's Chat logic endpoint.
- 2026-11-22: Stack decision ticked (Midhat ticked it in the master plan on Nov 13; Abdallah confirmed). Bachelor's data and Agent loop ticked in the agent plan (Abdallah confirmed; code and data are on main: PR #24 bachelor's programs, PRs #14 and #27 agent tools and loop).
- 2026-11-22: Setup page done (code and tests show it): frontend/src/setup/ has the form (degree level, program, minors/ASIs picker, starting term, include summers, number of semesters), validation against the backend's limits (1 to 18, 1 to 15 for master's), a live "plan at a glance" with projected graduation, and the request in the POST /plans/submit-setup format. Program list comes from frontend/src/setup/programOptions.json, built from data/json/ by data/tools/build_frontend_options.py (no list endpoint exists). 28 frontend tests pass. Not done: sending the request (Connect setup to backend), transcript/completed courses (Transcript upload), PhD programs (left out of scope). Only 5 bachelor's programs have data so far.
- 2026-11-22: Remaining bachelor's majors converted (Abdallah, asked by Abdallah after Samantha's first five covered only the examples): all 21 bachelor's PDFs are now 44 programs in data/json/bachelors.json (tracks, emphases and focus areas as separate programs), built by data/tools/build_bachelors_json.py. Every program's credits add up to the PDF total except the two QBE programs (CBEN321 is 4.0 in the PDF, 3.0 in the CSV). Decisions and open slots are in data/CONFLICT-LOG.md; two of Samantha's test files had pinned counts updated. The setup page's program list now shows all of them.
- 2026-11-22: Planner page built (code, tests and a browser check show it): frontend/src/planner/ renders a plan as semester columns of course cards with credits per semester, prerequisite arrows (out-of-order ones red and dashed), hover to highlight a course's whole prerequisite chain, click for details (what it needs and unlocks, and its problem), a summary bar with a credit ring and error/warning counts, and a flags list that jumps to the course. It only draws what the plan says (edges and flags come from the backend; the frontend never computes them). After 'Build my plan' it shows the sample plan with a notice, until Connect setup to backend. Not done, so the box stays open: course descriptions (the plan format has no description and the backend has no course endpoint; needs Midhat) and elective placeholders (the sample has none). 51 frontend tests pass.
- 2026-11-24: Connect setup to backend done (code, tests and a real run show it): 'Build my plan' now calls POST /plans/submit-setup (frontend/src/api.ts) and draws the plan the agent returns. A real run through the page, with the live backend and agent, built a valid 8-semester plan (130 of 130 credits, no errors, 3 warnings) in 58 seconds. The page waits on a screen with a clock and a Cancel button (the agent can take up to ten minutes), shows the assistant's explanation, lists its problems when it could not finish (and still draws its last attempt), and explains the failures it can meet: backend not running, assistant not available (503), request rejected (422), no plan at all. The student's form choices are kept when they go back. 75 frontend tests pass. Not yet sent: completed courses (Transcript upload) and exception overrides (the planner page does not let the student accept an exception yet). Cancel stops the page waiting; the backend may still finish that run. Each run uses the machine's Claude Code login. Integration day can now be run: Lookups, API endpoints, Agent loop and Connect setup to backend are all done.
