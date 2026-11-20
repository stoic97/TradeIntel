# Price series in production

Bar-derived figures read one 1-minute series per underlying, through `services/production/prices`
(TICKET-889). The bars convention is spec §4.7. Where the bars come from is ADR 008. Since
TICKET-997 every series is stored **one gzip file per trading day**.

## The layout

```
<SCOPE_MARKET_DIR>/                    data/market by default; /srv/scope/data/market on the server
  CRUDEOIL/
    manifest.json                      every day held: rows, sha256 of its text, what it was checked against
    2018/2018-10-01.csv.gz             the series' header and that day's bars, IST, start of minute
    ...
  NIFTY/ ...
  RELIANCE/2026/2026-11-19.csv.gz      a stock's day, fetched only when a trader's trades need it
```

- **Written only through `services/shared/market/day_store.py`**, which checks each day before it
  reaches disk and refuses with the day and the stamp, never a price: every stamp on a whole minute,
  rising and on that day; the session (MCX: its shape against `mcx_sessions.yaml`, a closed day with
  no bars, a full session opening at the open; NSE and BSE: the first bar at the open and no bars on
  a day the exchange closures call closed); and a day held already is replaced only when asked with a
  reason, which the manifest keeps. Each day records what it was checked against. A day older than any
  calendar we hold is `stamps only`: its session's shape can't be checked.
- **The manifest is the record.** Day files go to a temporary name and then `os.replace`; the
  manifest is replaced the same way, last. A day file the manifest doesn't list is never read.
- **Read one day at a time.** Nothing is read when the app starts. The first lookup for an
  underlying reads its manifest once; after that a lookup reads only its own day's file (about 7 KB,
  9 ms for crude on this laptop), checks it against the manifest's hash, and keeps the last 64 days in memory.
  Nothing ever reads the whole series.

Measured on the crude series (1,775,386 bars, 2,089 days): one 76 MB file took 5 s to open on every
start and was rewritten whole on every update; as day files it is 15 MB, opens with nothing, and an
update writes one small file a day.

## Turn an old single-file series into day files

```
uv run python scripts/split_series_by_day.py <series.csv> <UNDERLYING> [--out <folder>]
```

It opens the old file with its own checks (its manifest's digest, whole and rising stamps, the
session's usual first bar at the open), writes each day through the day writer, and proves nothing
moved: every row in exactly one day file, the rows adding up to the series' count and its manifest's,
and the day files joined in order equal to the file's rows byte for byte. Only then does it write the
manifest. It never writes over a folder that has one, and it prints counts and dates only.

## Add an underlying

1. Add an entry to `services/production/prices/underlyings.yaml`: the instrument profiles it measures,
   and its folder (named after it). Raise `version`, because imports record which mapping produced
   their figures. A share on NSE needs no entry: it is measured against the folder named after its
   symbol.
2. Put its day files and manifest in `SCOPE_MARKET_DIR/<folder>/`, written through the day writer.

No code changes. A series with no manifest, or one that says its bars aren't stamped at the start of
the minute, answers "no series for this underlying", and `Prices.why` says which. A day whose file no
longer matches its hash answers "no series" for that day, with the reason, and every other day still
answers.

## When something goes wrong

A missing, broken or unchecked series gives "no series for this underlying", and the fact shows "not
available". A lookup never raises into a request, and a trade is never skipped silently. Nothing is
fetched from a feed during a request.

## On the server

- **Where:** `/srv/scope/data/market`, which is where production's default (`data/market`, relative to
  `WorkingDirectory=/srv/scope`) already points. The app can write there (`ReadWritePaths=/srv/scope/data`).
- **First copy:** split the series on the laptop that holds it, then copy the folder up, for example
  `scp -r data/market/CRUDEOIL <server>:/srv/scope/data/market/`, and make it the `scope` user's.
  Nothing in the deploy fetches bars.
- **Staging reads production's folder, read only.** `deploy/staging.env.example` sets
  `SCOPE_MARKET_DIR=/srv/scope/data/market`. The staging unit can write only under
  `/srv/scope-staging/data`, so it can read production's days and never change them. Staging never
  fetches bars of its own.

## Backups, and the copy kept off the server

`deploy/backup.sh` backs up `scope.db` and `files/` only. **Market data is not in the nightly backup**:
it holds no trader's data, and recent days can be fetched again. But Fyers serves only about nine years
of minute bars, so the oldest days can't be fetched again once they age out. **Keep one copy of every
folder off the server** (the laptop that split it, or the off-box store), and refresh that copy when
the series grows.

## Never in git

The bars are the broker's data and the repository is public. `.gitignore` covers everything under
`data/market/` except `README.md` and `CROSSINGS.md`, and `tests/unit/repo/test_no_data_in_git.py`
fails if any other file there is tracked. Every pull through the fund's connection is a line in
`CROSSINGS.md`.
