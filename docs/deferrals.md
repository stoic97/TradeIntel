# Deferrals — the stage-0 ticket register

Developer Manual section 8.7: *a deferral is a ticket number or it didn't happen.* Stage 0
has no tracker, so this file is the register. **A deferral not listed here does not exist.**

## Research — these affect what the engine can measure

| id | Deferred | Why | Unblocked by | Due |
|---|---|---|---|---|
| TD-001 | Short-option R convention | No agreed risk unit for a sold option, so `ctr_v1` refuses them | A written convention | Before the CTR schema freezes; sooner if option sellers exceed a quarter of the partner pipeline |
| TD-002 | Fees. Every currency figure is gross | No adapter has a charges column, and Avoidable Loss in rupees is a headline number | A decision: ask partners for charges statements, or compute the Indian charge model and label it an estimate (spec 4.5 forbids presenting an estimate as exact) | The kickoff — it changes the recruitment ask |
| TD-003 | R7 is unmeasurable | CTR v1 has no stop-order field, so no stops are exported and every futures trip carries `risk_unit=None` | A stop-order field, or the inferred risk unit (TD-013) | Before R7 is counted in the library's size |
| TD-004 | E2 and E4-prime are scoped, not full | The crude series is 1-minute bars, not tick. MFE bias is about 0.33/sqrt(hold/bar), so 1-minute bars only carry these for holds of 45 minutes or more | Tick history, or accepting the scope | **In framework_v1.yaml before the hash lock** |
| TD-011 | S5 and R8 run on stand-in labels | The fund's regime and volatility labels have not crossed as data | An ADR-002 crossing | Before either test's result is published |
| TD-012 | Class B gate reading rules | The 600 adversarial nulls share one 1,816-day series. Window overlap is 6.3 / 12.5 / 37.8 percent by class and the median day is traded by 117 of them, so null events are correlated and a binomial interval is wrong | Writing three rules: a window-clustered interval; market-episode false positives counted once; the gate read on the 100- and 300-trip classes | **In framework_v1.yaml before the hash lock** |
| TD-013 | Inferred risk unit | Not implemented. The synthetic truth table carries the generator's risk instead | A definition: size times volatility at entry, labelled inferred | Before R is reported on futures trips |
| TD-014 | S10 planted on the Wednesday EIA release only | API lands after the MCX close; OPEC days are not planted | A release-calendar crossing | Before S10's recall is quoted |

| TD-017 | Block-bootstrap interval authority | Section 6.2 point 2: the stationary block bootstrap interval is computed alongside the model interval and **the model interval is widened to match if it is narrower** - "we never report the narrower of two honest answers". M1 currently reports only its own interval | Implementing P7 and the comparison in the fit path | Before the first promoted Finding; also feeds the dependence audit ratio floor of 0.85 |
| TD-018 | `tau_day`'s prior | Section 6.2 mandates day-level random intercepts; section 6.3 gives starting values for alpha, theta, sigma, nu and beta and stops, so the day effect's scale has no pre-committed prior. HalfNormal(0.5) is in use, matching alpha's scale, and carries its provenance in code | A ruling, written into framework_v1.yaml | **Before the hash lock.** Under section 0 an arbitrary value gets one revision window, on synthetic corpora, before any partner's data |
| TD-019 | A condition almost determined by the day defeats M1 | Measured 10 Oct 2026: with prevalence swinging 2 to 95 per cent across days there is no within-day contrast left, partial pooling leaves part of the day effect in the residual, and theta absorbs it - theta -0.45 with posterior sd 0.14 against a true theta of zero, with zero divergences, r_hat inside 1.01 and bulk ess far above 400. Non-identifiability, not a sampling failure, so the framework's diagnostics cannot see it. Affects S10 (Wednesday EIA), B12 (the day is the outcome), S1 (session), S6 (overnight carry) | A ruling: either a pre-registered identifiability check per test, or a different model for day-linked conditions | **Before the hash lock**, because it changes what some of the eighteen tests may claim |

## Engineering — the manual requires these; methodology.md defers them by stage

| id | Deferred | Why | Unblocked by | Due |
|---|---|---|---|---|
| TD-005 | Golden certification set, 200 or more round trips per broker | No partner exports yet. Development fixtures and a pinned synthetic digest serve the same purpose today | Partner tradebooks | Before the first framework-version gate |
| TD-006 | tests/integration and tests/e2e | There is no pipeline to integrate and no journey to walk | The first end-to-end path, upload to finding to report | With that path |
| TD-007 | DOF ledger, append-only | No charged run has happened | — | **Before the first isolation read, Phase 0 week 7** |
| TD-008 | .importlinter and the import-boundary job | Stage 1 in methodology.md. The boundary is honoured by layout today | A second engineer, or the agent service | Stage 1 |
| TD-009 | Faithfulness suite | No agent service exists, and nothing needs narrating until a Finding does | The narration layer | With that layer, before any composed prose ships |
| TD-010 | WALL.md signature | ADR-002 carries the reasoning; the signature is outstanding | CEO signature | **Overdue.** Section 10.1 requires it before partner data is ingested, and an export was imported on 7 Oct 2026. Sign now and minute the deviation with its true date |
| TD-015 | Pinned container image | Stage 0 pins the interpreter minor and every dependency exactly, and a cross-machine check passed on 7 Oct 2026 | — | Before the first charged run |
| TD-016 | Kickoff minutes template | Not written. No template exists anywhere | — | Before the kickoff |
