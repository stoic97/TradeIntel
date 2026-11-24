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

## Keeping it current: the market sync (TICKET-998)

`uv run python -m services.production.api.cli market-sync`, started by `deploy/scope-market.timer`
every ten minutes and at 00:15 IST (the units and the founder's one-time steps are in
`docs/runbooks/deploy.md`, "Market data"). Each run:

- uses the day's Fyers login, connected on `/admin` under **Market data** (one click when the app's
  registered redirect is `/admin/fyers/callback`, otherwise by pasting the address bar the login
  ended on). With no login, or an expired one, it records "needs login" and does nothing else;
- for NIFTY, BANKNIFTY, SENSEX, crude, gold and silver, asks for every finished session after the
  last day held, up to yesterday, never today's, at most 100 days a request and one request a
  second, waiting out a busy broker. Futures are asked with the near-month contract
  (`services/shared/market/fyers_history.py`, the same choice the extend script makes);
- writes each day through the day writer. A day it refuses is recorded with its reason, and the
  run carries on; the card on `/admin` shows it;
- fetches the stock days traders' trades need (`market_day_request`), one day each; a stock Fyers
  won't serve is given up after three tries, with the reason. Indices and commodities are never
  fetched a day at a time;
- records the run (`market_sync_run`): counts, dates and reasons, never a price.

An underlying with no day files yet is left alone until it is seeded with the split script. The
sync never builds a series from nothing a day at a time.

The day's login can place orders. It is kept only encrypted with `SCOPE_FILE_KEY`, decrypted only
by the sync, and never written to a log, a page, an error or the admin trail. The laptop's own
Fyers token file is for local checks only: never copy it to the server, a test or a log.

## Backups, and the copy kept off the server

`deploy/backup.sh` backs up `scope.db` and `files/` only. **Market data is not in the nightly backup**:
it holds no trader's data, and recent days can be fetched again. But Fyers serves only about nine years
of minute bars, so the oldest days can't be fetched again once they age out. **Keep one copy of every
folder off the server** (the laptop that split it, or the off-box store), and refresh that copy when
the series grows.

## Bar figures, worked out off the web app (TICKET-999)

Pages never read bars to work out a trade's figures. An upload adds one pending row
(`bar_figure_job`); `scope-market.service` runs `cli bar-figures` after `cli market-sync`, under
the same limits (`Nice=10`, `CPUQuota=50%`, `MemoryMax=200M`); pages read what it stored.

- **Per trade** (`bar_trade_figure`), in underlying points in the trade's direction, from the close
  of the entry minute: how far it went his way, how far against him, what he took, and the 30
  minutes after he clicked. Or the reason it has none: no single direction, no series, a crude
  contract month the near-month series doesn't follow, gold or silver (no month rule yet), or a day
  not in yet. Counted, never dropped.
- **Per underlying** (`bar_path_summary`): his median path, his middle half, up to 200 of his paths
  chosen evenly, and the median and middle 95% of one random moment per trade (same month and hour,
  at least 30 minutes from his entries, seeded from the trader and the import).
- **A stock's day the store lacks** is asked for in `market_day_request`; the next sync fetches it
  and the next run fills the trade in. A day the broker never serves ends as "the broker has no
  bars for this day".
- **Provenance** (`bar_figure_job.provenance`): the code version, the mapping version, and the
  sha256 of every day file read.
- "Delete everything" removes the job and the figures; the market files hold no trader data.

## Never in git

The bars are the broker's data and the repository is public. `.gitignore` covers everything under
`data/market/` except `README.md` and `CROSSINGS.md`, and `tests/unit/repo/test_no_data_in_git.py`
fails if any other file there is tracked. Every pull through the fund's connection is a line in
`CROSSINGS.md`.
