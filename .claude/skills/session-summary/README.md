# session-summary

A Claude Code skill that writes a private summary of the session you just had, so you can fill in `DECISIONS.md` later with the options and reasons you actually gave.

## How to use it

At the end of a Claude Code session in the `degree-planner` folder, type one of these:

| You type | You get |
|---|---|
| `/session-summary` | A summary in your own folder, picked from your `git config user.name` |
| `/session-summary Midhat` (or `Abdallah`, `Samantha`) | A summary in that person's folder |

You can also ask in plain words, such as "summarize this session" or "what did we decide today?".

If you just pulled and the skill does not show up, start a new Claude Code session; new skills load when a session starts.

## Where the summaries go

```
summaries/
  samantha/
  midhat/
  abdallah/
```

Each summary is one file named `<date>-<topic>.md`. The folder is gitignored, so summaries stay on your own machine and are never pushed to the public repo. Share one with the team by pasting it, if you want to.

## What is in a summary

- the goal of the session
- what was done: files, commits, uncommitted changes, test results
- choices made, each drafted in the `DECISIONS.md` template shape (Decision, Options considered, Why) and marked as worth an entry or not
- problems and dead ends
- open questions and next steps

## What it does not do

- It never edits `DECISIONS.md`, `EVAL.md`, or the plans. You copy the choices you want into `DECISIONS.md` yourself.
- It never invents reasons. If you did not say why you chose something, the Why field says `<fill in>`, and when Claude suggested something you only agreed to, the summary says so.
- It never commits or pushes.

The instructions Claude follows are in [SKILL.md](SKILL.md).
