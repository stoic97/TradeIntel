# docs/ - what each document is, and whether to trust it

Every document under `docs/` has one row here. A new document gets its row in the same PR;
`tests/unit/repo/test_docs_index.py` fails until it has one, and fails on any link or backticked
path in a live document that points at nothing.

**Status.** *live*: current, and kept true. *frozen <version>*: changes only by a version bump
and a change-log row, or for an ADR an Amendments entry (SR-011, `tests/unit/repo/test_frozen_docs.py`).
*archived*: kept for the record in `docs/archive/`, never edited, and its row names what superseded
it. *target state*: describes something not built yet.

Documents kept outside this repository (the PRD, the Developer Manual, the merge practice, the
deploy runbook and log) are listed in `docs/references.md` with where each lives.

| Document | What it is | Status | Owner | Last checked |
|---|---|---|---|---|
| [adr/ADR-001-canonical-trade-record.md](adr/ADR-001-canonical-trade-record.md) | ADR 001: the canonical trade record, versioned by file | frozen Accepted | founder, engineering | 2026-11-20 |
| [adr/ADR-002-the-wall.md](adr/ADR-002-the-wall.md) | ADR 002: the wall between the fund and the product | frozen Accepted | founder | 2026-11-20 |
| [adr/ADR-003-precommitment-hash.md](adr/ADR-003-precommitment-hash.md) | ADR 003: the pre-commitment hash of the research framework | frozen Accepted | founder, research | 2026-11-20 |
| [adr/ADR-004-stage0-tech-stack.md](adr/ADR-004-stage0-tech-stack.md) | ADR 004: language, runtime and environment | frozen Accepted | founder, engineering | 2026-11-20 |
| [adr/ADR-005-storage-and-reproducible-runs.md](adr/ADR-005-storage-and-reproducible-runs.md) | ADR 005: storage, and the environment for charged runs | frozen Accepted | founder, engineering | 2026-11-20 |
| [adr/ADR-006-sampler.md](adr/ADR-006-sampler.md) | ADR 006: the sampler for the research models | frozen Accepted | founder | 2026-11-20 |
| [adr/ADR-007-scope-v1-runtime.md](adr/ADR-007-scope-v1-runtime.md) | ADR 007: Scope v1 runtime - one process, server-rendered, SQLite, one droplet | frozen amended 2026-11-16 | founder, engineering | 2026-11-20 |
| [adr/ADR-008-market-data-source.md](adr/ADR-008-market-data-source.md) | ADR 008: market data from the Fyers connection | frozen Accepted | founder | 2026-11-20 |
| [architecture/tech-stack.md](architecture/tech-stack.md) | The stack the ADRs add up to, and what is deferred | live | engineering | 2026-11-20 |
| [archive/trade_dna_phase0_plan.md](archive/trade_dna_phase0_plan.md) | Phase 0's nine-week plan of 3 October. Superseded by Thesis v1.5, and for the schedule by TICKET-897's plan (Stages A to D). Its two seat rules moved to SR-014 in process_standing_rules.md. Its partner screen (at least 200 crude trades over at least 3 months) was a recruiting screen and is spent; it is not the research spec's adequacy bar (at least 100 trips, at least 3 months) | archived | founder | 2026-11-20 |
| [archive/trade_dna_product_thesis_v1.4.md](archive/trade_dna_product_thesis_v1.4.md) | Product thesis v1.4. Superseded by Thesis v1.5 | archived | founder | 2026-11-20 |
| [deferrals.md](deferrals.md) | Index of TD ids and their Jira tickets | live | founder | 2026-11-20 |
| [design/README.md](design/README.md) | What is in docs/design, and where the kit is not what to build | live | founder | 2026-11-20 |
| [design/scope-kit/README.md](design/scope-kit/README.md) | The engineering kit from Claude Design: tokens, components, screens | live | founder | 2026-11-20 |
| [design/scope-kit/static/fonts/README.md](design/scope-kit/static/fonts/README.md) | The fonts the kit uses, and where they come from | live | founder | 2026-11-20 |
| [methodology.md](methodology.md) | The repository methodology v1.0, with the rules enforced at each stage | live | Engineering Lead | 2026-11-20 |
| [phase0/blind-replay-prereg.md](phase0/blind-replay-prereg.md) | Blind replay: what the score may claim, written before anyone plays | live | research seat | 2026-11-20 |
| [phase0/corpus-a.md](phase0/corpus-a.md) | Corpus A, the synthetic test bed | live | research seat | 2026-11-20 |
| [phase0/method-findings.md](phase0/method-findings.md) | Facts about the method, learned while building | live | research seat | 2026-11-20 |
| [phase0/null-rate-b2-prereg.md](phase0/null-rate-b2-prereg.md) | B2 null rate: the predictions, written before the full run | live | research seat | 2026-11-20 |
| [phase0/null-rate-b2.md](phase0/null-rate-b2.md) | B2 false-positive rate: the Class B gate result | live | research seat | 2026-11-20 |
| [phase0/recall-b2-prereg.md](phase0/recall-b2-prereg.md) | B2 recall: the predictions, written before the run | live | research seat | 2026-11-20 |
| [process_standing_rules.md](process_standing_rules.md) | The standing rules, SR-001 onward | live | founder | 2026-11-20 |
| [product/broker_connector_note_v1.md](product/broker_connector_note_v1.md) | The first read-only broker connector: what the APIs expose (TICKET-901, started) | live | founder | 2026-11-20 |
| [product/definitions_v1.md](product/definitions_v1.md) | Definitions: trading day, the B2 rule, the Journal unit, the import states | live | founder | 2026-11-20 |
| [product/reconciliation_v1.md](product/reconciliation_v1.md) | Why an outside FIFO count differs from Scope's (TICKET-788) | live | founder | 2026-11-20 |
| [product/scope_testing_register_v1.md](product/scope_testing_register_v1.md) | The testing register, TR-001 to TR-014. Each open item is moving to a Jira ticket (TICKET-934) | live | founder | 2026-11-20 |
| [product/scope_engineering_handoff_v1.md](product/scope_engineering_handoff_v1.md) | The engineering handoff: the build spec for the Scope UI; it wins where others disagree | live | founder | 2026-11-20 |
| [references.md](references.md) | Where each document the repo cites lives, and who grants access | live | founder | 2026-11-20 |
| [research/experiments/TICKET-834/_common.md](research/experiments/TICKET-834/_common.md) | TICKET-834: the rules every file in the folder shares | live | research seat | 2026-11-20 |
| [research/experiments/TICKET-834/README.md](research/experiments/TICKET-834/README.md) | TICKET-834: T-001's research rows, pre-registered or declined | live | research seat | 2026-11-20 |
| [research/experiments/TICKET-834/TICKET-834-FB-0012-decline-guess-instrument.md](research/experiments/TICKET-834/TICKET-834-FB-0012-decline-guess-instrument.md) | FB-0012: declined, the guess is a gate instrument | live | research seat | 2026-11-20 |
| [research/experiments/TICKET-834/TICKET-834-FB-0013-decline-locked-engine-tag.md](research/experiments/TICKET-834/TICKET-834-FB-0013-decline-locked-engine-tag.md) | FB-0013: declined, a product feature | live | research seat | 2026-11-20 |
| [research/experiments/TICKET-834/TICKET-834-FB-0049-decline-nifty-premium-band.md](research/experiments/TICKET-834/TICKET-834-FB-0049-decline-nifty-premium-band.md) | FB-0049: declined, to the candidate register | live | research seat | 2026-11-20 |
| [research/experiments/TICKET-834/TICKET-834-FB-0050-B5-sequence-decay.md](research/experiments/TICKET-834/TICKET-834-FB-0050-B5-sequence-decay.md) | FB-0050: routed to B5 sequence_decay | live | research seat | 2026-11-20 |
| [research/experiments/TICKET-834/TICKET-834-FB-0058-S1-session-us-overlap.md](research/experiments/TICKET-834/TICKET-834-FB-0058-S1-session-us-overlap.md) | FB-0058: routed to S1 session_expectancy | live | research seat | 2026-11-20 |
| [research/experiments/TICKET-834/TICKET-834-FB-0059-decline-nifty-half-hours.md](research/experiments/TICKET-834/TICKET-834-FB-0059-decline-nifty-half-hours.md) | FB-0059: declined, merged into FB-0058 | live | research seat | 2026-11-20 |
| [research/experiments/TICKET-834/TICKET-834-FB-0078-decline-risk-per-trade-shift.md](research/experiments/TICKET-834/TICKET-834-FB-0078-decline-risk-per-trade-shift.md) | FB-0078: declined, to the candidate register | live | research seat | 2026-11-20 |
| [research/experiments/TICKET-834/TICKET-834-FB-0097-B2-book-split.md](research/experiments/TICKET-834/TICKET-834-FB-0097-B2-book-split.md) | FB-0097: routed to B2 with P2 | live | research seat | 2026-11-20 |
| [research/experiments/TICKET-834/TICKET-834-FB-0109-S5-R8-regime.md](research/experiments/TICKET-834/TICKET-834-FB-0109-S5-R8-regime.md) | FB-0109: routed to S5 and R8 | live | research seat | 2026-11-20 |
| [research/experiments/TICKET-834/TICKET-834-FB-0110-admissibility-journal-answers-r7.md](research/experiments/TICKET-834/TICKET-834-FB-0110-admissibility-journal-answers-r7.md) | FB-0110: Journal answers for R7, decline recommended | live | research seat | 2026-11-20 |
| [research/experiments/TICKET-852/TICKET-852-decline-post-loss-better.md](research/experiments/TICKET-852/TICKET-852-decline-post-loss-better.md) | TICKET-852: declined, to the candidate register | live | research seat | 2026-11-20 |
| [runbooks/charge-rates.md](runbooks/charge-rates.md) | The statutory charge rates, and how they are locked | live | engineering | 2026-11-20 |
| [runbooks/crude-series.md](runbooks/crude-series.md) | The crude 1-minute series, and how it is extended | live | engineering | 2026-11-20 |
| [runbooks/data-deletion.md](runbooks/data-deletion.md) | Deleting a trader's data | live | engineering | 2026-11-20 |
| [runbooks/data-flow-map.md](runbooks/data-flow-map.md) | Every system that touches a tradebook | live | engineering | 2026-11-20 |
| [runbooks/deploy.md](runbooks/deploy.md) | Putting Scope on a server, and every deploy after | live | engineering | 2026-11-20 |
| [runbooks/deploys.md](runbooks/deploys.md) | Production deploys to scope.plusev.in | live | engineering | 2026-11-20 |
| [runbooks/price-series.md](runbooks/price-series.md) | The price series in production | live | engineering | 2026-11-20 |
| [runbooks/uat-smoke.md](runbooks/uat-smoke.md) | The fixed UAT pass every release train gets | live | engineering | 2026-11-20 |
| [trade_dna_brainstorm_workbook_v1.1_final.md](trade_dna_brainstorm_workbook_v1.1_final.md) | The brainstorm workbook, cited as B section | frozen v1.1.1 | founder | 2026-11-20 |
| [trade_dna_product_thesis_v1.5.md](trade_dna_product_thesis_v1.5.md) | The product thesis, cited as T section | frozen v1.5 | founder | 2026-11-20 |
| [trade_dna_research_spec_v1_0.md](trade_dna_research_spec_v1_0.md) | The research specification and its annexes | frozen v1.0.5 | founder, research | 2026-11-21 |

## Phase 0 result files

Each file under `docs/phase0/` that holds a result, the code that writes it, and the commit its
rows came from.

| File | Produced by | At commit |
|---|---|---|
| `phase0/adr-006-benchmark.json` | `scripts/benchmark_m1_core.py` | `35cc417` |
| `phase0/finding-bar-b2.json` | `services/research/evaluation/finding_bar.py`, run as `python -m services.research.evaluation.finding_bar` | not recorded in the file |
| `phase0/null-rate-b2.json` | `scripts/run_null_rate_b2.py` | `aa10a0b` |
| `phase0/recall-b2.json` | `scripts/run_null_rate_b2.py` | `b572fcf` |
| `phase0/sbc-m1.json` | `scripts/run_sbc_m1.py` | `fab8074` |
| `phase0/sbc-m1-centred.json` | `scripts/run_sbc_m1.py` with `--centred` | `0bce1e2` |
