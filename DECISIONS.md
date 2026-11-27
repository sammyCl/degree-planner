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

### Transcripts: Mines layout read by rules, other layouts by Claude

- Date: 2026-11-26
- Owner: Abdallah Salhi (frontend)
- Decision: Mines transcripts are read by rules on our backend; other schools' transcripts are read by Claude with personal details removed. A Mines PDF goes to Claude (also redacted) only if the rules read fewer than 3 courses from it.
- Options considered: Sending every transcript to Claude (including Mines transcripts), parsing all transcripts locally, or having students type every course in by hand.
- Why: Mines transcripts follow a known local format that can be parsed deterministically without sending them to Claude, while external transcripts vary widely in layout and benefit from LLM extraction. Stripping personal details first reduces privacy exposure when sending external files to Claude.

### Transfer equivalents: Claude suggests from a shortlist, the student accepts

- Date: 2026-11-26
- Owner: Abdallah Salhi (frontend)
- Decision: Claude suggests transfer equivalents from a shortlist, and the student accepts them.
- Options considered: Auto-applying transfer credits without review, Claude inventing course equivalents freely from scratch, or forcing students to look up and match every transfer course manually.
- Why: Constraining Claude to a shortlist keeps suggestions grounded in valid catalog/equivalency options, while requiring student acceptance prevents silent errors on degree requirements and keeps the student in control.

### Summer terms switch on automatically, and only used summers show

- Date: 2026-11-26
- Owner: Abdallah Salhi (frontend)
- Decision: Summer terms switch on automatically for degrees that need a summer course, and the planner shows only the summers that have a course.
- Options considered: Showing empty summer columns for every year by default, requiring a manual toggle before any summer term appears, or omitting summer terms completely.
- Why: Automatically revealing a summer term when used reduces clicks and captures non-standard pacing, while hiding unused summers keeps the standard academic-year grid clean and uncluttered.

### One entry per major, with a track picker

- Date: 2026-11-26
- Owner: Abdallah Salhi (frontend)
- Decision: The setup page lists each major once, with a track picker.
- Options considered: Listing every major-plus-track combination as a separate top-level major entry, or treating tracks as free-text notes rather than structured options.
- Why: Grouping tracks under a single major entry keeps major selection clean and scannable while still letting students pick a specialization that shapes course or requirement rules.

### Plan download is a PDF (for now; not built yet)

- Date: 2026-11-26
- Owner: Abdallah Salhi (frontend)
- Decision: The plan download will be a PDF.
- Options considered: Exporting only JSON/CSV, printing directly from the browser stylesheet, building a shareable web link first, or delaying export planning altogether.
- Why: A PDF gives students a portable, advisor-friendly snapshot of their plan in a familiar format, while keeping it as a planned scope item avoids spending build time on export formatting before core planning flows settle.

### Validation strictness: reject or clean malformed data at load, don't just warn about it later

- Date: 2026-11-25
- Owner: Midhat Sajad (backend, data format), agreed with Samantha Clapp (agent tools)
- Decision: Genuinely malformed data (NaN/infinite/negative numbers, an empty required list, a prompt-injection-shaped catalog year, a prerequisite/corequisite referencing a course code that doesn't exist and has no safe alternative) is rejected at load, or cleaned to a safe value, instead of loading successfully with a tool-side `data_warning`. A value kept as literal, uncorrected text stays that way only when correcting it would mean guessing (a catalog typo like `CSC128` with no single obvious fix); a dead reference with no safe fallback becomes an overridable `exception` instead, so it's visible and actionable rather than a silent permanent failure.
- Options considered: Keep the agent tool's existing leniency (load anything, add a warning the agent reads) vs. move the check to the data format itself, so every consumer (validator, frontend, future tools, not just today's agent tool) gets the same guarantee.
- Why: The stricter checks were first tried back when models.py/plan_models.py were built, then held back after they collided with the agent tool's existing lenient behavior and its tests (bugs.txt BUG-010, 014, 017, 022, 023(a), 026(c), 028). Raised to Samantha directly rather than guessed at; she agreed none of these are legitimate cases, only broken ones, so rejecting or cleaning them at load is strictly better than relying on every future consumer to re-implement the same tool-side warning. The same principle later caught BUG-050 (most "code not in the catalog" prerequisite references were a dead end, not an overridable exception), but was applied carefully there: the 21 cases with a working OR fallback are left untouched, since converting those too would make the validator always flag them (BUG-026(d)) even though nothing is actually wrong with the plan.

### Frontend: React, Vite and TypeScript

- Date: 2026-11-17
- Owner: Abdallah Salhi (frontend)
- Decision: The frontend uses React, Vite and TypeScript.
- Options considered: Plain JavaScript with React, a full-stack framework like Next.js, or another frontend framework such as Vue or Svelte.
- Why: TypeScript catches state and data-model bugs early in a rule-heavy degree planner, React fits interactive schedule and requirement state well, and Vite keeps local development and builds fast for a client-focused frontend.

### Stack: Python 3.12, uv, FastAPI, SQLite

- Date: 2026-11-13
- Owner: Midhat Sajad (backend)
- Decision: Python 3.12, `uv` for env and dependency management, FastAPI for the API, SQLite for storage.
- Options considered: Package manager: `uv` vs Poetry vs pip+venv. Framework: FastAPI vs Flask vs Django. Database: SQLite vs Postgres vs flat JSON files.
- Why:  We picked uv for one fast tool covering env, deps, and the lockfile across three people's machines. We picked FastAPI because Pydantic models let us define the course/program schema once and reuse it for API validation and the Data format doc, instead of three separate definitions; its auto-generated docs also help since the team build against our API before it's finished. We picked SQLite because the data loader rebuilds the catalog from scratch each run, and a single file is trivial to wipe and reload, with no server or secrets to manage at this scale.

### Data format: structured AND/OR requirement trees, not free text

- Date: 2026-11-13
- Owner: Midhat Sajad (backend)
- Decision: Prerequisites and corequisites are a typed `Requirement` tree (`course`, `AND`, `OR`, `exception`), not the plain-text strings the raw catalog CSVs store (e.g. `"MATH301, MATH332."`).
- Options considered: Keep prerequisites as free text and have the agent or validator parse/interpret it at plan-check time, vs. parse it once into structured AND/OR logic at load time.
- Why: The validator needs a deterministic, repeatable answer to "is this prerequisite satisfied," the same requirement the team picked rules code over an LLM for; parsing free text at check time would reintroduce exactly the ambiguity that was being avoided. Parsing once, at load, means the validator, the agent's tools, and the frontend all read the same structure instead of three independent text-parsers potentially disagreeing. An `exception` type (for instructor consent, placement, or a catalog reference that can't be resolved) keeps anything the parser can't turn into real logic from being silently dropped or guessed at — it surfaces as a warning the student can override, rather than either a hallucinated interpretation or a dead, permanently-failing requirement (see bugs.txt BUG-050).

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
- Options considered:  Let the LLM check the plan itself vs. write the validator as plain rules code (prerequisites, credit totals, requirement overlap, transfer credits).
- Why:  An LLM check can miss or hallucinate a broken prerequisite and give a different answer on the same plan twice. Rules code gives one deterministic answer, and both the frontend's drag-and-drop flag and the agent's check_plan tool can call the exact same function.

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
