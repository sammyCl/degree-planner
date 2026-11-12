# Frontend Plan: Abdallah Salhi

Part: setup page, planner page, flowchart with prerequisite arrows, drag and drop, transcript upload, plan download, chatbot panel (UI side). Also data slice D3: minors, ASIs, certifications, Independent Study and other forms, policies.

Master plan: [MASTER-PLAN.md](MASTER-PLAN.md). Status marks, priorities and how Claude uses this file are explained there.

## Done means (from the proposal)

- Filling in the setup form shows a flowchart.
- Dragging a course to another semester shows a broken-prerequisite flag.
- A transcript can be uploaded and the finished plan downloaded.

## Waiting on others

| I need | From | For | Needed by |
|---|---|---|---|
| Plan JSON format (semesters, courses, prerequisite edges, flags) | Midhat B2 | F3, F4 | Nov 13 |
| Common data format | Midhat B1 | D3 | Nov 13 |
| API endpoints: submit setup, check a move | Midhat B7 | F6, F7 | Nov 18 |
| Validator flag format | Midhat B6 | F7 | Nov 18 |
| Transcript upload endpoint | Midhat B8 | F8 | Nov 19 |
| Chat endpoint and reply format | Samantha A5 | F9 | Nov 19 |

Until B2 and B7 land, build against a hand-written sample plan JSON (F2) so nothing blocks.

## Tasks

### Week 1: Nov 9-13 (foundations)

| ID | Task | Priority | Due | Needs | Status |
|---|---|---|---|---|---|
| F1 | UI mockup of both pages (setup, planner with chat panel) and review with team | P0 | Nov 13 | | [ ] |
| F2 | Sample plan JSON (one degree, a few semesters, a deliberate broken prerequisite) to develop against; swap for the real format once B2 exists | P0 | Nov 13 | | [ ] |
| D3a | Data: list which minors, ASIs, certifications and forms are needed for the five examples (CS minor, Geophysical Engineering minor, Independent Study Credit form, Thorson's honors program notes) | P0 | Nov 13 | M2 | [ ] |
| M1 | Join the stack decision (frontend framework, how it talks to the backend) | P0 | Nov 13 | | [ ] |

### Week 2: Nov 16-20 (first end-to-end)

| ID | Task | Priority | Due | Needs | Status |
|---|---|---|---|---|---|
| D3b | Data: collect the minors/ASIs/forms for the five examples into the agreed format | P0 | Nov 18 | B1, D3a | [ ] |
| F3 | Project scaffold in the repo, running locally, with run command added to CLAUDE.md and README | P0 | Nov 16 | M1 | [ ] |
| F4 | Page 1, setup form: degree level, major, optional minor/ASI, start year, number of semesters; validates inputs | P0 | Nov 17 | F3 | [ ] |
| F5 | Page 2, planner: semester columns with course boxes (title, credits, description), electives shown, prerequisite arrows, rendering from sample plan JSON | P0 | Nov 18 | F2, F3 | [ ] |
| F6 | Wire setup form to the backend and draw the returned plan | P0 | Nov 19 | F4, F5, B2, B7 | [ ] |
| F7 | Drag and drop: move a course to another semester, call the validator, show a broken-prerequisite flag on the course | P1 | Nov 20 | F5, B6, B7 | [ ] |
| F8 | Transcript/completed-courses upload on the setup page, wired to the backend; shows parsed courses so the student can correct them | P1 | Nov 20 | F4, B8 | [ ] |
| F9 | Chatbot panel UI: message list, input, shows agent replies and applies plan changes it returns | P2 | Nov 20 | F6, A5 | [ ] |
| F10 | Plan download (file format chosen with team, e.g. PDF or JSON) | P1 | Nov 20 | F5 | [ ] |
| M6 | Integration day (Nov 20): setup -> plan drawn for Example 1 | P0 | Nov 20 | F6 | [ ] |

### Week 3: Nov 23-25 (user trial)

| ID | Task | Priority | Due | Needs | Status |
|---|---|---|---|---|---|
| F11 | Get the UI ready for the user trial: clear errors, loading state while the agent works, nothing that crashes on bad input | P0 | Nov 23 | M6 | [ ] |
| F12 | Watch the user trial (Nov 24), note every point where they got confused | P0 | Nov 24 | F11, M7 | [ ] |
| F13 | Turn the user's feedback into fixes for the UI and add them below | P0 | Nov 25 | F12 | [ ] |
| D3c | Spot-check five random courses/requirements from a teammate's slice against the Mines catalog (done-means for data) | P1 | Nov 25 | D1 or D2 | [ ] |

### Week 4: Nov 30 - Dec 3 (finish)

| ID | Task | Priority | Due | Needs | Status |
|---|---|---|---|---|---|
| F14 | Fix remaining UI problems from the user trial | P0 | Dec 1 | F13 | [ ] |
| F15 | Draft DECISIONS.md entries for frontend choices (framework, flowchart library, download format). Team writes the judgments; Claude does not | P1 | Dec 1 | | [ ] |
| F16 | Threat-model input from the UI side: what the user can upload, what is displayed back (untrusted text from transcripts and agent replies, escaping) | P1 | Dec 2 | M9 | [ ] |
| F17 | Write my section of the README and prepare my part of the presentation and likely questions | P0 | Dec 2 | | [ ] |
| M13 | Demo recording (UI driven by me) | P0 | Dec 2 | M6 | [ ] |

## If I run short, cut in this order

1. F9 chatbot panel (needs A5 anyway)
2. F7 drag and drop (the proposal ranks it second to cut)
3. F8 transcript upload, replaced by a typed list of completed courses
4. F10 download

Never cut F4, F5, F6: they are the core path.

## Notes and decisions

- (none yet)

## Status log

- 2026-11-12: Plan created. Nothing started.
