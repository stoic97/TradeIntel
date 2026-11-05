# TICKET-834 — rules every file in this folder shares

*Drafted for the runner (Harshad) · ruled by the ruler (Pawan) · runner never rules. Nothing here is a verdict.*

**Source.** Each row is a claim T-001 made in his page-by-page review of 3 Nov 2026 (tracker rows FB-00nn in `stoic97/scope-feedback-loop`), ruled "research seat" by the founder on 4 Nov. His figures stay in the tracker and Jira: none is written here (README rule 1).

**Two outcomes only** (spec Annex B, §13.3; framework `governance.ai_may_not: add_or_alter_confirmatory_test`):

1. **Routed pre-registration.** The claim is already the question of a test in the core library (`services/research/prereg/framework_v1.yaml`, `library:`). It is pre-registered *as that test, as written there*: same quantity, model, null, θ_min, n_min, buckets and robustness set. The claim's own framing (its metric, its window, its split) is not used: re-cutting a library test to fit what one history showed is the forking path the pre-commitment exists to close (spec §2).
2. **Decline.** Anything else. A question outside the core is written to the candidate register (Annex B) as one line with its seed. Phase 0 does not build, pre-register or validate it (spec §10, Annex B); it enters through §13.3 when the core has proved the machinery.

**Data window, for every routed test.**
- **Excluded: the generating sample.** That is T-001's history as uploaded up to the 3 Nov review. Each claim was found by looking at it, so it cannot also be the evidence for it.
- **Eligible:**
  - (a) other cohort histories, in the framework's zones (`data.zones`: training, embargo, isolation read once);
  - (b) T-001's trades entered after 5 Nov 2026, from a fresh upload, once they reach n_min on their own.
- Instrument: `scope.validation_instrument` (MCX crude) is the confirmatory read. Other instrument families wait for their own calibration (`scope.transfer_rule`).

**Kill conditions, for every routed test:** the framework's own (`evidence.kills`), plus:
- **not run** before `framework_v1.yaml` is locked (its `.sha256` committed; status today is DRAFT);
- **void** if the only history reaching n_min is the generating sample.

**Lane.** Serialized (developer manual §8): pre-registration before any full-window run. No result from this folder appears on a Scope page until its test reaches a tier under `evidence.tiers`.
