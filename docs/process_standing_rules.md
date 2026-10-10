# Standing rules

Developer Manual section 10.7: ADRs explain the system, this file explains the process.
Every review ruling that changes practice is added here with the incident that paid for it,
and cited by number. Rules are not deleted; a superseded rule says so and names its
successor.

### SR-001 — methodology.md governs stage-0 scope; the Developer Manual is the target state

*10 Oct 2026.* An audit reported eight stage-1 items as repository defects: no CI, no PRs,
`main` rather than `master`, branch naming, no import-linter, no container, no DOF ledger,
no deletion service. All eight are methodology.md's deliberate staged-activation choices.
The audit had read one of the two governing documents. **Before auditing against the manual,
read methodology.md's stage table; on scope or timing it wins.** Recorded in the manual's
precedence section, v1.1.

### SR-002 — a verification tool may never be more forgiving than the thing it checks

A sandbox harness caught `Exception` broadly and reported green on a schema change that
pytest correctly failed, because the real code distinguished `UnsupportedInV1` from a
validation error and the harness did not. **The check runs the same way the subject does.**

### SR-003 — truncated output is not a result

*10 Oct 2026.* A pytest run piped through `tail -3` was read as the complete failure list,
producing a claim that two fixes had shipped without tests. Both had tests, under almost the
names proposed for them. **Read the whole output, or say that it was truncated.**

### SR-004 — "it exists" is a verification claim

*10 Oct 2026.* A Phase 0 summary was described as written to project knowledge before it had
been written. Section 4.6 binds documents and messages, not only commit messages:
**check, then state.**

### SR-005 — a guard whose RED was never seen is not yet a test

A test asserting a property that already holds can pass for the wrong reason, or assert
nothing at all. **Break the property deliberately, watch it fail, revert, watch it pass** —
and leave the RED in the terminal record. Manual section 5.2.

### SR-006 — no trader-derived content in git, in any form

Not raw, not aggregated, not summarised, and not in a commit message. Git history cannot be
deleted on request, and deletion was promised to recruits on 4 Oct 2026. Commit 0c48848
predates this rule and carries trader-derived counts; a pushed history is not rewritten, and
the rule dates from the moment it was found.

### SR-007 — every rate states its clustering unit

*10 Oct 2026.* The 600 adversarial nulls share one price series with overlapping windows, so
their false-positive events are correlated and the effective number of independent market
windows is far below the trader count. A rate reported with a binomial interval can pass or
fail a gate on noise, indistinguishably from merit. **State the unit the observations are
independent at, next to the rate.** Manual section 8.5.

### SR-008 — repository changes are executed by the founder, not applied for him

Reads may be direct. Every addition, edit and deletion is run as a command in the founder's
own terminal, so the change is visible as it happens. A change is proposed and approved
before it is run. Commands come one at a time when the outcome shapes the next step, and in
larger blocks when every step is certain.

### SR-009 — build the machinery before locking the framework

Pre-commitment only means something if the statistics it fixes have been exercised first.
Spec 13.1 gates external data ingestion behind the hash, not code, so the model, SBC, one
test end to end and the null rate all come before the lock. An error found after the lock is
an amendment that should have been a free fix. Manual section 8.3.

### SR-010 — a gate piped into `tail` is not a gate

*10 Oct 2026.* `pytest ... | tail -2 && git commit` committed a red test: the pipeline's
exit status is `tail`'s, so the `&&` chain saw success. Same class as SR-003, in the
form that matters most. **Any command whose exit status gates a commit runs with
`set -o pipefail`, or is not piped at all.** Where a gate's output is long, trim it
after the gate has been judged, not in the same pipeline.
