# Where things live

Each kind of record has one home. Everywhere else carries a key or a link to it, never a
second copy. Set by the founder on 17 Nov 2026 (TICKET-953).

| What | Its one home | Allowed anywhere else |
|---|---|---|
| Open work: bug, feature, change, deferral, open decision | Jira (Plusev_Engineering) | Its Jira key only |
| Raw customer feedback | scope-feedback-loop tracker (FB rows) | Once it becomes work: a Jira ticket, and the FB row carries the key |
| A ruling | A comment on its Jira ticket, plus the repo doc it changes | A link |
| Specs, design, runbooks, the handoff | TradeIntel `docs/`, one copy | Project knowledge keeps only a copy headed "Mirror of <repo path> @ <commit>; edit the repo", or nothing |
| Team process docs (Developer Manual, PR merge practice) | The plusEV – Scope Project's knowledge, one copy | The repo links to it |
| Figures from a real trader's file | Never in git or the Project; in the Jira ticket only when the fix needs them | Nothing |

## Deferrals

- No new TD or TR ids. A new deferral is a Jira ticket labelled `deferral`.
- `docs/deferrals.md` is an index only: id · one-line title · area · Jira key. A row closed
  without a ticket reads "Closed <date>: <reason>" instead of a key. No status, no history:
  the detail lives in the ticket.
- The testing register's rows keep their ids in the archived register, each with its Jira key
  or closed note.

## What holds this

`tests/unit/repo/test_where_things_live.py` runs in `make test`. It fails when:

- a file in `docs/` calls itself a register or tracker, or the place where items go;
- a TD or TR id anywhere in the repo, code comments included, has no Jira key or closed note;
- the index gains a column, or an id above the highest one on 17 Nov 2026;
- this file is missing, or `docs/README.md` exists and does not link to it.

Whether each key opens in Jira is checked by hand when a PR changes the index: tests have no
network.
