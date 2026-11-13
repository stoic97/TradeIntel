# ADR 008: Market data comes from the Fyers connection we already use

**Status.** Accepted on merge. **Date.** 2026-11-13. **Deciders.** Founder (TICKET-894).

## Context

The round-2 run measured T-001's entries against NIFTY 1-minute bars from the Fyers history API, and the
crude series has been current through the same API since TICKET-893. The ticket asked four questions
before the finding is shown beyond T-001. They are answered here once, so the series layer and the
screen can be built against one answer.

## Decision

**Bars for every instrument family come from the Fyers API connection already in use.** That covers
NIFTY, NIFTY BANK, SENSEX, NSE stocks, and MCX crude, gold and silver. We open no new account and buy
no separate feed. Founder, 13 Nov 2026: "we already have API connections that we are using, so do not
overcomplicate".

1. **Display.** Bar-derived figures, which are counts rather than prices, may be shown to traders and
   on the demo from this connection. For the record, Fyers' API terms §12 ask for Fyers' written
   consent to display or derive from API content for third parties. The founder has ruled on the
   source with that known.
2. **Cost.** Flat in traders. There is one series per underlying (spec §4.7.3), so requests grow with
   underlyings, not traders, and 20 and 200 traders cost the same. A 9-year 1-minute backfill is about
   34 requests of 100 days, then one request a day per underlying. That is far inside the data API's
   5,000-a-day limit. Going over the per-minute limit more than 3 times in a day blocks the account for
   the rest of that day, so fetches are paced.
3. **Account.** It is the existing connection, with the token renewed each trading day. If it lapses,
   no new bars arrive. Each series stops at its manifest's `as_of`, and a claim about a later date
   refuses itself (spec §4.7.6, `SeriesManifest.covers`). No report goes silently wrong.
4. **Fallback.** None is needed while the connection serves. If it ever stops, the facts show their
   "not available" state, as they do when a series doesn't cover a trader's dates.

## What the connection serves (measured 13 Nov 2026)

These come from read-only `history` calls on the connected account. Only counts and dates were
recorded.

| Family | 1-minute history available |
| --- | --- |
| NIFTY 50, NIFTY BANK | From 14 Nov 2017, a rolling 9 years |
| NSE single stocks | From 14 Nov 2017 (checked on one large stock) |
| SENSEX | From 28 May 2019, when the data starts |
| Crude, gold, silver | Asked with the near-month contract and `cont_flag=1`. Crude is in `crude_1m_current.csv`. Gold and silver both returned 2020 bars. |

A trader uploading five years of history is covered for every family except SENSEX before mid-2019.
Such a trade gets the "not covered" state.

## Alternatives considered

- **A licensed vendor feed.** Rejected for now. It is a second source to pay for and run, while the
  existing connection already serves every family at 1-minute.
- **A coarser interval where 1-minute is missing.** Rejected by spec §4.7.1, which allows one interval
  and no fallback.
