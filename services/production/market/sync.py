"""Keep the market data current on the server (TICKET-998): ``cli market-sync``, run by a timer.

Each run, for every underlying kept whole (the indices and the commodity futures, ``KEPT_WHOLE``),
asks the broker for every **finished** session after the last day held, up to yesterday. Today's
session is never asked for: it isn't finished. Each day goes through the one day writer
(``services/shared/market/day_store.py``), which checks it; a day it refuses is recorded with its
reason and the run carries on with the next. Then it fetches the stock days traders' trades need
(``MarketDayRequest``), one day each, giving a day up after three tries. Then it exits.

An underlying with no day files yet is named and left alone: its first copy is seeded by
``scripts/split_series_by_day.py``, never by a day-by-day fetch from nothing. A futures series is
asked for with the near-month contract (``fyers_history.near_month_symbol``, shared with the extend
script), so it is the same construction whichever one wrote the day.

What a run records (``MarketSyncRun``) and prints is counts, dates and reasons, never a price.
The caller hands in a history client that is already logged in and paced; nothing here reads
the login or sleeps.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from services.production.db import models as m
from services.production.prices import layer
from services.shared.market import closures as shared_closures
from services.shared.market import day_store as ds
from services.shared.market import fyers_history as fh
from services.shared.market import series as ms

near_month_symbol, fetch = fh.near_month_symbol, fh.fetch

KEPT_WHOLE: dict[str, tuple[str, str]] = {
    "NIFTY": ("index", "NSE:NIFTY50-INDEX"),
    "BANKNIFTY": ("index", "NSE:NIFTYBANK-INDEX"),
    "SENSEX": ("index", "BSE:SENSEX-INDEX"),
    "CRUDEOIL": ("future", "CRUDEOIL"),
    "GOLD": ("future", "GOLD"),
    "SILVER": ("future", "SILVERM"),
}
"""Every finished session of these is kept. A stock is fetched only for the days trades need."""
MAX_TRIES = 3
HEADER = b"timestamp,open,high,low,close,volume\n"
MARK = "market-sync (TICKET-998)"
WAITING, FETCHED, GAVE_UP = "waiting", "fetched", "gave up"


def folder_of(prices: layer.Prices, underlying: str) -> str:
    entry = prices.mapping.entries.get(underlying)
    return entry["folder"] if entry else prices.mapping.stocks["folder"].format(symbol=underlying)


def session_check(prices: layer.Prices, underlying: str, calendar: dict[date, ms.SessionException],
                  closures: dict[str, shared_closures.Closures]) -> ds.SessionCheck:
    """The day writer's session check for this underlying's exchange."""
    opens = prices.session(underlying)[0]
    exchange = prices.exchange(underlying)
    if exchange == "MCX":
        return ds.mcx_check(calendar, opens)
    known = closures.get(exchange)
    return ds.open_check(opens, known.closed if known else frozenset(), known.through if known else None)


def _header_of(store: ds.DayStore) -> bytes:
    if not store.days:
        return HEADER
    text = store.text(date.fromisoformat(max(store.days)))
    return text.split(b"\n", 1)[0] + b"\n"


def _by_day(bars: dict[datetime, list[str]], header: bytes, after: date, before: date) -> dict[date, list[bytes]]:
    newline = b"\r\n" if header.endswith(b"\r\n") else b"\n"
    out: dict[date, list[bytes]] = {}
    for t in sorted(bars):
        if after < t.date() < before:
            out.setdefault(t.date(), []).append(
                (t.strftime("%Y-%m-%d %H:%M:%S") + "," + ",".join(bars[t])).encode() + newline)
    return out


def _part_sessions(days: dict[date, list[bytes]], calendar: dict[date, ms.SessionException]) -> tuple[str, ...]:
    lines = []
    for day, rows in days.items():
        shape = ms._shape([ds._stamp(r) for r in rows])
        if shape != "full" and day in calendar:
            lines.append(f"{day:%Y-%m-%d} {shape}: {calendar[day].reason}")
    return tuple(lines)


def _one(client, root: Path, underlying: str, today: date, prices: layer.Prices,
         calendar: dict[date, ms.SessionException], closures: dict) -> dict:
    kind, name = KEPT_WHOLE[underlying]
    folder = root / folder_of(prices, underlying)
    if not (folder / ds.MANIFEST).exists():
        return {"added": 0, "refused": [], "note": "no day files yet: seed it with scripts/split_series_by_day.py"}
    store = ds.DayStore(folder, underlying)
    held = store.manifest
    start, end = held.as_of + timedelta(days=1), today - timedelta(days=1)
    if start > end:
        return {"added": 0, "refused": [], "last": held.as_of.isoformat(), "note": "current"}
    try:
        symbol = near_month_symbol(client, today, root=name) if kind == "future" else name
        bars = fetch(client, symbol, start, end)
    except fh.Refused as exc:
        return {"added": 0, "refused": [], "last": held.as_of.isoformat(), "broker": str(exc)}

    header = _header_of(store)
    days = _by_day(bars, header, held.as_of, today)
    check = session_check(prices, underlying, calendar, closures)
    added, refused = [], []
    for day, rows in days.items():
        try:
            store.put(day, header, rows, check=check)
            added.append(day)
        except ds.Refused as exc:
            refused.append((day.isoformat(), str(exc)))
    if added:
        source = held.source if MARK in held.source else (
            f"{held.source}; then {MARK}: the Fyers history API, near-month continuous for futures "
            f"(cont_flag=1), from {min(added):%Y-%m-%d}")
        store.save(serves=held.serves, source=source, roll=held.roll, clock=held.clock, interval=held.interval,
                   built=today, sessions=held.sessions + _part_sessions({d: days[d] for d in added}, calendar))
    return {"added": len(added), "refused": refused, "first": min(added).isoformat() if added else None,
            "last": max(store.days)}


def _stock_days(sess: Session, client, root: Path, today: date, prices: layer.Prices,
                closures: dict, now: datetime) -> dict:
    counts = {FETCHED: 0, GAVE_UP: 0, WAITING: 0}
    for req in sess.scalars(select(m.MarketDayRequest).where(m.MarketDayRequest.status == WAITING)
                            .order_by(m.MarketDayRequest.id)).all():
        day = date.fromisoformat(req.trading_day)
        req.updated_at = now
        if req.underlying in KEPT_WHOLE:
            req.status, req.reason = GAVE_UP, "an index or commodity is kept whole, never fetched a day at a time"
            counts[GAVE_UP] += 1
            continue
        if day >= today:
            counts[WAITING] += 1
            continue
        store = ds.DayStore(root / folder_of(prices, req.underlying), req.underlying)
        if req.trading_day in store.days:
            req.status = FETCHED
            counts[FETCHED] += 1
            continue
        req.tries += 1
        why = None
        try:
            header = _header_of(store)
            rows = _by_day(fetch(client, f"NSE:{req.underlying}-EQ", day, day), header,
                           day - timedelta(days=1), day + timedelta(days=1)).get(day)
            if not rows:
                why = "the broker has no bars for that day"
            else:
                store.put(day, header, rows, check=session_check(prices, req.underlying, {}, closures))
                held = store.manifest
                store.save(serves=(req.underlying,), roll="", clock=ms.CLOCK, interval="1 minute", built=today,
                           source=held.source if held else (
                               f"the Fyers history API, NSE:{req.underlying}-EQ, one day at a time as trades "
                               f"need them ({MARK})"),
                           sessions=held.sessions if held else ())
        except (fh.Refused, ds.Refused) as exc:
            why = str(exc)
        if why is None:
            req.status, req.reason = FETCHED, None
        else:
            req.reason = why
            req.status = GAVE_UP if req.tries >= MAX_TRIES else WAITING
        counts[req.status] += 1
    return counts


def run(sess: Session, client, *, root: Path, today: date, prices: layer.Prices | None = None,
        calendar: dict[date, ms.SessionException] | None = None, closures: dict | None = None,
        now: datetime | None = None) -> dict:
    """One run: every series kept whole, then the stock days asked for. Records the run."""
    now = now or datetime.now(UTC)
    prices = prices or layer.Prices(data_dir=root)
    calendar = ms.load_calendar() if calendar is None else calendar
    closures = shared_closures.load() if closures is None else closures
    report: dict = {u: _one(client, root, u, today, prices, calendar, closures) for u in KEPT_WHOLE}
    report["stocks"] = _stock_days(sess, client, root, today, prices, closures, now)
    if any(r.get("broker") for u, r in report.items() if u in KEPT_WHOLE):
        result = "broker refused"
    elif any(r["refused"] for u, r in report.items() if u in KEPT_WHOLE):
        result = "some days refused"
    else:
        result = "ok"
    sess.add(m.MarketSyncRun(started_at=now, finished_at=datetime.now(UTC), result=result,
                             summary=json.dumps(report, sort_keys=True)))
    sess.flush()
    return report


def needs_login(sess: Session, *, now: datetime | None = None) -> None:
    """A run with no usable login: nothing is asked for, nothing is written, and the card says so."""
    now = now or datetime.now(UTC)
    sess.add(m.MarketSyncRun(started_at=now, finished_at=now, result="needs login", summary="{}"))
    sess.flush()
