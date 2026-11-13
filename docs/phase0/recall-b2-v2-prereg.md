# B2 recall, second run — predictions, written before the run

*14 November 2026 · TICKET-897 · M1 with nu floored at 2 and one escalated
attempt per zone. The 12 October run and its pre-registration stand; this is a
different model and a different register, not a correction of that file.*

The first run reported 62.5% recall at k=2. That number was the statistical
core before the gate that decides whether a Finding exists: all five histories
that reached it carried `kill: failed_diagnostics`, so **shippable recall was
zero** and the register quoted the flattering half. This run reports both, and
the honest one is the headline.

## What changed in the engine

* `nu` is floored at 2, because the posterior is improper without it on any
  history with a large tie group, and corpus A is 49–55% tied at −1R.
* A history whose tie bound the floor cannot clear is refused, not fitted.
* A fit the diagnostics refuse gets one harder attempt — double draws and
  warmup, `target_accept` 0.99, `maxdepth` 12, new seed. The three thresholds
  do not move.

## Predicted

| Quantity | First run | Predicted now |
|---|---|---|
| Diagnostics failures, 1,000-trip cells | 23 of 24 | **4 to 10 of 24** |
| Shippable recall, k=1 | 0% | 0–10% |
| Shippable recall, k=2 | 0% | **20–50%** |
| Shippable recall, k=4 | 0% | **0–25%** |
| Core recall above shippable, every cell | — | yes |
| Fits with `nu` within 0.1 of the floor | — | 40–70% |
| Median M1 theta / realised contrast | — | 0.3–0.7 |
| Fires in the wrong direction | none | none |

**Two of these are revised down from the TICKET-897 plan of 13 November,**
which predicted 40–80% at k=2 and 25–75% at k=4. The oracle run of 14 November
measured 1 of 3 and 0 of 3 on the 1,000-trip seeds. The plan's bands were
written before that measurement and are recorded here as falsified rather than
quietly restated.

## Why shippable recall stays low, and why that is the finding

Flooring `nu` makes the posterior a distribution. It does not make M1 estimate
the quantity the product promises. The planted leak acts mostly on the atoms —
at k=4 the condition group reaches target 2% of the time against 21% — and a
Student-t location discounts exactly that mass. Roughly 85% of each planted
leak lives in the atom shares and only ~15% in the continuous part, which is
the only part `theta` can see.

So a modest number here is the expected result of a correct fix to a different
problem, and it is the evidence for the model work that follows.

## Falsifiable

* **Shippable recall at k=4 of 50% or more** — the estimand diagnosis is wrong,
  the under-read was a sampler artifact after all, and the mixture model is not
  needed. This is the one that would overturn the plan.
* **Diagnostics failures above 10 of 24** — the escalated attempt is not doing
  its job and the budget rule needs rethinking, not adopting.
* **Any fire in the wrong direction** — worse than missing one, as before.
* **Core recall below shippable recall in any cell** — an accounting error.

## Carried unchanged from the first run

The 8 seeds per cell still index into the one crude series, so outcomes are
correlated and the per-cell Wilson intervals are narrower than the truth. The
shape across k is the evidence; no single cell's point estimate is.
