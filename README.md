# degree-planner

A degree planner for Colorado School of Mines students, with integrations for bachelor's degrees, master's degrees, minors, and ASIs (Area of Special Interest). Group 9, P4 for CSCI 498E/598E.

## The user and their problem

Mines publishes recommended flowcharts for most majors, but each flowchart shows only one way through a degree.
If a student wants to take classes in a different order, or do something outside the regular plan such as a minor or transfer credits, the flowchart stops working as a degree plan.
A student who adds a minor or a combined bachelor's and master's has to cross-reference many different websites to plan properly.

From conversations with our users, we expect the planner to be used 1-2 times a semester, mostly early in a degree and around course registration, when students can see which classes are offered next semester.

## What it does

Students build their degree plan in the order that suits them, with all the required information in one place: the courses for each degree, checks that the plan meets the requirements of every degree they want, and the forms a course needs (such as the Independent Study Credit form).

The website has two pages:

1. **Setup.** The student chooses their degree level, major (and optional minor or ASI), uploads their completed courses, and sets how many semesters they want the degree(s) to take.
2. **Planner.** A flowchart of the degree, with the remaining courses, arrows for prerequisites, and a suggested semester-by-semester plan. The student can drag courses to other semesters, and the site flags any broken prerequisites. A chatbot helps edit the plan, for example filling in electives or applying exceptions the student has been granted. The finished plan can be downloaded.

Flow: the frontend sends the student's inputs to the backend, which calls the agent. The agent reads the data through tools and returns a plan, which the frontend draws on the planner page. Each edit (a moved course or a chat message) repeats the loop.

### Why an agent

The agent decides at run time which programs and catalog years are needed, which requirements overlap between a major and a minor, and what to do when a plan fails the check (move a course, swap an elective). Students' situations and exceptions vary too much for rules written in advance, so a fixed workflow would give students fewer options.

## Backend

The backend is a FastAPI app over SQLite (Python 3.12, `uv`); Pydantic models double as both the API's request/response validation and the schema for the common data format ([docs/data-format.md](docs/data-format.md), [docs/plan-format.md](docs/plan-format.md)).

- **Data format and loader.** Courses, programs, and forms are stored in one common JSON shape, built from each data slice's raw source (catalog CSVs, program PDFs) by scripts in `data/tools/`. Prerequisites and corequisites are parsed once, at load, into a typed AND/OR/exception tree rather than kept as free text, so the validator, the agent's tools, and the frontend all read the same structure (see DECISIONS.md, "Data format"). One command (`uv run load-data`) reloads the whole catalog from `data/`, reporting errors per file without aborting the rest of the load. Malformed data (an impossible credit value, an empty required list, a catalog year that isn't a real year, a prerequisite naming a course that doesn't exist and has no safe alternative) is rejected or cleaned at load rather than passed through with a warning attached (DECISIONS.md, "Validation strictness").
- **Plan validator** (`validator.py`) is plain rules code, not the model: prerequisite and corequisite order, a per-semester credit cap, every program's requirement groups (fixed lists, elective credit choices, and rule-based groups), double-counted credits between a combined program or a minor/ASI and the student's degree, and claimed exceptions (shown as an overridable warning, never silently passed). The same `check_plan` function backs the frontend's drag-and-drop check and the agent's `check_plan` tool, so both get one deterministic answer.
- **API** (`main.py`): `POST /plans/check` re-validates a plan (used after a drag-and-drop move); `POST /plans` / `PUT /plans/{plan_id}` / `GET /plans/{plan_id}` are the plan store, always re-running the validator before saving so a client can't forge a passing plan into storage; `POST /plans/submit-setup` and `POST /plans/chat` call the agent loop and chat loop; `POST /transcripts/parse` turns an uploaded `.csv` or `.pdf` transcript into completed courses. Validation errors return 422 without echoing request internals back; an unexpected server error returns one fixed, non-revealing 500 message, with the real exception only in the server log.
- **Tests:** `uv run pytest` from `backend/` (1027 tests); `uv run pytest ../data/tools` for the data-conversion scripts (45 tests).

## Frontend

React, TypeScript and Vite (`frontend/`). It draws what the backend decides: whether a plan is valid is always the validator's answer, never the page's.

- **Setup page.** Degree level, major (with a track picker), minors and ASIs, starting term, summer terms and number of semesters. Completed and transfer courses come from an uploaded `.csv` or `.pdf` transcript, or are typed in, and the student reviews the list before it is used. A course from another school without a Mines match gets a suggested equivalent that counts only after the student accepts it.
- **Planner page.** One column per semester with prerequisite arrows. Courses can be dragged (or moved from their details) to another semester, with undo and redo; every change is sent to `POST /plans/check` and the answer replaces the plan. Completed courses sit in their own columns, and "About this plan" shows the requirement checklist, things to check and the assistant's choices.
- **Alerts.** Validator messages are reworded into short sentences that say what to do (`planner/plainFlags.ts`).
- **Chat assistant.** Suggests changes through `POST /plans/chat`; the board changes only when the student clicks Apply, and Undo takes it back.
- **Forms.** The forms the plan calls for (independent study, minor declaration) with what to do, and the other Registrar forms behind a click (`planner/forms.ts`, checked against the forms data).
- **Downloads.** The plan as a PDF, or the flowchart as a PNG image. Both are made in the browser.
- **Reloads.** The setup and plan are kept for the browser tab (`sessionStorage`) and gone when it is closed.
- **Tests:** `npm test` from `frontend/`.

## Team and who owns what

All three members share data collection; each also owns one part.

| Member | Part they own | Data collection slice |
|---|---|---|
| Abdallah Salhi | Frontend: setup and planner pages, flowchart, drag and drop, transcript upload, plan download, chatbot panel (UI side) | Minors, ASIs, certifications, Independent Study and other forms, policies |
| Midhat Sajad | Backend: API, database and data-loading pipeline, common data format, plan validator, transcript parser | Master's and PhD programs, combined BS+MS rules |
| Samantha Clapp | Agent: the Sonnet 5.5 agent, its tools, chatbot logic for electives and exceptions, evaluation of the five examples | Bachelor's degrees and course catalog entries |

## Schedule

| Week | What happens |
|---|---|
| Nov 9-13 | Finalize examples, set up repo, choose catalog sources, finish data collection |
| Nov 16-20 | Catalog pipeline, first agent tools, basic UI. First end-to-end version by Fri Nov 20 |
| Nov 23-25 | User tries it (target Tue Nov 24). Evaluation of the five examples |
| Nov 30-Dec 3 | Fix issues from the user, cost and security notes, demo recording, README/DECISIONS/EVAL, present |

## How to run it

Requires Python 3.12 and [uv](https://docs.astral.sh/uv/).

Backend (from `backend/`):
```
uv sync
uv run uvicorn degree_planner_backend.main:app --reload
uv run pytest
```

Frontend (from `frontend/`; needs Node 20 or newer):
```
npm install
npm run dev      # http://localhost:5173, forwards /api to the backend on port 8000
npm test
npm run build
```

## Demo

<link to the recorded demo>

## More

- [DECISIONS.md](DECISIONS.md): the judgment calls and why
- [EVAL.md](EVAL.md): the claim, the numbers, the cost, and the threat model
