# Corpus A — the synthetic test bed

*Step A of the Phase 0 timeline, built 5–7 Oct 2026. Code: `services/research/evaluation/synthetic/`. Build: `uv run python scripts/build_corpus_a.py`. Output: `data/corpus/corpus_a_v1/` (gitignored — it regenerates from code + seeds + the logged price file).*

## What it is

Research Spec v1.0 §12.2's synthetic corpus: traders whose flaws we planted, so the engine's recall and false-alarm rate can be measured against ground truth before any partner's data is read.

| Part | Count | Market |
|---|---|---|
| Planted: 17 behaviours × 3 sizes (θ_min, 2θ_min, 4θ_min) × 3 lengths (100, 300, 1,000 trips) × 8 seeds, each with a no-behaviour twin | 1,224 | MCX crude 1-min, `data/market/crude_1m.csv` |
| Clean nulls: zero edge, no behaviour, i.i.d. random walk | 400 | Each its own seeded random walk |
| Adversarial nulls: zero edge, no behaviour, real market structure, drifting trade rate, per-trader style | 600 | MCX crude 1-min |

## Identity

The manifest carries two digests (Research Spec §12.1 splits determinism this way):

- **`decision_sha256`** — every fill and every label, no float. Must match on every machine. **Corpus A v1 at the commit that adds this file: `44e8e495bc56bfde3e07d6937b4cef70f75a99ad5ae02103af85c2923f622947`.** `tests/reproducibility/test_corpus_digest.py` pins the same digest for a small corpus on every test run.
- **`corpus_sha256`** — all three tables, floats included. Exact only within one environment: another numpy or CPU moves the 16th digit of R, risk and size (measured 7 Oct 2026: identical trades and labels on an Apple-silicon Mac with the locked numpy 2.4.6 and an x86 box with numpy 2.5.3; float columns differed by at most ~1e-9 relative). The pinned environment (`uv.lock`) is the reference.

## Where it departs from Research Spec §12.2 — each a known limit, not a silent one

| # | Spec says | Corpus A v1 does | Consequence |
|---|---|---|---|
| 1 | Three mechanisms | Three for condition-driven behaviours (drift, size, exit) plus six trade-shape mechanisms (size spread, stop widen, giveback, latency, add, carry) | R1, R7, E4′, E2, B1, R11 and S6 change the shape of a trade, which the three cannot express |
| 2 | Plant θ_min, 2θ_min, 4θ_min | 33 of 153 cells are marked `reached=False`: drift caps at about 0.78R (4θ_min = 1.0R), B12 at 2θ_min and 4θ_min, E5 below a 0.59 duration ratio | Recall is scored only on reached cells; B12 and E5 have one reached size |
| 3 | Market layer: the fund's crude **tick** history | Stitched **1-minute** bars, Oct 2018 – Dec 2025 | Tick data not yet confirmed; §4.2 allows 1-min bars only for holds ≥ 45 min, and the base trader's median hold is 45 min |
| 4 | Contract identity per trip | Stitched series; each trip given the future expiring on the 19th; no carry across an expiry | A convention, not real contract prices |
| 5 | S5 on the fund's regime labels | A stand-in label (previous day's range vs the prior 20 days) | Replace when the fund's labels cross as data (ADR 002) |
| 6 | R8 on the fund's volatility regime | The trader's own ATR tercile against the previous 5 days | Same as 5 |
| 7 | S10: holding interval overlapping [T−15, T+30] of EIA, API and OPEC releases | Entry within [T−45, T+30] of the Wednesday EIA release only | API (after the MCX close) and OPEC days not planted |
| 8 | R7 needs stop orders in the export | CTR v1 has no stop-order field; no stops exported | R7 is measurable only once stops are exportable; every synthetic futures trip reconstructs with `risk_unit=None` until the inferred risk unit exists |
| 9 | Adversarial nulls: autocorrelated outcomes, changing instrument mix | Real-market structure and a drifting rate; one instrument | Autocorrelation comes only from the market; no instrument mix |
| 10 | Holding times in minutes | Holds, latencies and cut-offs count **bars**; real days have missing minutes | Small on liquid sessions; larger on thin days |
| 11 | Avoidable cost from the twin | Twin = same seed and length without the behaviour; when a behaviour changes entries or holds, the two histories span different calendar stretches | The twin cost is exact per trading decision, approximate per calendar period |

## A finding the corpus already produced

On a driftless path, behaviours that only reshape *when* a trade exits (stop widen, giveback, add, carry at zero strength) move the distribution of R — tails, MAE — but not its mean. Any avoidable cost the engine claims for them on synthetic histories must be checked against the twin, not assumed.
