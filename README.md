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

## Demo

<link to the recorded demo>

## More

- [DECISIONS.md](DECISIONS.md): the judgment calls and why
- [EVAL.md](EVAL.md): the claim, the numbers, the cost, and the threat model
