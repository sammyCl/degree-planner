# degree-planner

This is Group 9's P4 project (the full-stack agent project) for CSCI 498E/598E at Colorado School of Mines: a degree planner for Mines students covering bachelor's, master's, combined BS+MS, minors, and ASIs.
The brief is `projects/p4-full-stack-agent/README.md` in the course repository; `README.md` here summarizes our proposal.
The repository is public on GitHub, so nothing private (keys, real student transcripts) is ever committed.

## Architecture

- Frontend (web UI): a setup page (degree level, major, minor/ASI, transcript upload, number of semesters) and a planner page (flowchart with prerequisite arrows, drag and drop, chatbot panel, plan download).
- Backend API: request router, transcript parser, plan validator (rules code, no LLM), plan store, and the data-loading pipeline.
- Agent: Sonnet 5.5 in a plan, check, revise loop, with the tools `search_catalog`, `get_prerequisites`, `get_program_requirements`, `get_forms`, and `check_plan` (which calls the backend's validator).
- Data layer: the course catalog, forms and policies, and program rules (BS/MS/minor/ASI/combined), filled by a scheduled scraper of the Mines online catalog and department pages.

## Stack

Python 3.12, managed with `uv`. FastAPI for the API (Pydantic models double as the data format schema). SQLite for storage.

## Commands

Backend (run from `backend/`):
- Install: `uv sync`
- Run the API: `uv run uvicorn degree_planner_backend.main:app --reload`
- Test: `uv run pytest`

Frontend (run from `frontend/`; Node 20 or newer; React + Vite + TypeScript):
- Install: `npm install`
- Run the dev server: `npm run dev` (http://localhost:5173; `/api/*` is proxied to the FastAPI backend at 127.0.0.1:8000 with the `/api` prefix removed)
- Test: `npm test`
- Type check and build: `npm run build`
- Lint: `npm run lint`

## Who owns what

| Part | Owner |
|---|---|
| Frontend | Abdallah Salhi |
| Backend, data format, validator | Midhat Sajad |
| Agent, tools, chatbot logic, evaluation | Samantha Clapp |
| Data collection | All three (bachelor's: Samantha; graduate and combined: Midhat; minors, ASIs, forms: Abdallah) |

Before changing code, ask whose part the change touches, and mention it in the commit message.
Collected data follows the format the backend owner sets.

## What Claude does and does not write

- Claude builds code and tests when asked, one step at a time, and says what it changed and why.
- Claude does not write the team's judgments in `DECISIONS.md` or `EVAL.md`, invent eval results or costs, or fill in placeholders the proposal does not answer; the team writes those.

## Git

We merge straight to `main` instead of opening pull requests. The team agreed because we mostly work in different areas, and waiting on manual PR merges left people building on stale code. Claude does the safety checks that a PR review would have done.

- Work on a branch per task and commit there; never commit directly on `main`.
- **When the user asks to push, merge, or ship** (their request is the permission; do not push `main` otherwise):
  1. Commit everything on the branch, then `git fetch origin`.
  2. Check the branch merges cleanly into `origin/main` (`git merge-tree --write-tree origin/main <branch>`). If there are conflicts, stop and show them to the user; never resolve them silently and never push.
  3. Run the checks for the parts the change touches, and stop on any failure: backend `uv run pytest` (from `backend/`); frontend `npm test`, `npm run build` and `npm run lint` (from `frontend/`); data tools `uv run pytest ../data/tools`; for changes under `data/`, `uv run load-data ../data` must report no errors.
  4. `git checkout main`, `git pull --ff-only`, `git merge --no-ff <branch>`, then `git push origin main`. If the push is rejected because someone pushed first, fetch and repeat from step 2.
  5. Branch cleanup after a successful merge, for the branch that was just merged: Abdallah's is deleted automatically (locally and on the remote); for Midhat and Samantha, ask first. Never delete another member's branch.
- If the change touches another member's part (see the table above), tell the user to message that owner before merging. Open a pull request only if the user asks for one.
- Never force-push. Do not push other branches unless the user wants a backup.
- Keep `.env` and secrets out of git (`.gitignore` covers `.env`).

## Plans and tracking

- `plans/MASTER-PLAN.md` is the overall plan; `plans/FRONTEND-PLAN.md`, `plans/BACKEND-PLAN.md`, and `plans/AGENT-PLAN.md` are each member's plan, with task names, dependencies (Needs), priorities, and status boxes.
- When asked what to work on next or what someone is waiting on, read all four plans, find unchecked tasks whose Needs are done, and name the owner of any task that blocks another person's work.
- Tick a box only when the team member says it is done or the code and tests show it, and add a line to that plan's status log.
- If `/team-status` is not available in your session (skills are only loaded when a session starts), read `.claude/skills/team-status/SKILL.md` and follow it by hand.
