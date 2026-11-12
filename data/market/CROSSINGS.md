# Fund -> product data crossings (ADR 002)

Market data only. One-way. The data files are gitignored; this log is the record.

| Date | File | Source (fund repo) | Fund commit | SHA-256 | Contents |
|---|---|---|---|---|---|
| 2026-10-05 | `data/market/crude_1m.csv` | `plus_ev_code_base/services/backtest/data/input/Crude/1min/crude_1m.csv` | `1dfc1251` | `57e17bc53c728d43129f4c10a5ad1e6fd3dcf1a8b4ca2cc38eba88b51605519d` | MCX crude 1-min OHLCV, continuous (stitched), 2018-10-01 to 2025-12-24, 1,861 days. Prices only - no strategy outputs, signals or positions. |
| 2026-11-12 | `data/market/crude_1m_current.csv` | `plus_ev_code_base/services/backtest/data/input/Crude/1min/crude_1m.csv` to 2025-12-24 (sha256 `67b217869d9297fb0397907b849101729295b64a8885c353aab051a19dacfbbc`, the TICKET-658 repair), then the Fyers history API's near-month continuous future through the fund's connection, 2025-12-26 to 2026-11-11 | `325d324c` | `8a8a83a341b96991e2f8bc02d427a5277e91fe6968ddb99ed2115d0be63cd0de` | MCX crude 1-min OHLCV, near month, not back-adjusted, 2018-10-01 to 2026-11-11, 1,775,386 bars. Built by `scripts/extend_crude_series.py`; roll convention and refresh in `docs/runbooks/crude-series.md`. Prices only. |
