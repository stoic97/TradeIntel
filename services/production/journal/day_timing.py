"""When each of the day's trades happened, for its day questions.

915's day questions describe the order and timing of a day and never its result. The new
questions need a little more about each trade, and two of his own medians from his record, so
any threshold is his and never ours. ``enrich`` adds to each trade dict the Journal builds:

* ``entry`` and ``exit``: in the instrument's own zone, as the report shows them
* ``side``: "calls" or "puts" for a single-leg option; "long" or "short" for a single-leg
  future or share, by the side that opened it; None for a position of two or more legs
* ``opens`` and ``closes``: the instrument's session, from its profile
* ``evening``: an MCX trade opened in the evening session, which is not "the open"

``medians`` gives, over his whole record:

* ``median_gap``: minutes from a trade's close to his next trade that day, the next one being
  the first opened after it closed (the rule of ``shared/conditions/b2_condition.py``)
* ``median_first``: minutes from the session's open to a day's first trade, evening trades left
  out

Nothing here reads a price or a result.
"""

from __future__ import annotations

from datetime import datetime, time
from statistics import median

from services.shared.market.series import EVENING_OPENS

OPTION_SIDES = {"CE": "calls", "PE": "puts"}


def side_of(trip) -> str | None:
    """Which way one leg went: a call or a put, or long or short."""
    if len(trip.lines) != 1:
        return None
    line = trip.lines[0]
    if line.segment == "OPT":
        return OPTION_SIDES.get(line.option_type or "")
    return "long" if (line.side or "").lower().startswith("b") else "short"


def instruments_of(rows) -> dict[str, tuple[str, str, str]]:
    """Each trade's instrument, by the trade id the Journal uses (a position's, or its trip's)."""
    out: dict[str, tuple[str, str, str]] = {}
    for row in rows:
        out.setdefault(row.position_id or row.trip_id, (row.exchange or "", row.symbol or "", row.segment or ""))
    return out


def sessions_for(instruments: dict, profile_map, lookup) -> dict[tuple, tuple[time, time]]:
    """Each instrument's session open and close, from its profile; none where it has none."""
    out: dict[tuple, tuple[time, time]] = {}
    for inst in set(instruments.values()):
        profile = lookup(profile_map, *inst)
        if profile is not None:
            out[inst] = (profile.session_start, profile.session_end)
    return out


def _evening(inst: tuple | None, entry: datetime) -> bool:
    return bool(inst) and inst[0] == "MCX" and entry.time() >= EVENING_OPENS


def _since_open(entry: datetime, opens: time) -> float:
    return (entry - datetime.combine(entry.date(), opens, entry.tzinfo)).total_seconds() / 60


def enrich(trades: list[dict], record: list, instruments: dict, sessions: dict) -> None:
    """Add each trade's timing, side and session, where his record holds the trade."""
    by_id = {t.trip_id: t for t in record}
    for trade in trades:
        trip = by_id.get(trade["trip_id"])
        if trip is None:
            continue
        inst = instruments.get(trade["trip_id"])
        trade["entry"], trade["exit"] = trip.entry_ts, trip.exit_ts
        trade["side"] = side_of(trip)
        trade["evening"] = _evening(inst, trip.entry_ts)
        if inst in sessions:
            trade["opens"], trade["closes"] = sessions[inst]


def medians(record: list, instruments: dict, sessions: dict) -> dict[str, float | None]:
    """His median gap to the next trade, and his median minutes from the open to a day's first."""
    by_day: dict[str, list] = {}
    for trip in record:
        by_day.setdefault(trip.trading_day, []).append(trip)
    gaps: list[float] = []
    firsts: list[float] = []
    for trips in by_day.values():
        trips = sorted(trips, key=lambda t: t.entry_ts)
        for i, trip in enumerate(trips):
            nxt = next((t for t in trips[i + 1:] if t.entry_ts > trip.exit_ts), None)
            if nxt is not None:
                gaps.append((nxt.entry_ts - trip.exit_ts).total_seconds() / 60)
        for trip in trips:
            inst = instruments.get(trip.trip_id)
            if inst in sessions and not _evening(inst, trip.entry_ts):
                since = _since_open(trip.entry_ts, sessions[inst][0])
                if since >= 0:
                    firsts.append(since)
                break
    return {"median_gap": float(median(gaps)) if gaps else None,
            "median_first": float(median(firsts)) if firsts else None}
