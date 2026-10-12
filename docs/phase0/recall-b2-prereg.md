# B2 recall — predictions, written before the run

*12 October 2026 · null rate known (0 of 411), recall unknown*

The null sweep said B2 does not invent leaks. It cannot say whether B2 finds
real ones. This run is the other half, and the two must be read together: a
test that fires on nothing passes Class B for the wrong reason.

72 planted histories — B2 at 1x, 2x and 4x theta_min, at 100, 300 and 1,000
trades, 8 seeds each.

## Predicted

| Quantity | Prediction |
|---|---|
| Evaluable at 100 trades | **0 of 24** — same structural bar as the nulls |
| Recall at k=1 (0.25R, exactly theta_min) | **10–40%** |
| Recall at k=2 (0.50R) | **60–90%** |
| Recall at k=4 (nominal 1.0R, saturating at 0.78R) | **85–100%** |
| Monotonic in k | yes |
| Any fire in the wrong direction | **none** |

## Why low recall at k=1 is the correct answer

theta_min is defined as the smallest effect worth telling a trader about, and
promotion requires the shrunk training median to *clear* it. An effect sitting
exactly on the threshold should therefore be caught about half the time at
best — the estimate lands either side with roughly equal chance.

This is the cross-check that makes the null result meaningful. Recall near 90%
at k=1 would mean the promotion rule is too loose, and would sit badly beside
zero false positives in 411 nulls: a rule cannot be both that sensitive and
that silent unless something is wrong. Recall near 0% at k=2 would mean the
opposite — the test is not dead but deaf, and the 0% null rate would be
explained by a test that cannot fire at all.

The result we want is a visible climb from k=1 to k=4. The shape matters more
than any single number.

## Falsifiable

* Recall at k=4 below 50% — B2 cannot reliably find an effect three times its
  own threshold, and the test is not shippable as written.
* Recall flat across k — the promotion rule is not responding to effect size,
  which would undermine every tier above Exploratory.
* Any fire in the wrong direction — a worse failure than missing one, because
  it would mean the engine can tell a trader the opposite of the truth.

## Caveat carried from the null run

These 72 histories also index into the one crude series, so their outcomes are
correlated and the per-cell intervals (8 seeds, fewer once starved) are wide.
Recall is reported with Wilson intervals and the clustering stated; the shape
across k is the evidence, not any single cell's point estimate.
