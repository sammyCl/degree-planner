# team-status

A Claude Code skill that gives the team a progress check on the degree planner.
It reads our plans in `plans/`, compares them with what the repository actually shows, and reports in chat where we are and what comes next.
It changes no files.

## How to use it

Open Claude Code in the `degree-planner` folder and type one of these:

| You type | You get |
|---|---|
| `/team-status` | The whole team |
| `/team-status Midhat` (or `Abdallah`, `Samantha`) | One person's tasks, plus who is waiting on them |
| `/team-status backend` (or `frontend`, `agent`) | The same, chosen by part |

You can also just ask in plain words, such as "where are we?", "are we on track?", or "what am I waiting on?", and Claude will use the skill.

If you just pulled and the skill does not show up, start a new Claude Code session; new skills load when a session starts.

## What it does

1. Reads every file in `plans/` as it is right now. Nothing about the plans is built into the skill, so adding tasks, changing dates, or adding a plan file needs no change here.
2. Checks today's date.
3. Looks at the repository without changing it: fetches from GitHub, reads recent commits on every branch, lists pull requests (if `gh` is set up), and looks at the files.
4. Sorts every task into done, in progress, blocked, ready (everything it needs is done), waiting (and on whom), or overdue.
5. Reports, in this order:
   - a one-line headline: the next milestone and whether we are on track
   - a milestones table
   - per member: done this week, in progress, ready next, and waiting on whom
   - whole-team tasks
   - blockers on the critical path
   - boxes to check: tasks that look done but are not ticked, or that are ticked with no sign of the work in the repo

## What it does not do

- It never ticks boxes, edits plans, writes status logs, commits, or pushes. When it suggests a tick, you tick it yourself, or ask Claude to in a separate request.
- It never invents progress, results, or dates. If there is no evidence, it says so.

## Help it work well

- Keep the status marks current: `[ ]` not started, `[~]` in progress, `[x]` done, `[!]` blocked (with the reason).
- Put the task ID in commit messages, branch names, or PR titles (for example `B1: add data format doc`), so the skill can match the work to the task.
- Keep the table shape the plans use now: an ID column, a status column, and ideally Priority, Due, and Needs.

The instructions Claude follows are in [SKILL.md](SKILL.md).
