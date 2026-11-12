---
name: team-status
description: Progress check for the Group 9 degree planner. Reads every plan in plans/ as it stands today, compares the status marks with what the repo shows (commits, files, pull requests), and reports in chat where the team is, what each member can do next, who is waiting on whom, and which boxes look wrong. Changes no files. Use for "team status", "progress check", "where are we", "are we on track", "what is everyone working on", "what am I waiting on", "what should I work on next", or "/team-status".
argument-hint: "[member name or part, e.g. Midhat or backend]"
---

# Team status - a progress check from the plans and the repo

This skill gives the team a progress update.
It reads the plans fresh every time, because they change: never rely on task IDs, owners, dates, or file names remembered from an earlier run or written in this file as examples.
It is read-only: it reports in chat and never edits a plan, ticks a box, or writes a status log.

## 1. Discover the plans

1. Read `CLAUDE.md` for the team's rules and any documented commands.
2. List and read every `plans/*.md`.
   - The master plan is the file that holds the milestones or timeline and the owner table (today it is `MASTER-PLAN.md`, but go by content, not name).
   - Every other plan file belongs to one member. Take the owner from the file's heading, its "Part:" line, or the master plan's owner table.
3. From the master plan, take: the status legend, the priority legend, the milestones with dates, the whole-team tasks, the cross-part dependencies, the critical path, and the cut order.
4. From each member plan, take: the task tables, the "Waiting on others" table, the cut order, and the status log.

If a plan file is missing, new, or shaped differently than expected, work with what is there and say in the report what you could not read. Never fill a gap by guessing.

## 2. Parse the tasks

A task is a row in any markdown table that has an ID column and a status column. Other columns are usually Task, Priority, Due, and Needs, but take whatever is there.

- **Status marks:** use the master plan's legend. If there is none, use `[ ]` not started, `[~]` in progress, `[x]` done, `[!]` blocked.
- **Needs:** a list of task IDs. A Need is met only when that task is `[x]` in its own row.
- **Duplicates:** the same ID can appear in the master plan and in a member plan (a whole-team task listed under one member). Treat it as one task. If the two rows disagree on status, report that as a mismatch.
- **Owner:** the owner of the file the row is in. A row in the master plan's whole-team table belongs to the whole team unless its text names a lead.
- **Due dates:** dates without a year are in the current year of the course, taken from the master plan.

## 3. Get today's date

Run `date +%Y-%m-%d`. Compare every Due date and milestone date with today. Never assume the date.

## 4. Gather evidence from the repo (read-only)

Run these, all read-only:

1. `git fetch --quiet origin` (only updates the remote refs, never your files), then `git status -sb` to see whether the local copy is behind.
2. `git log origin/main --since=<the earliest status-log date in the plans> --format='%h %an %ad %s' --date=short`, and the same for other remote branches (`git branch -r`) to catch work not merged yet.
3. `gh pr list --state all --limit 30` if `gh` is installed and signed in. Skip it quietly otherwise.
4. `git ls-files` for the file tree, and look at `.github/workflows/` if it exists.
5. If `CLAUDE.md` documents a test or eval command, you may run it and report the result. Never guess at commands that are not documented.

Match evidence to tasks in two ways:

- **By ID:** a task ID in a commit message, branch name, or PR title.
- **By what the task names:** for example, a task about a data format and a new schema file, an eval runner task and a script that runs the examples, a GitHub Actions task and a workflow file, or a filled-in `<placeholder>` in README.md, DECISIONS.md, or EVAL.md.

Name the evidence precisely: a commit hash, a file path, or a PR number.

## 5. Classify every task

- **Done:** marked `[x]`.
- **In progress:** marked `[~]`.
- **Blocked:** marked `[!]`, with the reason written in the plan.
- **Ready:** not started and all its Needs are done (or it has none).
- **Waiting:** not started and at least one Need is not done. Name the unmet Need, its owner, and that Need's own status.
- **Overdue:** past its Due date and not done. This combines with any of the above.

Then compare the marks with the evidence:

- **Looks done, not ticked:** evidence suggests the task is finished, but the box is not `[x]`.
- **Ticked, no evidence:** the box is `[x]`, but nothing in the repo shows the work. Some tasks leave no trace in the repo, such as a conversation with the user or a decision made in a meeting, so say "no repo evidence (may be fine)" rather than calling it wrong.
- **Disagreeing rows:** the same ID with different marks in two files.

## 6. Report in chat

With no argument, report on the whole team. With an argument (a member's name, first name, or part such as "backend"), match it to one member plan, and report only that member's section plus who is waiting on them. If the argument matches nobody, say so and list the members.

Use this order. Keep it to what a teammate can read in a minute.

1. **Headline**, one or two sentences: today's date, the next milestone and how many days away it is, and whether the team is on track or at risk. Call it at risk if a critical-path task is overdue, or if a P0 task due before the next milestone is not started.
2. **Milestones**: a table with milestone, date, and status (done / upcoming / at risk / missed). A milestone is done only when the tasks it depends on are done, or the plan marks it done.
3. **Per member**, for each member (or the one asked about):
   - Done in the last 7 days, with evidence where there is some.
   - In progress.
   - Ready next: P0 before P1 before P2, then by earliest Due.
   - Waiting on: the task, its owner, and what that owner should do first.
   - Overdue, if any.
4. **Whole-team tasks**: ready, waiting, and overdue, briefly.
5. **Blockers**: overdue or unstarted tasks on the master plan's critical path, and the tasks that block the most other tasks. Say who unblocks whom.
6. **Marks to check**: the mismatches from step 5, written as suggestions, for example "B1 may be done: commit abc1234 added `docs/data-format.md`. If so, Midhat can tick it in BACKEND-PLAN.md."
7. **Not read**: anything in the plans you could not parse, if there was any.

If nothing is ticked and there is no evidence yet, say that plainly and focus the report on what is ready to start and what is blocking the critical path.

## Rules

- Change no files. Do not tick boxes, edit plans, append to status logs, commit, or push. If the person asks for a tick after the report, that is a separate request, handled under the rules in `CLAUDE.md`. Tick only on the member's word or on evidence shown, and add a status-log line.
- Never invent progress, results, numbers, dates, or decisions. Say plainly when there is no evidence.
- Refer to members by the names the plans use.
- Write in complete sentences. Use tables only where they help, and never use the em dash.
