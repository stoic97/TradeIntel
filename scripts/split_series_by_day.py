"""Split a single-file 1-minute series into one gzip file per day (TICKET-997).

    uv run python scripts/split_series_by_day.py data/market/crude_1m_current.csv CRUDEOIL

The day files and their manifest go to ``<out>/<UNDERLYING>/`` (``--out``, default
``SCOPE_MARKET_DIR`` or ``data/market``), the layout ``services/shared/market/day_store.py``
describes. What it does, in order, and what makes it stop:

1. **Opens the old series with its own checks** (``prices.layer.Series``): its manifest's digest,
   every stamp on a whole minute and rising, and the session's usual first bar at the open. A
   series that fails them is refused before anything is written.
2. **Writes each day through the one day writer**, which checks its stamps and, where a calendar
   covers the day, its session (MCX: ``mcx_sessions.yaml``; NSE and BSE: the first bar at the open
   and the exchange closures). A day it refuses stops the split.
3. **Proves nothing was lost or changed:** every row lands in exactly one day file, the rows add up
   to the series' row count and its manifest's, and the day files read back and joined in order,
   without their header lines, are the series' rows byte for byte (their sha256 over the header and
   the rows equals the file's).
4. **Only then writes the manifest**, keeping everything the old one recorded. Until it is written
   no reader sees any of the day files, so a refused split leaves nothing in use.

It never writes over a folder that has a manifest already, and it prints counts and dates only,
never a price. It reads the old file a day at a time, so it needs little memory.
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from services.production.prices import layer
from services.shared.market import closures
from services.shared.market import day_store as ds
from services.shared.market import series as ms

IST = timezone(timedelta(hours=5, minutes=30))


class Refused(Exception):
    """No manifest was written, and the message says why."""


def session_check(prices: layer.Prices, underlying: str,
                  calendar: dict[date, ms.SessionException] | None) -> ds.SessionCheck:
    """The day writer's session check for this underlying's exchange."""
    opens = prices.session(underlying)[0]
    exchange = prices.exchange(underlying)
    if exchange == "MCX":
        return ds.mcx_check(ms.load_calendar() if calendar is None else calendar, opens)
    known = closures.load().get(exchange)
    return ds.open_check(opens, known.closed if known else frozenset(), known.through if known else None)


def _days(path: Path):
    """The header line, then (day, rows) for each day in order, one day in memory at a time."""
    with open(path, "rb") as f:
        header = f.readline()
        yield header
        day, rows = None, []
        for raw in f:
            if not raw.strip():
                continue
            this = raw[:10]
            if this != day and rows:
                yield date.fromisoformat(day.decode()), rows
                rows = []
            day = this
            rows.append(raw if raw.endswith(b"\n") else raw + b"\n")
        if rows:
            yield date.fromisoformat(day.decode()), rows


def split(src: str | Path, underlying: str, out_root: str | Path, *, built: date,
          calendar: dict[date, ms.SessionException] | None = None,
          prices: layer.Prices | None = None) -> ds.DayManifest:
    src, out_root = Path(src), Path(out_root)
    prices = prices or layer.Prices(data_dir=out_root)
    try:
        old = layer.Series.open(underlying, src, prices.session(underlying)[0])
    except layer.Unusable as exc:
        raise Refused(f"{src.name} fails its own checks: {exc}") from None
    folder = out_root / underlying
    if (folder / ds.MANIFEST).exists():
        raise Refused(f"{folder} holds a manifest already; it is never split over")
    check = session_check(prices, underlying, calendar)

    store = ds.DayStore(folder, underlying)
    days = _days(src)
    header = next(days)
    rows = 0
    try:
        for day, day_rows in days:
            if day.isoformat() in store.days:
                raise Refused(f"{day} appears twice in {src.name}")
            store.put(day, header, day_rows, check=check)
            rows += len(day_rows)
    except ds.Refused as exc:
        raise Refused(str(exc)) from None

    counted = sum(e.rows for e in store.days.values())
    if not (rows == counted == old.manifest.rows):
        raise Refused(f"rows don't add up: {rows:,} read, {counted:,} in day files, "
                      f"{old.manifest.rows:,} in {src.with_suffix('.json').name}")
    joined = hashlib.sha256(header)
    for key in sorted(store.days):
        text = ds.read_day(folder, date.fromisoformat(key), store.days[key])
        joined.update(text[len(header):])
    if joined.hexdigest() != old.manifest.sha256:
        raise Refused("the day files joined in order are not the series' rows byte for byte")

    m = old.manifest
    return store.save(
        serves=m.serves, source=f"{m.source}; split into day files by scripts/split_series_by_day.py on {built}",
        roll=m.roll, clock=m.clock, interval=m.interval, built=built, sessions=m.sessions, as_of=m.as_of)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("series", type=Path, help="the single-file series, its manifest beside it as <name>.json")
    p.add_argument("underlying", help="the underlying's name in underlyings.yaml, which is also its folder")
    p.add_argument("--out", type=Path, default=layer.market_dir(), help="where its folder goes (default: %(default)s)")
    a = p.parse_args(argv)
    today = datetime.now(IST).date()
    try:
        m = split(a.series, a.underlying, a.out, built=today, calendar=ms.load_calendar())
    except Refused as e:
        print(f"refused, no manifest written: {e}", file=sys.stderr)
        return 2
    folder = a.out / a.underlying
    size = sum(ds.day_path(folder, date.fromisoformat(k)).stat().st_size for k in m.days)
    checked: dict[str, int] = {}
    for e in m.days.values():
        checked[e.checked] = checked.get(e.checked, 0) + 1
    print(f"{a.underlying}: {sum(e.rows for e in m.days.values()):,} rows in {len(m.days):,} day files, "
          f"{m.first_day():%Y-%m-%d} to {max(m.days)}, as of {m.as_of:%Y-%m-%d}, {size / 1e6:.1f} MB")
    print("  checked: " + ", ".join(f"{n:,} {k}" for k, n in sorted(checked.items())))
    print(f"  manifest sha256 {hashlib.sha256(ds.manifest_bytes(folder)).hexdigest()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
