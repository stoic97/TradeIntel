# TICKET-852 · decline (to the candidate register)

*Drafted for the ruler (Pawan). Nothing here is a verdict. Rules shared with the earlier research hand-off: [`../TICKET-834/_common.md`](../TICKET-834/_common.md).*

**The question.** After two straight losses, do a trader's next trades do *better* than his other qualifying trades? It came from reading B2's shuffle test on one real file. The figures stay in Jira (README rule 1).

**Declined, for four reasons:**
- **It isn't a core test.** B2 is registered in one direction, `<`: trades after two losses doing worse. The opposite direction is a different question. A new test is a MAJOR version, Phase 0 builds none (Annex B), and `governance.ai_may_not` bars this draft from adding one.
- **It was seen before it was asked.** The direction was visible in the generating sample before anyone chose to look for it, so that sample can't also be its evidence (`_common.md`).
- **The one reading isn't strong.** It doesn't clear 0.05 when read both ways around the shuffled centre (see below), and no split of that file is strong on its own. Those splits were chosen after seeing the result, so they describe it and don't test it.
- **A higher mean isn't a good outcome.** Both groups can lose money and this still be true. Read as "trade on after two losses", it would be a move the evidence doesn't support, and the core has no move for it.

**Candidate register line (Annex B, Behaviour):** *B13 (id proposed) post-loss rebound: expectancy after two straight losses above the comparison, the reverse of B2. Seed: TICKET-852. Dormant. If it's ever built, the direction, null and bar are fixed before any look, and it's tested on histories that didn't suggest it.*

**Revisit when:** the core has passed §13.3, or B2's P1 and P2 reads on other cohort histories show a sign opposite to `<`.

**What this doesn't change:**
- **The gate on Chapter 3's post-loss sentence** (`production_gates.B2_post_loss_sentence`) stays one-sided in B2's direction, and a result the other way keeps it closed.
- **No test, threshold, null or tier.** This is a document only.

## For the research seat: N-B doesn't centre on zero for B2's difference

This came up while reading the result, and it applies to any reader of N-B on this statistic, whatever is ruled above.

N-B holds each day's total fixed. So once two trades in a day have lost, what's left of that day's outcomes runs better, and shuffling alone puts the condition ahead of the comparison. On a clean synthetic file with no effect planted (1,200 trades, standard deviation ₹1,000 per trade, 800 draws), the shuffled difference centres on +₹24, with a standard deviation of ₹69.

What follows from that:
- **A distance from zero isn't a fair two-sided figure.** One tail is much nearer than the other, so that figure is close to a one-sided p with the wrong label. An earlier reading of the real file made this mistake. It's corrected in Jira.
- **The size of an effect should be read from the shuffled centre, not from zero.** The raw gap between the two means overstates it in this direction, and understates it in B2's.
- **The production gate is unaffected.** It compares a file with its own shuffles, one-sided.
- **Not checked:** whether `engine/evidence.py`'s use of the 1.65 shuffle inflation, or the M1 fit, needs to take this into account. That's a question for the research seat, and this draft changes neither.

**Ruling (Pawan):** ______ · date ______
