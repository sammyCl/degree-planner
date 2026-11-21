---
name: session-summary
description: End-of-session summary for the Group 9 degree planner. Writes a private markdown file in summaries/<person>/ recording what was done in this Claude Code session (files, commits, tests) and the choices that came up, drafted in the DECISIONS.md template shape so the person can copy them into DECISIONS.md themselves. Never edits DECISIONS.md. Use for "summarize this session", "session summary", "write up what we did", "what did we decide today", or "/session-summary".
argument-hint: "[member name, e.g. Midhat]"
---

# Session summary - a private record of one session, for filling in DECISIONS.md

This skill writes one summary file for the session that is running now.
Its purpose is to catch the choices made while working, with the options and reasons the person actually gave, before they are forgotten, so the team can later write real `DECISIONS.md` entries from them.
It writes only inside `summaries/`, which is gitignored, and never touches `DECISIONS.md`, `EVAL.md`, or the plans.

## 1. Work out who the summary is for

1. If an argument was given, match it to a member by first name, full name, or part (frontend, backend, agent).
2. Otherwise run `git config user.name` and match it:

   | git user.name | Member | Folder | Part |
   |---|---|---|---|
   | Samantha Clapp, sammyCl | Samantha Clapp | `summaries/samantha/` | Agent, tools, chatbot logic, evaluation |
   | Midhat Sajad, midhatsajad | Midhat Sajad | `summaries/midhat/` | Backend, data format, validator |
   | Abdallah Salhi, Abdallah-Salhi | Abdallah Salhi | `summaries/abdallah/` | Frontend |

3. If nothing matches, ask the person which member they are. Never guess.

If the owner table in `CLAUDE.md` has changed, go by `CLAUDE.md` rather than this table.

## 2. Gather what happened

The main source is this conversation itself: what the person asked for, what was built, what was tried and dropped, and what they said about why.
Back it up with read-only evidence from the repository:

1. `date +%Y-%m-%d` for today's date. Never assume it.
2. `git branch --show-current` for the branch.
3. `git log --since=<today> --format='%h %an %s'` on the current branch, and keep only commits made in this session.
4. `git status -s` and `git diff --stat` for changes not committed yet.
5. Any test or lint commands run in this session, with their actual results (for example "pytest: 42 passed, 1 failed in `test_agent_tools.py`"). Do not rerun them just for the summary.

Read `plans/*.md` only to match the work to task names, so the summary can name the task it advanced.

## 3. Write the file

1. `mkdir -p summaries/<folder>`.
2. Name the file `summaries/<folder>/<YYYY-MM-DD>-<short-slug>.md`, where the slug is two to four lowercase words about the session, joined with hyphens (for example `2026-11-19-get-forms-tool.md`). If that name exists, add `-2`, `-3`, and so on. Never overwrite an earlier summary.
3. Use this layout:

```markdown
# <Short title of the session>

- Date: <YYYY-MM-DD>
- Person: <full name> (<part>)
- Branch: <branch>
- Plan tasks touched: <task names from plans/*.md, or "none matched">

## Goal

<One or two sentences: what the person set out to do.>

## What was done

- <Change, with file paths>
- Commits: <hash and message, or "none yet">
- Not committed yet: <files, or "nothing">
- Tests and checks: <command and actual result, or "none run">

## Choices made

### <Short title of the choice>

- Worth a DECISIONS.md entry: <yes / probably not, with a half-sentence reason>
- Decision: <what was chosen>
- Options considered: <the alternatives that came up>
- Why: <the reason the person gave>
- Source: <"said by <name>", "Claude suggested, <name> agreed", or "shown by the code">

## Problems and dead ends

- <What did not work and what was done about it, or "none">

## Open questions and next steps

- <Unanswered questions, and the next task from the plans if one was named>
```

4. Under "Choices made", include every real choice between options: a library, a data shape, a tool's inputs, a prompt wording, what to cut, how to handle an edge case. Leave out routine steps that had only one sensible way.
5. If no choices came up, write "No choices between options came up in this session." rather than inventing one.

## 4. Report in chat

Say where the file is, list the choice titles marked "yes" in one sentence, and invite the person to copy any of them into `DECISIONS.md` themselves, filling in whatever is still `<fill in>`.

## Rules

- Never edit `DECISIONS.md`, `EVAL.md`, `README.md`, or any plan, and never tick a box. Writing the team's judgments is the team's job, per `CLAUDE.md`.
- Never invent options, reasons, results, numbers, or costs. If the person did not say why, write `<fill in>` in that field.
- Keep Claude's reasoning separate from the person's. When Claude proposed something and the person just accepted it, say so in Source, so the team knows the "why" still needs their own words.
- No keys, tokens, `.env` contents, or real student transcript data in a summary, even though the folder is private.
- Do not commit, stage, or push anything; `summaries/` is gitignored on purpose. If `git status` shows a summary file as untracked, stop and tell the person the `.gitignore` line is missing.
- Write in complete sentences where there is prose, and never use the em dash.
