# Price series in production

Bar-derived figures read one 1-minute series per underlying, through `services/production/prices`
(TICKET-889). The bars convention is spec §4.7. Where the bars come from is ADR 008.

## Add an underlying

1. Add an entry to `services/production/prices/underlyings.yaml`: the instrument profiles it
   measures, and its series file. Raise `version`, because imports record which mapping produced
   their figures. A share on NSE needs no entry: it is measured against `<symbol>_1m.csv`.
2. Put the series and its manifest in `SCOPE_MARKET_DIR` (default `data/market`, gitignored). The
   manifest is `<name>.json`, in TICKET-893's format, and `scripts/extend_crude_series.py` is the
   pattern for writing both.

No code changes. A series that fails its checks answers "no series", and `Prices.why` says which
check failed.

## What the layer checks when it opens a series

- The manifest says the bars are stamped at the start of each minute, and its digest matches the
  file.
- Every timestamp falls on a whole minute, and they strictly rise.
- On the most recent 120 days, the most common first bar of a day falls at the session's open
  (from the instrument profile). A series stamped at the end of each minute opens a minute late,
  and fails.

## Decisions

- **Where the bars live:** files on disk, not the database. Opening a series streams it once:
  8 years of crude, 1.77M bars, took 3.3 s and under 2 MB of memory on this laptop. After that, a
  lookup reads only its own day, about 6 ms, and the last 64 days stay cached. A trader with five
  years of history costs only the days he traded.
- **One series for every trader, held for every date it covers.** It is extended by the monthly
  refresh. Nothing is fetched from a feed during a request.
- **When something goes wrong:** a missing, broken or unchecked series gives "no series for this
  underlying", and the fact shows "not available". A lookup never raises into a request, and a
  trade is never skipped silently.

## Deploying a series

Copy the CSV and its manifest into `SCOPE_MARKET_DIR` on the server. That is the operator's step;
nothing in the deploy fetches bars.
