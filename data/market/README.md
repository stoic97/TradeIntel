# data/market

Market data lives here on a machine that holds it, and never in git: the bars are the broker's
data and this repository is public. Only this README and `CROSSINGS.md` are tracked
(`tests/unit/repo/test_no_data_in_git.py` fails if anything else is).

One folder per underlying, one gzip file per trading day (TICKET-997):

```
data/market/
  CRUDEOIL/
    manifest.json            every day held: rows, sha256 of its text, what it was checked against
    2018/2018-10-01.csv.gz   the series' header line and that day's 1-minute bars, IST, start of minute
    ...
  NIFTY/ ...
  RELIANCE/ ...              a stock's days, fetched only when a trader's trades need them
```

Days are written only through `services/shared/market/day_store.py`, which checks them first.
`scripts/split_series_by_day.py` turns an old single-file series into this layout. The runbook
is `docs/runbooks/price-series.md`; every pull through the fund's connection is a line in
`CROSSINGS.md`.
