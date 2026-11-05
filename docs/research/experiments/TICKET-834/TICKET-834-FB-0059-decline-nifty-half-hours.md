# FB-0059 · decline (merged into FB-0058 for crude; register for NIFTY)

*Runner: Harshad · Ruler: Pawan · Shared rules: [`_common.md`](_common.md)*

**The claim (T-001):** on NIFTY, one half-hour window lost in both years, and another lost in 2026 only.

**Declined, for four reasons:**
- It is FB-0058's question, expectancy by time of day, on an instrument that isn't calibrated yet (`scope.transfer_rule`).
- Half-hour windows are about a dozen buckets chosen after the look, against S1's three fixed ones. That multiplies the comparisons, and at S1's n_min of 30 per bucket, few windows would even be evaluable.
- One of the two windows holds in one year only, which is the P1 temporal-halves failure before any test runs.
- The only history it was seen on is the generating sample.

**Where the honest version lives:** S1 with its fixed buckets (FB-0058's file), on crude now, and on NIFTY once that family is calibrated. No half-hour test is created.

**Ruling (Pawan):** ______ · date ______
