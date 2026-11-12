# Decisions

The judgment calls behind this project and why we made them, newest first.
Add an entry whenever the team picks between real options; copy the template below.

## Template

### <short title of the decision>

- Date: <YYYY-MM-DD>
- Owner: <who made or owns this call>
- Decision: <what we chose>
- Options considered: <the alternatives>
- Why: <the reason, and what evidence it rests on>

## Entries

The first entries are the decisions recorded in our proposal (submitted Fri Nov 6, 2026).

### What to cut first if we run short

- Date: 2026-11-06
- Owner: Team
- Decision: If catalog data is messy or hard to get, cut minors, ASIs/certifications, and PhDs first. If prerequisite exceptions (placement, instructor approval) are invisible to the agent, show a warning and let the user override, and handle fewer exceptions by returning errors. If scope creep (UI polish, master's programs) eats the time, cut the chatbot first.
- Options considered: <fill in>
- Why: These are our three biggest risks; the cuts protect the core plan-building path.

### Data from the scraped catalog, refreshed on a schedule

- Date: 2026-11-06
- Owner: Team
- Decision: Use scraped or exported course catalog and program requirement pages, refreshed on a schedule, and possibly give the agent the pages directly so it has the latest information. The user approves or edits every plan.
- Options considered: <fill in>
- Why: <fill in>

### Plan validator is rules code, not the model

- Date: 2026-11-06
- Owner: Midhat Sajad (backend)
- Decision: The plan validator (prerequisites, credits, requirement overlap) is plain rules code with no LLM, used both by the frontend's broken-prerequisite flags and by the agent's `check_plan` tool.
- Options considered: <fill in>
- Why: <fill in>

### Model: Sonnet 5.5

- Date: 2026-11-06
- Owner: Samantha Clapp (agent)
- Decision: The agent runs on Sonnet 5.5, with the tools `search_catalog`, `get_prerequisites`, `get_program_requirements`, `check_plan`, and `get_forms`.
- Options considered: <fill in>
- Why: <fill in>

### An agent, not a fixed workflow

- Date: 2026-11-06
- Owner: Team
- Decision: Build an agent that plans, checks, and revises.
- Options considered: A fixed workflow with rules written in advance.
- Why: The agent has to decide at run time which programs and catalog years are needed, which requirements overlap between a major and a minor, and what to do when a plan fails the check. Students' plans and exceptions vary too much for rules written in advance.
