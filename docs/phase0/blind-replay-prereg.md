# Blind replay — what the score may claim, written before anyone plays

*13 November 2026 · written with the code (TICKET-924) · **Signed 13 November 2026 by Rikk,
holding the research seat for this test by his own ruling the same day.** Signed before any
real trader played. `services/production/replay/blind.py` records it as `PREREG_SIGNED = True`;
a change to anything above the signature is a new version, signed again.*

## The question

Does the trader's choice of when to enter carry any information about the next
`HORIZON_MINUTES` (15) minutes of the underlying, once hindsight is taken away?

## The draw, fixed here

* Cards: at most 10. Half are his own entries, half random moments.
* His entries: only those at least `OLD_AFTER_DAYS` (180) days old, with a single
  direction by the shared option direction rule, and a full window and horizon of bars.
* Random moments: one per real entry drawn, on the same underlying, in the same calendar
  month, at least 30 minutes from any of his entries, with a full window and horizon.
  Each random moment takes one of the drawn entries' directions, shuffled.
* The card shows the 60 one-minute bars before the moment and nothing from the moment on.
  The date and the time are not shown until the reveal.
* Seeded: `SEED` and the trader's key decide the draw.

## What is counted

* A **call** is one card answered. It is **right** when he took a card the underlying then
  moved his way over the horizon, or skipped one it didn't.
* Reported: the number of calls, the number right, and the band a fair coin gives on that
  many calls (95%, two-sided, binomial). The count is printed before anything else.
* On the cards he took: the underlying's points in his direction, **before charges**.

## What it may not claim

* No composite score, rating, percentage of skill or leaderboard, here or in anything
  built from it.
* No rupee figure, and no "would have saved" figure.
* A result inside the coin band says only that these calls can't be told apart from
  chance. A result outside it says his selection carried information on these cards, on
  this horizon, and nothing about why or about future trades.
* One session of 10 cards is too few to say much; the count is printed first so the reader
  sees that.

## Known limit, carried onto the page

About 89% of one-minute bars come out Normal under the current bar rules, so a sample of
only rare bars would misrepresent what a chart usually prints. The random moments are drawn
from every minute, so the cards hold ordinary bars as a chart does.

## Signature

| Seat | Name | Date |
|---|---|---|
| Research | Rikk | 13 November 2026 |
