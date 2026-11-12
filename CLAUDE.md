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

Python. <version, package manager, and web framework, once decided>

## Commands

<install, run, test, and eval commands, added once there is code>

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

- Work on a branch and merge through a pull request; never commit straight to `main`.
- Never force-push, and ask before pushing or opening a pull request.
- Keep `.env` and secrets out of git (`.gitignore` covers `.env`).

## Plans and tracking

- `plans/MASTER-PLAN.md` is the overall plan; `plans/FRONTEND-PLAN.md`, `plans/BACKEND-PLAN.md`, and `plans/AGENT-PLAN.md` are each member's plan, with task IDs, dependencies (Needs), priorities, and status boxes.
- When asked what to work on next or what someone is waiting on, read all four plans, find unchecked tasks whose Needs are done, and name the owner of any task that blocks another person's work.
- Tick a box only when the team member says it is done or the code and tests show it, and add a line to that plan's status log.
