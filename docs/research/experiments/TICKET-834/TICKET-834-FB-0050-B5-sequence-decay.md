# FB-0050 → B5 `sequence_decay` · routed pre-registration

*Runner: Harshad · Ruler: Pawan · Shared rules: [`_common.md`](_common.md)*

**The claim (T-001):** on crude, his win rate falls with each trade of the day.

**The question, as pre-registered.** Does expectancy, in R, decline with a trade's sequence number within the day? This is B5 as the library defines it. The test reads expectancy in R, not win rate. Win rate is the claim's framing, and a falling win rate with a rising payoff is no decline in expectancy. Testing win rate would be a new quantity, and so a new test.

| Field | Value (from `library: B5`) |
|---|---|
| Model | M6 |
| Null | N-B: outcomes permuted within day, holding day, day total, context, sizes and times |
| θ_min | 0.25 R |
| n_min | 40 trading days |
| Family | F-Behaviour (Benjamini–Hochberg, q from `evidence.multiplicity`) |
| Robustness | P1, P4, P5, P6, P7 mandatory; P3 (leave one session out) if it applies |
| Move if it reaches Likely | DL-1 (after the day's first two losses, done for the day). It requires B12 ≥ Likely, not B5 alone, so B5 informs DL-1 and does not unlock it |
| Data window | As `_common.md`: generating sample excluded; other cohort histories, and T-001's trades after 5 Nov |
| Kill | Framework kills plus `_common.md`. Also: a decline that appears only after a cap on trades per day (a sweep of the sequence boundary) is the P4 flip, not a finding |

**Ruling (Pawan):** ______ · date ______
