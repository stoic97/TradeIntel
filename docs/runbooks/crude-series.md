# The crude 1-minute series

Market context for a crude trade is read against one series: MCX crude, 1-minute bars. This page says
how the series is built, how to tell how current it is, and how to bring it current each month
(TICKET-893).

## Refresh it, once a month

```
uv run --with fyers-apiv3 python scripts/extend_crude_series.py --token-file <path to a Fyers token>
```

It extends `data/market/crude_1m_current.csv` from where the file ends to yesterday's session, and
prints a line to add to `data/market/CROSSINGS.md`. If it refuses, it has written nothing, and its
message says why: either the broker's bars no longer match the file at the join, or a session that
isn't a full session has no reason in `services/shared/market/mcx_sessions.yaml`. Add the reason
(from MCX's holiday list) and run it again. Don't loosen the check.

## What the series is

| | |
| --- | --- |
| File | `data/market/crude_1m_current.csv`, gitignored. Its manifest, `crude_1m_current.json`, sits beside it. |
| Instrument | MCX CRUDEOIL futures, near month. CRUDEOILM is served by the same series (below). |
| Interval and clock | 1 minute. IST, naive timestamps; each bar is stamped at the start of its minute. |
| Prices | Rupees a barrel, as traded. Columns: timestamp, open, high, low, close, volume. |
| To 24 Dec 2025 | The fund's `crude_1m.csv` at `325d324c`, byte for byte (the TICKET-658 repair included). |
| From 26 Dec 2025 | The Fyers history API, continuous future (`cont_flag=1`), asked with the near-month contract. |

### The roll convention

The series follows **the nearest unexpired CRUDEOIL futures contract, up to and including its last
trading day, then the next contract from the following session.** Prices are each contract's own and
are **not back-adjusted**, so a roll shows as a jump between one session's close and the next
session's open. A reader that compares prices across a roll has to allow for that jump. The same text
is `ROLL_CONVENTION` in `services/shared/market/series.py` and is written into every manifest.

This was checked, not assumed:

- **The old file is built the same way.** Over June to 24 December 2025, all 124,586 of its bars
  had a matching bar from the broker's near-month continuous series, and every close was equal. So
  the old part and the new part join with no seam.
- **It follows the expiring contract to its last day.** Against single-contract bars held from the
  live engine, the series matched the August contract to 19 August 2026 and the September contract
  from 20 August. It matched the November contract from 20 October.
- **The broker's continuous series depends on the contract asked for.** Asked with the second
  contract, it returns the next-month series instead, which differed from the old file by about 23
  points at the median. So the script always asks with the nearest contract the broker still knows.
  An expired contract is an invalid symbol to the broker.

### CRUDEOILM uses this series

The mini trades the same market in the same rupees a barrel, with a smaller lot. Over May to
November 2026, the mini's near-month bars fell on the same minutes as crude's. The median close
differed by 1 point, and 99% of closes were within 7 points. On minutes where crude moved 5 points
or more, the mini moved the same way 97% of the time, and the two rolled on the same days. The
manifest's `serves` lists both roots, so nothing should build a second series for the mini.

## How current it is

The manifest's `as_of` is the last complete session. `SeriesManifest.covers(day)` is the question to
ask before using a bar for a trade on `day`. When it says no, the claim says the series doesn't cover
that date. It never falls back to the nearest bar.

## Sessions that aren't full

Every calendar day from where the old file ended to `as_of` was checked. The script refuses to write
if any of these has no reason in `mcx_sessions.yaml`: a weekday with no bars, an evening-only or
morning-only session, or a weekend session. It also refuses if a day the calendar says was closed
traded a full session. The manifest lists every session that wasn't full, with its reason. The
extension through 11 November 2026 had:

- Four closed weekdays: Christmas, Republic Day, Good Friday and Gandhi Jayanti.
- Eleven evening-only sessions, on Indian holidays when the morning session was closed.
- The Union Budget session on Sunday 1 February.
- The Diwali muhurat hour on Sunday 8 November.

## What it doesn't touch

- `data/market/crude_1m.csv`, the file Corpus A is pinned to by its digest. It stays as logged
  on 5 October, so every synthetic history still regenerates exactly.
- The fund's own copy, which the fund's backtests read. Extending it would change the fund's
  results and spend its unseen months, so that is the fund's call, not this script's.
- Licensing, and every other series (TICKET-894, TICKET-889).

Until the fund and the product have separate accounts (ADR 002), the broker connection is the fund's.
So each pull is a market-data crossing, and it is logged in `CROSSINGS.md` like one.
