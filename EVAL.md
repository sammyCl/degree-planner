# Evaluation

## The claim

<one claim about the system, stated so a number can confirm or refute it>

## Baseline

<the obvious simpler approach the system is compared against; if there is more than one agent, the single-agent version too>

## Examples

The five real examples from our proposal. For every example, the right output is a degree plan that is organized in a readable way and lets the student graduate in the time they specified, plus the extra requirements listed.

| # | Input | Also must | Difficulty |
|---|---|---|---|
| 1 | General Computer Science bachelor's | Almost match the CS General Track flowchart | Simple |
| 2 | General EE master's with transfer credits | Account for the transfer credits properly | Simple |
| 3 | Combined mining bachelor's and master's | Handle double-counted credits properly | Medium |
| 4 | AMS bachelor's with a Computer Science minor | Handle double-counted credits properly | Medium |
| 5 | CS bachelor's (with transfer credits and the Thorson First Year Honors Program), a Geophysical Engineering minor, and a non-thesis CS master's (project track, Independent Study credits, combined credits) | Handle transfer credits, Independent Study credits, master's project credits, and double-counted credits properly | Hard |

<where the example inputs and expected outputs live in the repo>

## How to run it

<the command, and the GitHub Actions workflow that runs it>

## Results

<the numbers, from the latest run, with a link to that run>

## Cost

- One task: <cost>
- At 10,000 requests a day: <cost, with the arithmetic>

## Threat model

Which parts of the lethal trifecta the system has (lecture 26):

- Reads private data: <yes/no, what>
- Reads content from outside: <yes/no, what>
- Can send things out: <yes/no, how>

What we did about it: <mitigations>
