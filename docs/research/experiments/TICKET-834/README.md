# TICKET-834 — T-001's research rows: pre-register or decline

Hand-off from the Scope feedback loop to the research loop; runs on the research calendar, not in a sprint. Rules shared by every file: [`_common.md`](_common.md).

| Row | Claim (T-001's, figures in the tracker) | Outcome | Test | Blocked by | Ruling (Pawan) |
|---|---|---|---|---|---|
| FB-0049 | NIFTY option price band at entry | **Decline** → candidate register | — | — | |
| FB-0050 | Crude win rate falls through the day | **Routed** pre-reg | B5 `sequence_decay` | framework lock | |
| FB-0058 | Crude 5–7 pm IST | **Routed** pre-reg | S1 `session_expectancy`, `us_overlap` bucket | framework lock | |
| FB-0059 | NIFTY half-hour windows | **Decline** → merged into FB-0058's S1 for crude; register for NIFTY | — | — | |
| FB-0078 | ₹ at risk per trade, and its 2026 change | **Decline** → candidate register (2026 shift set) | — | — | |
| FB-0097 | Mixing books hides the post-loss effect | **Routed** pre-reg | B2 `post_loss_expectancy` + P2 `leave_one_instrument_out` | framework lock | |
| FB-0012 | Ask a belief before the reveal | **Decline**: not a hypothesis; it is the gate instrument | TR-009 | — | |
| FB-0013 | Locked engine tag per day | **Decline**: a product feature, not a hypothesis | — | — | |
| FB-0109 | R8 / S5 wait on regime labels | **Routed**: already in the library | S5, R8 as written | TD-011, framework lock | |
| FB-0110 | Journal answers as R7 evidence | **Decline as evidence** (admissibility ruling) | R7 unchanged | — | |

**Also carried:** B1 `post_loss_latency` (M3, N-B, θ_min ratio ≤ 0.67, n_min 30/30, move PL-1) is the home for any cross-day re-entry-speed claim, per the TICKET-820 ruling. No new test is created for it.

**What this folder does not do:**
- add or change any library test, threshold, null or tier: `ai_may_not` in the framework, and a MAJOR version if a person does it;
- touch isolation;
- carry any trader figure.
