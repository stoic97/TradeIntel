# Contributing to TradeIntel (the Scope app)

How a change reaches `main`. This is the short form. The full practice, with the incidents
that shaped it, is the Project document **"Scope — how a PR gets merged"** (`claude/scope_pr_merge_practice_v1.md`
in the plusEV – Scope claude.ai Project; see [docs/references.md](docs/references.md) for
access). Where the two differ, the Project document wins and this file is corrected.

## Setup

See the [README](README.md). Every command runs through `uv` (`make help` lists them); there
is nothing to activate.

## One ticket, one branch, one PR

- Every change starts as a Jira ticket in `Plusev_Engineering` with its gate ("what must be
  true to close this"). No ticket, no branch.
- **Branch:** `<prefix>/TICKET-NNN-short-slug`, where the prefix is one of:

  | Prefix | For |
  |---|---|
  | `fix/` | a bug or a wrong read |
  | `feat/` | anything new, CI and tooling included |
  | `docs/` | documents only |
  | `refactor/` | a change that alters no behaviour |

  Not `feature/`, `screenshots/` or anything else. `methodology.md` §11 names `feature/*`; the
  merge practice the founder adopted on 4 Nov 2026 replaced it with the set above.
- **One PR closes one ticket.** If a fix needs a second ticket's worth of change, raise the
  second ticket and stack its PR on the first. Never widen the PR.
- Only the PR's own ticket key appears in its title and commits: a merged PR moves every
  ticket it names to Done.

## Commits

Conventional Commits, with the ticket id:

```
<type>(<area>): TICKET-NNN <what changed, in plain words>
```

`type` is one of `feat`, `fix`, `docs`, `refactor`, `test`, `style`, `chore`, `ci`. The first
line stays under 72 characters; the body says *why*.

**RED first.** A branch's first commit is the failing test, marked RED:
`test(<area>): TICKET-NNN RED - <what it pins>`. The fix follows as its own commit, so a
reviewer sees the test fail before it passes (SR-005). Both are kept.

**No WIP commits on `main`.** A branch may hold work in progress; what merges is finished.
"wip" in a subject line on `main` is a defect.

## Before review

- Merge `main` into the branch and run `make test`. Paste its last line (`N passed …`) into
  the PR description. Green on today's `main` is the bar, not green on your branch.
- A change to a Mirror or Journal figure comes with a hand-calculated fixture or expected
  values, written from the spec, never from program output.
- Screenshots go **in the PR**, dragged into its description. Never committed, never pushed to
  a branch.
- No trader data, anywhere: not in code, tests, fixtures, commits, screenshots or the PR
  (README rule 1, SR-006). Fixtures are synthetic.

## Review and merge

- **The reviewer is not the author**, and the reviewer merges. Rotation: Harshad → Megha →
  Rikk → Vishal → Harshad.
- Review is against the ticket's gate: does this diff make the gate's sentence true, and does
  a test prove it? Call out every time: a change to definitions, the consent text, the
  never-use words or an engine read ("pending research seat"); a figure over a different
  population than its sentence; any migration, deletion or storage change.
- **Merge commit, never squash, never rebase:** `gh pr merge <n> --merge --delete-branch`.
  Squashing folds the RED test into the fix and loses the proof.
- **Stacked PRs merge base first.** Write "stacked on #n" as the PR's first line, and re-point
  the top PR at `main` (`gh pr edit <top> --base main`) before merging the base.
- Never push to `main`, never force-push it, never merge your own PR.
- After any error from `gh pr merge`, check `gh pr view <n> --json state,mergedAt` before
  retrying.

## Done

A ticket is **Done only when its gate is true on the running product**, not merely on
`main`. If it needs a deploy, it waits for the deploy; if it needs a re-upload or a data fix
for the trader who raised it, that is done first.

## Where tests and fixtures go

- **Tests** mirror the code: a test for `services/production/<module>/…` goes in
  `tests/unit/<module>/`; repository rules go in `tests/unit/repo/`. Nine older files sit at
  the `tests/unit/` root; leave them until their module is next worked on, then move them
  into its folder. New files never go at the root.
- **`data/fixtures/`** holds synthetic **input files in a broker's own format**: what an
  upload would be (a Dhan tradebook, a Groww orders file, the demo file, the duplicate
  pairs). Tests, scripts and the demo all read them.
- **`tests/fixtures/`** holds what only tests read: **expected values and contracts** (the
  Mirror contract, the wording reference, the dial geometry cases).
- Both are synthetic, made by hand or by code from a committed seed. Nothing derived from a
  real trader's history, ever.

## Documents cited from the code

Code and docs cite documents that live outside this repository (the PRD, the handoff, the
Developer Manual, the technical design). [docs/references.md](docs/references.md) says where
each one lives, its current version and who grants access.
