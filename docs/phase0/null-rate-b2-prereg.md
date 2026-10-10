# B2 null rate — predictions, written before the full run

*10 October 2026 · 60-history smoke run complete, 1,000-history run not yet started*

Two predictions this session were falsified by their own runs (the nu floor, the
centred parameterisation), and both times the record of what we expected is what
made the result readable. Same discipline here, before a 40-minute sweep.

## Predicted

| Quantity | Prediction |
|---|---|
| Evaluable adversarial nulls | 250–330 of 600 |
| Fires | 0–4 |
| Rate | 0–1.5% |
| Wilson upper bound | below 2% |
| Verdict | **below the band** |
| Interval authority | binomial, *if* fires are 0 — the cluster bootstrap cannot express uncertainty when every cluster has zero fires |
| Clean class | materially fewer evaluable than adversarial at the same trip count |

## Why "below the band" is not a failure

The [2%, 8%] band has a floor, which implies a test should sometimes fire on
noise. A ceiling breach and a floor breach are not the same kind of news:

* **Above 8%** — the engine invents leaks. Fatal to trust; nothing ships.
* **Below 2%** — the engine is more conservative than the spec anticipated.
  This is only bad news if recall on planted histories is *also* poor, in which
  case the test is dead rather than careful. Zero false positives beside good
  recall is the best available outcome, and the band's shape cannot express it.

So the floor is a **power** diagnostic, readable only beside the recall curves
(cycle 5), not a trust gate. This reading is wider than TD-012, which asks
whether the band binds on the point estimate or the interval; it asks what the
floor *means*. Both go to the kickoff.

## Falsifiable

If the rate comes back above 8%, this document is wrong and B2 is not shippable
as written. If it comes back inside [2%, 8%], the band fits and TD-012 decides
the rest. If evaluable histories fall below 200, the corpus cannot support this
gate at the precision §6.2 implies and the corpus is what needs fixing.
