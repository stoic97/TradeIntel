"""Bring the crude 1-minute series current, and keep it current (TICKET-893).

Run once a month (the runbook, ``docs/runbooks/crude-series.md``, has the line):

    uv run --with fyers-apiv3 python scripts/extend_crude_series.py --token-file <path to a Fyers token>

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
5. **Writes** the series (the held bytes unchanged, the new bars after them) and its
   manifest, and prints the line to add to ``data/market/CROSSINGS.md``.

The token is read from a file outside the repository and never written anywhere. Until
the fund and the product have separate accounts (ADR 002), the connection is the fund's,
so each pull is a market-data crossing and is logged like one.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.shared.market import series as ms

IST = timezone(timedelta(hours=5, minutes=30))
OVERLAP_DAYS = 10
MAX_OHLC_MISMATCH = 0.001
CHUNK_DAYS = 99  # the broker answers at most 100 days of 1-minute bars per request
MONTHS = ("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC")
DEFAULT_SERIES = ROOT / "data" / "market" / "crude_1m_current.csv"
FMT = "%Y-%m-%d %H:%M:%S"


class Refused(Exception):
    """The run wrote nothing, and the message says why."""


def manifest_path(series: str | Path) -> Path:
    return Path(series).with_suffix(".json")


def _history(client, symbol: str, start: datetime, end: datetime) -> dict:
    return client.history({"symbol": symbol, "resolution": "1", "date_format": "0",
                           "range_from": str(int(start.timestamp())), "range_to": str(int(end.timestamp())),
                           "cont_flag": "1"})


def near_month_symbol(client, today: date) -> str:
    end = datetime(today.year, today.month, today.day, 23, 59, tzinfo=IST)
    for ahead in range(4):
        y, m = divmod(today.month - 1 + ahead, 12)
        symbol = f"MCX:CRUDEOIL{(today.year + y) % 100:02d}{MONTHS[m]}FUT"
        if _history(client, symbol, end - timedelta(days=5), end).get("s") == "ok":
            return symbol
    raise Refused(f"no crude contract from {today:%b %Y} on is known to the broker")


def fetch(client, symbol: str, start: date, end: date) -> dict[datetime, list[str]]:
    """Bars from the start of ``start`` to the end of ``end``, IST naive, start of minute."""
    out: dict[datetime, list[str]] = {}
    s = datetime(start.year, start.month, start.day, tzinfo=IST)
    stop = datetime(end.year, end.month, end.day, 23, 59, 59, tzinfo=IST)
    while s <= stop:
        e = min(s + timedelta(days=CHUNK_DAYS), stop)
        r = _history(client, symbol, s, e)
        if r.get("s") != "ok":
            raise Refused(f"the broker refused {symbol} {s:%Y-%m-%d} to {e:%Y-%m-%d}: {r.get('message', r)}")
        for c in r.get("candles") or []:
            t = datetime.fromtimestamp(c[0], IST).replace(tzinfo=None)
            out[t] = [f"{float(v):g}" for v in c[1:5]] + [str(int(c[5]))]
        s = e + timedelta(seconds=1)
    return out


def _stamp(line: str) -> datetime:
    """A row's timestamp. Older rows write single-digit hours (``9:00:00``), so no fixed width."""
    return datetime.strptime(line.split(",", 1)[0], FMT)  # noqa: DTZ007 - the series is naive IST


def _held(data: bytes) -> tuple[dict[datetime, list[str]], datetime, datetime, int]:
    """The held bars of the last ``OVERLAP_DAYS``, the first and last bar, and the row count."""
    rows = data.decode("utf-8").splitlines()[1:]
    first, last = _stamp(rows[0]), _stamp(rows[-1])
    since = last.date() - timedelta(days=OVERLAP_DAYS)
    tail: dict[datetime, list[str]] = {}
    for line in reversed(rows):
        t = _stamp(line)
        if t.date() < since:
            break
        tail[t] = line.split(",")[1:]
    return tail, first, last, len(rows)


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


def extend(base: str | Path, out: str | Path, client, *, today: date,
           calendar: dict[date, ms.SessionException], built: date,
           base_source: str | None = None) -> ms.SeriesManifest:
    base, out = Path(base), Path(out)
    data = base.read_bytes()
    held, first, last, n_held = _held(data)
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

    newline = b"\r\n" if data.split(b"\n", 1)[0].endswith(b"\r") else b"\n"
    body = data if data.endswith(b"\n") else data + newline
    body += b"".join((t.strftime(FMT) + "," + ",".join(new[t])).encode() + newline for t in sorted(new))

    prior = manifest_path(base)
    before = (ms.read_manifest(prior).source if prior.exists()
              else base_source or f"{base.name}, {first:%Y-%m-%d} to {last:%Y-%m-%d}")
    m = ms.SeriesManifest(
        underlying="CRUDEOIL", serves=ms.CRUDE_SERVES, file=out.name,
        sha256=hashlib.sha256(body).hexdigest(), rows=n_held + len(new),
        first_bar=first, last_bar=max(new), as_of=as_of,
        source=(f"{before}; then the Fyers history API, {symbol} with cont_flag=1 (near-month continuous), "
                f"{added_from:%Y-%m-%d} to {as_of:%Y-%m-%d}, pulled {built:%Y-%m-%d}"),
        roll=ms.ROLL_CONVENTION, clock=ms.CLOCK, interval="1 minute", built=built, extended_from=added_from,
        sessions=tuple(f"{d:%Y-%m-%d} {seen}: {reason}" for d, seen, reason in check.listed),
    )
    tmp = out.with_name(out.name + ".part")
    tmp.write_bytes(body)
    os.replace(tmp, out)
    ms.write_manifest(m, manifest_path(out))
    return m


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
    p.add_argument("--series", type=Path, default=DEFAULT_SERIES, help="the series to extend (default: %(default)s)")
    p.add_argument("--base", type=Path, help="first run only: the file to start from, when --series does not exist")
    p.add_argument("--base-source", help="first run only: where --base came from, for the manifest")
    a = p.parse_args(argv)
    base = a.series if a.series.exists() else a.base
    if base is None:
        p.error(f"{a.series} does not exist yet: pass --base, the file it starts from")
    today = datetime.now(IST).date()
    try:
        m = extend(base, a.series, _client(a.token_file), today=today, calendar=ms.load_calendar(), built=today,
                   base_source=a.base_source)
    except Refused as e:
        print(f"refused, nothing written: {e}", file=sys.stderr)
        return 2
    print(f"{m.file}: {m.rows:,} bars, {m.first_bar:%Y-%m-%d} to {m.as_of:%Y-%m-%d}, sha256 {m.sha256}")
    for s in m.sessions:
        print("  ", s)
    print("\nAdd to data/market/CROSSINGS.md:")
    print(f"| {m.built:%Y-%m-%d} | `data/market/{m.file}` | Fyers history API, near-month continuous, "
          f"through the fund's connection | - | `{m.sha256}` | MCX crude 1-min OHLCV, added "
          f"{m.extended_from:%Y-%m-%d} to {m.as_of:%Y-%m-%d}. Prices only. |")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
