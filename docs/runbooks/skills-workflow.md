# The skills workflow: who does each step, with which skill and which prompt

As of 24 November 2026. This page is the order of the loop from a trader's words to the
trader being told, and what to type at each step. It records where each skill stands on that
date; it does not build or change any skill (those are TICKET-978 to TICKET-984, under
TICKET-977).

A skill does the mechanical work of a step. A person makes every decision. A step marked
"person only" has no skill and no prompt, and no skill may do it.

## The steps, in order

| # | Step | Who | Skill | Prompt |
|---|---|---|---|---|
| 1 | Capture the trader's words | a person | person only | none |
| 2 | Split the note into rows | the person who owns intake | verbatim-intake | "Run verbatim-intake on raw note RN-000N" (suggested wording) |
| 3 | Rule each row | the founder | person only | none |
| 4 | File the tickets | the founder's session | jira-ticket-creator | "raise the tickets" |
| 5 | Say yes to a drafted gate | the founder | person only | none |
| 6 | Build and open the PR | the ticket's assignee | scope-ticket | "start TICKET-NNN", then "page read", then "raise the PR" |
| 7 | First-pass review | the reviewer | pr-reviewer | "review PR #n" |
| 8 | Approve on GitHub | the reviewer, never the author | person only | none |
| 9 | Merge | the founder | pr-merger | "what can merge", then "merge the approved PRs" |
| 10 | Follow-up for an unmet gate line, the same day | the approver | jira-ticket-creator | "raise a follow-up" |
| 11 | Classify the release | the deployer | deployer | "classify the release" |
| 12 | Refresh staging | the deployer, with a person pasting on the server | deployer | "refresh staging" |
| 13 | UAT, then the tag | a tester who is not the author, then the founder | person only | none |
| 14 | Production deploy | the deployer prepares and checks; a person deploys, pasting on the server (person only) | deployer | "prepare the production deploy", "verify the deploy", "log the deploy" |
| 15 | Tell the trader | the skill drafts, the founder sends | loop-closer | "Draft the closing message for RN-000N" (suggested wording) |

Steps 1, 3, 5, 8 and 13 are person only. In step 14 the production deploy is person only: the
deployer skill only prepares and checks. In step 15 the sending is person only. Staging UAT
and the tagged production deploy decision stay human by the 14 November ruling.

## Where each skill stands on 24 November 2026

| Skill | Ticket | State |
|---|---|---|
| verbatim-intake | TICKET-978 | In Review |
| jira-ticket-creator | none (the worked example) | saved; TICKET-1044 waiting for the founder's yes |
| scope-ticket | none | saved; does step 6 until pr-raiser exists |
| pr-raiser | TICKET-979 | In Progress; not built |
| pr-reviewer | TICKET-980 | Done; follow-up TICKET-1045 waiting for the founder's yes |
| pr-merger | TICKET-981 | saved; In Progress |
| loop-closer | TICKET-982 | In Review |
| night-shift | TICKET-983 | In Progress; not built |
| deployer | TICKET-984 | saved; In Progress |

## Prompts off the main path

| Situation | Skill | Prompt |
|---|---|---|
| Try a review without posting anything | pr-reviewer | "DRY RUN. Review PR #n" |
| See which reviews are late | pr-reviewer | "which reviews are overdue" |
| Rehearse a merge batch | pr-merger | "DRY RUN merge" |
| Merge one PR | pr-merger | "merge PR #n" |
| A merge command errored | pr-merger | "gh pr merge failed" |
| A stacked PR must move to main | pr-merger | "re-point the stack" |
| Record rulings given in chat | jira-ticket-creator | "register the rulings" |
| Is the release destructive | deployer | "Path A or Path B" |
| A verify check failed | deployer | "roll back" (it prints the block and never runs it) |

## Rules for every step

- One new chat for each step. A skill fires on its prompt; name the skill only if it does not.
- Give the number in the prompt: the PR, the ticket or the tag.
- Where a skill gives a script or a block, run it and paste back exactly what the terminal
  showed.
- When a skill says STOP, a person has to act. Do the person-only step; do not reword the
  prompt to get past it.
- A ticket is done when its gate is true on the running product, not when its PR merges.

The deploy steps follow `docs/runbooks/deploy.md`, and step 13 follows
`docs/runbooks/uat-smoke.md`.
