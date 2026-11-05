# FB-0097 → B2 `post_loss_expectancy` with P2 · routed pre-registration

*Runner: Harshad · Ruler: Pawan · Shared rules: [`_common.md`](_common.md)*

**The claim (T-001):** mixing books hides it. After two straight losses, one book does better and the other worse, so the pooled figure cancels out.

**The question, as pre-registered.** B2 as the library defines it: expectancy, in R, of a trade taken after the two most recent same-day resolved trades both closed at a loss (`services/shared/conditions/b2_condition.py`, Annex A.1). The claim is a statement about B2's **P2** check, leave one instrument out, which already exists. P2 applies when at least two instruments each carry 15% or more of the trades. A per-book effect of opposite sign is what P2 exists to catch, and it **fails robustness**; it does not create two findings. No per-book B2 test is added.

| Field | Value (from `library: B2`, `evidence.robustness`) |
|---|---|
| Model | M1 |
| Null | N-B |
| θ_min | 0.25 R |
| n_min | 30 condition / 60 comparison |
| Family | F-Behaviour |
| Robustness | P1, P4, P5, P6, P7 mandatory; **P2 is the claim's own check**; P3 if it applies |
| Instrument | Crude is the confirmatory read. A NIFTY book enters P2 only as a split of the same history; NIFTY's own calibration waits (`scope.transfer_rule`) |
| Move if it reaches Likely | PL-1 (after two losses wait 30 min; merged with R2) |
| Data window | As `_common.md` |
| Kill | Framework kills plus `_common.md`, plus P2 failing (sign flips between instruments) blocks Established |

**Registered with FB-0078?** The ticket asks for the two together as the "2026 shift" set. FB-0078 is declined (see its file). The year half of the shift is read by B2's own **P1** temporal-halves check, already mandatory, so nothing is lost.

**Ruling (Pawan):** ______ · date ______
