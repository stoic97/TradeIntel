# Scope v1 — definitions reconciled

*PRD v1.2 §12 step 0 · 16 October 2026 · Owner: founder · Status: binding for phases 1–5. Sources: `scope_prd_v1_2_frozen.md` (§2, §5, §6.3, §7.2, Appendix A), `services/research/library/b2.py` (docstring and `population_and_condition`), `services/shared/schemas/ctr_v1.py`. Rules marked **(closed here)** fill a gap the PRD leaves; the founder may overrule any of them before phase 3 starts.*

Three things count the same behaviour — the Mirror, the Journal and the research library. This page is what makes them count it once.

## 1. Trading day

- The **trading day** of a round trip is the calendar date of its **entry** in the instrument profile's timezone. Indian exchanges share IST, so a trader active on MCX and NSE gets one IST day. Other exchanges use their own timezone from their profile. (PRD §7.2, Appendix A.)
- An **eligible day** is any trading day with at least one trip in the upload. The first and last days of an upload are included and may be partial; the drawer shows the upload boundary. (Appendix A.)
- A **normal day** is the median trip count over eligible days. (Appendix A.)
- A day is **complete** when the upload contains a later trading day, or the export date is after that day. (PRD §7.2.) **(closed here)** The export date comes from the file when the adapter can read one; otherwise the trader states it on the upload form, pre-filled with the upload date, and the import records which source it came from. An upload whose export date is unknown and whose last day has no later day leaves that last day incomplete until a later upload.

## 2. "Two straight losses" is the research library's B2 condition — one function

Verbatim from `services/research/library/b2.py`, which is the pre-registered definition:

- **Population:** round trips with **≥ 2 same-day prior round trips resolved before entry**. *Resolved* means exited before this entry (`exit_at < entry_at`); an overlapping trip does not count, however it later ends. Losses do not carry across the day boundary.
- **Condition:** the **two most recent resolved trips before entry** (by exit time) were both losses.
- A trip with net = 0 among the two most recent breaks the run. Two losses, then a win, then a trade: not in the condition. "Any two losses that day": not the condition. (Appendix A.)
- **A scratch between two losses suppresses the condition for the two trades that follow it** — verified against the function on 16 Oct 2026. With loss, scratch, loss, trade: the third trip's two most recent resolved priors are the scratch and the first loss, and the fourth's are the second loss and the scratch, so neither is in the condition. Both are in the population. (`tests/unit/shared/test_b2_condition.py::test_a_scratch_trade_between_two_losses_breaks_the_run`.)

**The function** is `population_and_condition(obs)`, today in `services/research/library/b2.py`, moved byte-for-byte in phase 1 to `services/shared/conditions/b2_condition.py` and imported from there by the research module. The Mirror (§6.3), the Journal (§7.4) and the research B2 test all call it and nothing else. The research test passes R in the `r` slot; the Mirror and Journal pass **net result in rupees** — the function reads only the sign, so the population and condition are identical by construction, and a unit test asserts it on the fixture.

- **Net** is gross − fees (`ctr_v1.RoundTrip.net_pnl`). When the export carries no fees, fees are zero, net equals gross, and every money figure is labelled *gross*. (PRD §5.3, Appendix A.) **(closed here)** The loss test is on this same net figure in both cases; the label changes, the arithmetic does not.
- **Win / loss:** net > 0 / net < 0. Net = 0 is neither: excluded from rate and median-by-outcome metrics, counted in totals. (Appendix A.)

## 3. Journal unit

- **Density default, per upload:** if the median eligible trading day has ≥ 2 trips, the unit is the trading day; otherwise it is per 10 trips. Recorded on the import. (PRD §2, §7.2, Appendix A.)
- **The trader's own setting overrides** from the moment it is set: `day` · `week` · `per_n_trips` with N. (PRD §7.2.)
- **(closed here)** A *week* is the ISO week (Monday–Sunday) of the trading day, in the same timezone as the day. A week is complete when the upload contains a trading day in a later week, or the export date is after the week's Sunday.
- **(closed here)** *Per N trips* groups trips in entry-time order into consecutive runs of N; a group is complete only when it holds N trips. A trailing group with fewer than N waits for a later upload. The density default's N is 10; the trader's N may be any integer ≥ 2.
- **Day-based Mirror sections (§6.1, §6.3, §6.5)** switch to their per-trade equivalents under the same density rule — fewer than two trips on the median eligible day — and only then. The threshold is a product constant, fitted to no history. (PRD §2.)

## 4. Import outcome — three states, never a fourth

The enum has exactly three values: `REJECTED`, `ACCEPTED_WITH_EXCLUSIONS`, `ACCEPTED_PARTIAL_FIELDS`. (PRD §5.3.)

- `REJECTED` when no adapter matches the header, or the format check finds no time-of-day, no prices or no quantities, or every row is rejected by the adapter. **(closed here)** on the last clause: a file with rows but zero parsable fills cannot proceed. The message names what the file appears to be, the missing field, and — from the file map — the export to send and where it lives.
- **(closed here) Precedence when both apply:** if any row or trip is excluded, the state is `ACCEPTED_WITH_EXCLUSIONS`; `ACCEPTED_PARTIAL_FIELDS` is the state only when nothing is excluded and a field some metrics need is absent. Partial fields are recorded on the import and labelled where they appear **in every accepted state** — the label does not depend on the state name.
- **(closed here) A clean file** (nothing excluded, every field present) is `ACCEPTED_WITH_EXCLUSIONS` with an exclusion count of zero, shown as "0 rows set aside". There is no fourth state.

## 5. Risk budget declaration

- Fields: value · unit (rupees or % of trading capital) · `effective_from` (trader-set, may be in the past) · `declared_at` (system time). A declaration whose `effective_from` precedes its `declared_at` is **retrospective** and the record says so. Full history kept. (PRD §5.5.)
- **(closed here)** A **% declaration requires the trading capital in rupees** as of `effective_from`; the form will not save a percentage without it, because without it no trip has a rupee denominator. The rupee value is derived at use time and labelled as derived from the percentage.
- **(closed here) The declaration in force at a trip's entry** is the one with the latest `effective_from` ≤ the trip's trading day; among equal `effective_from`, the latest `declared_at`. A trip in no declaration's range has no declared-budget denominator (`risk_unit_source = unavailable` unless a stop or premium applies).

## 6. The Appendix A fixture — specification

Lives in `tests/fixtures/mirror_contract/`. Regenerated from code (`generate.py`, deterministic, no randomness — every trip is written out explicitly), never from a real export; a test fails if the committed output differs from a fresh regeneration (Manual §7.6: regenerate, never edit). Expected values live in `expected.json`, **written by hand from Appendix A's formulas**, never copied from program output (Manual §5.4).

Three synthetic histories:

| File | Trips | Purpose |
|---|---|---|
| `main.json` | 40 | Every Appendix A row with known answers |
| `share_positive_total.json` | small | A positive overall total with negative worst days → no percentage; the offset sentence |
| `share_over_100.json` | small | Total −100 with worst five summing to −500 → no percentage; "the other N days were net +400" |

`main.json` must contain, each with its hand-calculated answer: ≥ 6 eligible days, one with a single trip · a day whose count is several times the normal day · the share-of-total in the (0%, 100%] regime · two losses then a win then a trade (not in the condition) · a scratch trade between two losses (not in the condition) · an overlapping trip that is not resolved · a net = 0 trip (excluded from strike rate and medians, counted in totals) · an entry hour with fewer than 5 trips (small-sample flag) · a losing run that crosses a day boundary · trips carrying each `risk_unit_source` value the product can write (`declared_budget`, `defined_stop`, `premium_paid`, `unavailable`) · a median-holding-time ratio that is defined, and the case where one median is zero ("—").

The three duplicate fixtures (repeated legitimate fills · a duplicated block · an overlapping re-export) are raw-file fixtures and live in `data/fixtures/duplicates/`; they test ingestion, not the Mirror.

## 7. Product constants named here

density threshold = 2 trips on the median eligible day · Journal surface = latest 5 · WTP floor = second upload or 14 days · WTP price = ₹500 placeholder · default N = 10. All in one module, each with its argument; changed by the kickoff, never fitted to a history. (PRD §13.4, §14.)
