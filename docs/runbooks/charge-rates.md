# Statutory charge rates

STT, CTT, exchange transaction charges, the SEBI turnover fee, stamp duty and GST are kept as a
dated table, `services/production/charges/rates.yaml` (TICKET-911). Every row names the Act,
circular or notice that set it. Brokerage is not here (TICKET-912).

## When a rate changes

1. Read the circular, notice or Act. A broker's page is how we hear of a change. It is never the
   source of a row.
2. Add a row at the end of `rates.yaml` with:
   - the next `id`;
   - the new rate, as a quoted decimal fraction of its base;
   - `effective_from`, the date it takes effect;
   - `added`, today;
   - the `source`.

   **Never edit an existing row.**
3. Run `uv run python scripts/lock_charge_rates.py`. It pins the new row in `rates.lock`, and it
   refuses if an old row was changed.
4. Run the tests. `tests/unit/charges/test_rates_shipped.py` pins the real change dates. Add a
   test either side of the new date.

**A rate that was wrong** gets a correction row: the same `effective_from` with a later `added`.
Reads see the correction. A read made with `as_of` before it still gets the old answer, so an
old report reproduces.

## The stale-rate check

    uv run python scripts/check_charge_rates.py --webhook <the team's alert webhook>

It prices 14 made-up orders with the table and with the rates FYERS and Zerodha publish. If any
component differs by more than a paisa, or a page can't be read, it prints what moved, posts it to
the webhook (or `SCOPE_ALERT_WEBHOOK`), and exits 1. It never edits the table. Run it daily from
cron, away from the product. An alert means someone reads the circular and adds a row.

## What the table doesn't do

- **Before 1 Oct 2024 it refuses.** Until then, exchange charges were slabbed on each broker's
  monthly turnover, and what a trader was billed was the broker's choice. SEBI's "true to label"
  circular, SEBI/HO/MRD/TPD-1/P/CIR/2024/92, made them flat and the same for everyone from that
  date.
- **Stamp duty is one rate for every state.** Since 1 Jul 2020 the exchange collects it at a
  national rate and passes it to the buyer's state, so the trader's state doesn't change the
  amount.
- **Option exercise isn't covered.** That is STT or CTT on the settlement value. A trip the
  product reads is closed by a trade.
- **BSE SENSEX 50 and stock options aren't in `BSE_OPT`.** Their charge is 0.000005; the
  `BSE_OPT` rows are for SENSEX and BANKEX options.
- **Clearing charges aren't covered.** They are the clearing member's, not a statute's.
