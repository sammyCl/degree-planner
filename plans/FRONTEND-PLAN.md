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
| UI mockup | UI mockup of both pages (setup, planner with chat panel) and review with team | P0 | Nov 13 | | [ ] |
| Sample plan | Sample plan JSON (one degree, a few semesters, a deliberate broken prerequisite) to develop against; swap for the real format once Plan format exists | P0 | Nov 13 | | [ ] |
| Minors list | Data: list which minors, ASIs, certifications and forms are needed for the five examples (CS minor, Geophysical Engineering minor, Independent Study Credit form, Thorson's honors program notes) | P0 | Nov 13 | Five examples | [ ] |
| Stack decision | Join the stack decision (frontend framework, how it talks to the backend) | P0 | Nov 13 | | [ ] |

### Week 2: Nov 16-20 (first end-to-end)

| Name | Task | Priority | Due | Needs | Status |
|---|---|---|---|---|---|
| Minors data | Data: collect the minors/ASIs/forms for the five examples into the agreed format | P0 | Nov 18 | Data format, Minors list | [ ] |
| Frontend scaffold | Project scaffold in the repo, running locally, with run command added to CLAUDE.md and README | P0 | Nov 16 | Stack decision | [ ] |
| Setup page | Page 1, setup form: degree level, major, optional minor/ASI, start year, number of semesters; validates inputs | P0 | Nov 17 | Frontend scaffold | [ ] |
| Planner page | Page 2, planner: semester columns with course boxes (title, credits, description), electives shown, prerequisite arrows, rendering from sample plan JSON | P0 | Nov 18 | Sample plan, Frontend scaffold | [ ] |
| Connect setup to backend | Wire setup form to the backend and draw the returned plan | P0 | Nov 19 | Setup page, Planner page, Plan format, API endpoints | [ ] |
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
