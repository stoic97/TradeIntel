# B2 false-positive rate — the Class B gate result

*11–12 October 2026 · 1,000 null histories from corpus A · rows from `aa10a0b`, intervals recomputed later · machine-readable: `null-rate-b2.json`*

## The number

| | fired | evaluable | starved | rate | authority interval | envelope |
|---|---|---|---|---|---|---|
| **adversarial** (the gate) | **0** | 278 | 322 | 0.00% | [0%, 1.36%] | [0%, **17.59%**] |
| clean (control) | 0 | 133 | 267 | 0.00% | [0%, 2.81%] | [0%, 2.81%] |

**B2 did not produce a single false positive in 411 traders who had nothing to find.** The ceiling — the reading that would have made the test unshippable, the engine inventing leaks in clean traders — was never approached.

## The pre-registration held

Written before the run, in `null-rate-b2-prereg.md`, after two predictions this project made earlier were both falsified:

| Predicted | Actual |
|---|---|
| 250–330 evaluable adversarial | 278 |
| 0–4 fires | 0 |
| rate 0–1.5% | 0.00% |
| Wilson upper below 2% | 1.36% |
| verdict below the band | yes |
| binomial as authority, bootstrap degenerate at zero fires | exactly that |
| clean class materially thinner | 33% evaluable vs 46% |

Seven for seven. The value of that is not the score — it is that a result nobody predicted in advance can be read however the reader wishes afterwards.

## The envelope, and why the headline number is not 1.36%

The authority interval assumes 278 independent observations. The 278 adversarial histories sit in **18 calendar windows** of one crude series, and histories covering the same months saw the same noise.

At zero fires the block bootstrap returns [0%, 0%] — every resample of every cluster gives zero, so it asserts certainty. Authority then fell to the binomial by default. The "wider wins" rule (TD-017) protected this project in every case except the one it got.

So a third reading is now computed: each window as one Bernoulli observation of "did anything here fire?". That gives **[0%, 17.59%]** — above the 8% ceiling. The two readings bracket the truth:

- **1.36%** if histories within a window are effectively independent.
- **17.59%** if a whole window tells us one thing.

Reality is nearer the low end — measured pairwise overlap between adversarial histories was 6.3% / 12.5% / 37.8%, so they are correlated but far from identical. Without a non-zero event count there is nothing to estimate the intra-window correlation from, so the bracket cannot be narrowed from this run.

The clean class confirms the machinery rather than the test: with 133 independent series its envelope collapses onto its authority interval. The cluster bound widens only where clustering exists.

## What this licenses, and what it does not

**Can be said:** B2 produced no false positive in 278 adversarial null histories and 133 clean ones, under a promotion rule measured without the four pending gates, which can only lower the rate further.

**Cannot be said:** that the false-positive rate is below 2%, or that the Class B gate is passed. This corpus's 18 independent calendar windows cannot pin the rate to the precision §6.2 implies — a pre-registered failure mode, and it points at the corpus, not the test.

**Must not be said:** that a 0% rate is good news on its own. A test that fires on nothing clears this gate for the wrong reason. It becomes good news only beside recall on the planted corpus (cycle 5), and that pairing is the honest claim to take to a design partner.

## What it opens

1. **TD-012 sharpened.** Not only *which* reading binds (point, interval, envelope) but what the band's floor *means*. A ceiling breach is a trust failure; a floor breach is a power diagnostic. Kickoff ruling.
2. **Corpus width.** More independent calendar windows, or a longer series, if the gate is to be established at §6.2's precision. Costs nothing in fits to plan; costs a rebuild to produce.
3. **The clean class is not yet a control for population-dependent tests.** Its trips-per-day density differs from the real series, which is why 0 of 133 three-hundred-trip clean histories were evaluable against 78 of 200 adversarial.
4. **Recall.** The other half of the sentence.
