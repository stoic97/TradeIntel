"""Bring the crude 1-minute series current, and keep it current (TICKET-893).

Run once a month (the runbook, ``docs/runbooks/crude-series.md``, has the line):

    uv run --with fyers-apiv3 python scripts/extend_crude_series.py --token-file <path to a Fyers token>

It extends the day files in ``<SCOPE_MARKET_DIR>/CRUDEOIL/`` (TICKET-997), one gzip file per
session, written through ``services/shared/market/day_store.py``. The first time, split the old
single file into day files with ``scripts/split_series_by_day.py``.

What it does, in order, and what makes it stop:

1. **Finds the near month.** The broker serves its continuous future relative to the
   contract asked for, so asking with the nearest unexpired contract gives the near-month
   series (the roll convention in ``services.shared.market.series``). An expired contract is
   an invalid symbol to the broker, so the first month it still knows is the near month.
2. **Checks the seam.** It re-fetches the last ``OVERLAP_DAYS`` already held. Every close
   there must match the held bar exactly, and at most ``MAX_OHLC_MISMATCH`` of bars may
   differ in open, high or low. Otherwise the broker's construction is not the one the file
   was built with, and joining the two would put a step in the series that no market made.
3. **Keeps finished sessions only.** Today's session is still trading, so it is left for
   the next run.
4. **Checks every session added.** A weekday with no bars, a part session or a weekend
   session must be in ``mcx_sessions.yaml`` with a reason, or nothing is written.
5. **Writes** each new session as a day file (the held days untouched), then the manifest, and
   prints the line to add to ``data/market/CROSSINGS.md``.

The token is read from a file outside the repository and never written anywhere. Until
the fund and the product have separate accounts (ADR 002), the connection is the fund's,
so each pull is a market-data crossing and is logged like one.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.shared.market import day_store as ds
from services.shared.market import fyers_history as fh
from services.shared.market import series as ms

# The symbol choice and the request live in one place, shared with the server's sync (TICKET-998).
IST, CHUNK_DAYS, MONTHS = fh.IST, fh.CHUNK_DAYS, fh.MONTHS
Refused = fh.Refused
_history, near_month_symbol, fetch = fh.history, fh.near_month_symbol, fh.fetch
OVERLAP_DAYS = 10
MAX_OHLC_MISMATCH = 0.001
DEFAULT_FOLDER = ROOT / "data" / "market" / "CRUDEOIL"
SESSION_OPEN = time(9, 0)  # MCX_CRUDEOIL.yaml's session_start
FMT = "%Y-%m-%d %H:%M:%S"


def _stamp(line: str) -> datetime:
    """A row's timestamp. Older rows write single-digit hours (``9:00:00``), so no fixed width."""
    return datetime.strptime(line.split(",", 1)[0], FMT)  # noqa: DTZ007 - the series is naive IST


def _held(store: ds.DayStore) -> tuple[dict[datetime, list[str]], datetime, bytes]:
    """The held bars of the last ``OVERLAP_DAYS``, the last bar held, and the header line."""
    last_day = date.fromisoformat(max(store.days))
    since = last_day - timedelta(days=OVERLAP_DAYS)
    tail: dict[datetime, list[str]] = {}
    header, last = b"", None
    for key in sorted(store.days):
        if date.fromisoformat(key) < since:
            continue
        text = store.text(date.fromisoformat(key))
        header, rows = text.split(b"\n", 1)[0] + b"\n", text.decode("utf-8").splitlines()[1:]
        for line in rows:
            last = _stamp(line)
            tail[last] = line.split(",")[1:]
    return tail, last, header


def _seam(held: dict[datetime, list[str]], got: dict[datetime, list[str]]) -> None:
    both = sorted(held.keys() & got.keys())
    if not both:
        raise Refused(f"seam: the broker returned none of the bars held over the last {OVERLAP_DAYS} days")
    close = [t for t in both if Decimal(held[t][3]) != Decimal(got[t][3])]
    if close:
        raise Refused(f"seam: {len(close)} of {len(both)} held closes differ from the broker's, first at "
                      f"{close[0]:%Y-%m-%d %H:%M}; its continuous series is not the one this file was built with")
    ohl = [t for t in both if any(Decimal(held[t][i]) != Decimal(got[t][i]) for i in range(3))]
    if len(ohl) > MAX_OHLC_MISMATCH * len(both):
        raise Refused(f"seam: {len(ohl)} of {len(both)} held bars differ in open, high or low")


def extend(folder: str | Path, client, *, today: date, calendar: dict[date, ms.SessionException],
           built: date, session_open: time = SESSION_OPEN) -> ds.DayManifest:
    store = ds.DayStore(folder, "CRUDEOIL")
    if store.manifest is None:
        raise Refused(f"{Path(folder)} holds no day files yet: split the series first with "
                      "scripts/split_series_by_day.py")
    held, last, header = _held(store)
    symbol = near_month_symbol(client, today)
    got = fetch(client, symbol, last.date() - timedelta(days=OVERLAP_DAYS), today)
    _seam(held, got)

    new = {t: v for t, v in got.items() if last.date() < t.date() < today}
    if not new:
        raise Refused(f"nothing new: the series already runs to {last:%Y-%m-%d}, and today's session is unfinished")
    added_from, as_of = min(new).date(), max(new).date()
    check = ms.check_sessions(new, last.date() + timedelta(days=1), as_of, calendar)
    if not check.ok:
        raise Refused("sessions without a reason in mcx_sessions.yaml: "
                      + "; ".join(f"{d} {seen}" for d, seen in check.unexplained))

    newline = b"\r\n" if header.endswith(b"\r\n") else b"\n"
    by_day: dict[date, list[bytes]] = {}
    for t in sorted(new):
        by_day.setdefault(t.date(), []).append((t.strftime(FMT) + "," + ",".join(new[t])).encode() + newline)
    day_check = ds.mcx_check(calendar, session_open)
    try:
        for day, rows in by_day.items():
            store.put(day, header, rows, check=day_check)
    except ds.Refused as exc:
        raise Refused(f"a day was refused, and the manifest is unchanged: {exc}") from None

    before = store.manifest
    return store.save(
        serves=ms.CRUDE_SERVES, roll=ms.ROLL_CONVENTION, clock=ms.CLOCK, interval="1 minute", built=built,
        source=(f"{before.source}; then the Fyers history API, {symbol} with cont_flag=1 (near-month continuous), "
                f"{added_from:%Y-%m-%d} to {as_of:%Y-%m-%d}, pulled {built:%Y-%m-%d}"),
        sessions=before.sessions + tuple(f"{d:%Y-%m-%d} {seen}: {reason}" for d, seen, reason in check.listed),
        as_of=as_of,
    )


def _client(token_file: Path):
    import tempfile

    from fyers_apiv3 import fyersModel  # only the refresh needs the broker's library

    tok = json.loads(token_file.read_text(encoding="utf-8"))
    logs = tempfile.mkdtemp(prefix="fyers-")  # the library writes request logs; keep them out of the repo
    return fyersModel.FyersModel(client_id=tok["client_id"], token=tok["access_token"], is_async=False,
                                 log_path=logs + "/")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--token-file", type=Path, required=True, help="a Fyers token file, outside the repository")
    p.add_argument("--folder", type=Path, default=DEFAULT_FOLDER,
                   help="the crude day files to extend (default: %(default)s)")
    a = p.parse_args(argv)
    today = datetime.now(IST).date()
    before = ds.read_manifest(a.folder).days.keys() if (a.folder / ds.MANIFEST).exists() else set()
    try:
        m = extend(a.folder, _client(a.token_file), today=today, calendar=ms.load_calendar(), built=today)
    except Refused as e:
        print(f"refused, manifest unchanged: {e}", file=sys.stderr)
        return 2
    added = sorted(set(m.days) - set(before))
    rows = sum(e.rows for e in m.days.values())
    digest = hashlib.sha256(ds.manifest_bytes(a.folder)).hexdigest()
    print(f"CRUDEOIL: {rows:,} bars in {len(m.days):,} day files, {m.first_day():%Y-%m-%d} to "
          f"{m.as_of:%Y-%m-%d}; manifest sha256 {digest}")
    for s in m.sessions:
        print("  ", s)
    print("\nAdd to data/market/CROSSINGS.md:")
    print(f"| {m.built:%Y-%m-%d} | `data/market/CRUDEOIL/` | Fyers history API, near-month continuous, "
          f"through the fund's connection | - | `{digest}` (manifest) | MCX crude 1-min OHLCV, added "
          f"{added[0]} to {m.as_of:%Y-%m-%d}, {len(added)} day files. Prices only. |")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
