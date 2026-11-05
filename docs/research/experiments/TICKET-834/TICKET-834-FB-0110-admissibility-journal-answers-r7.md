# FB-0110 · admissibility of Journal answers for R7: recommend decline

*Runner: Harshad · Ruler: Pawan, who rules admissibility · Shared rules: [`_common.md`](_common.md)*

**The question:** are Journal answers ("Where was your stop?", "Was the stop on the chart when you entered?") admissible evidence for R7 `stop_discipline`?

**Recommendation: not admissible as R7's condition in v1.**
- **Point in time.** A Journal exists only after an upload, so every Journal field is captured **after close** by construction (`capture_phase = after_close`, pinned in `tests/unit/api/test_journals.py`). R7's condition would then be known after the outcome. That breaks `data.point_in_time` (`feature.available_at ≤ trade.entry_time`), and it is leakage class C3/C4: a stop remembered after a loss is not a stop that existed at entry.
- **Self-report.** The method rule (brand C03) is never to build on self-report alone. A Journal answer is self-report.
- **R7 is already scoped.** Its library class is `conditional_on_stop_orders`: it reads stop orders the broker recorded. That is unchanged.

**What the answers can be:**
- a description shown back to the trader beside his trades, never a condition, a comparison or evidence toward a tier;
- if a stop is ever captured **before entry** in some future version, that capture is a new data source with its own admissibility ruling.

**Ruling (Pawan):** admissible / not admissible / admissible only for ______ · date ______
