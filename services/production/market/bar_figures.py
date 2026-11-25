"""Bar figures, worked out off the web app and stored (TICKET-999).

Scope runs one app process on a one-vCPU, 512 MB droplet (ADR-007), so nothing here runs inside a
request. An upload records one pending row (``m.BarFigureJob``); the timer runs
``cli bar-figures`` after ``market-sync``; pages read what this stores.

**Per trade, in underlying points, in the trade's direction:**

* **reference:** the close of the entry minute. Never its open: measuring from the open counts the
  minute he bought in as skill (the rule of the 891 count, ``mirror/prior_minute.py``).
* **went your way:** the most favourable point from the minute after entry through the exit
  minute (the high when he needed it up, the low when down), less the reference; 0 at least.
* **went against you:** the same for the least favourable.
* **took:** the close of the exit minute (or the last bar before it) less the reference.
* A trade held overnight reads every day it spans. Points only, never rupees: an option's premium
  path isn't in the bars, and a rupee conversion would be a would-have figure (ruled 20 Nov).

**After you clicked:** the close at +1 ... +30 minutes after the entry minute, less the reference,
in his direction. A minute with no bar carries the last close; a path that reaches the session's
end stops there and is marked short. **The comparison** is one random moment per measured trade:
the same underlying, month and hour of day, at least 30 minutes from any of his entries, dealt
with the blind replay's seeding (``replay/blind.py``) from the trader and the import, so a page
never changes on reload.

**Counted, never dropped.** A trade with no single direction (``option_direction.of_legs``), no
series, a contract month the series doesn't follow, or a day not in yet is stored with its reason.

**Crude near the roll.** The crude series is MCX's near month (``ROLL_CONVENTION``): the nearest
unexpired future, whose expiry is the 19th of its month or the working day before
(``ctr/profiles/registry.py``, rule ``monthly_day_19``; holidays from ``mcx_sessions.yaml``, which
starts 25 Dec 2025, so an older 19th on a holiday is not moved). A crude option or future on any
other month moves against a different contract, about 23 points away (TICKET-893), and is left
out. Gold and silver have no contract-month rule here yet, so their trades are left out with that
reason rather than measured against a month they may not follow.

**Stock days on request.** A stock's day the store lacks is asked for in ``market_day_request``;
the next ``market-sync`` fetches it and the next run here fills the trade in. Indices and
commodities are never asked for: they are kept whole.
"""

from __future__ import annotations

import json
import random
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from services.production.db import models as m
from services.production.market import sync
from services.production.mirror import loader
from services.production.prices import layer
from services.production.replay import blind
from services.shared import option_direction as od
from services.shared.market import series as ms
from services.shared.schemas.ctr_v1 import Direction, OptionType, Segment

IST = timezone(timedelta(hours=5, minutes=30))
HORIZON = 30
FAINT = 200
KEEP_AWAY = timedelta(minutes=blind.KEEP_AWAY_MINUTES)
KEEP_AWAY_MINUTES_MINUS_ONE = blind.KEEP_AWAY_MINUTES - 1  # a moment 30 minutes away is allowed
MEASURE = "bar figures v1 (TICKET-999)"
PENDING, WAITING, DONE = "pending", "waiting", "done"

NO_DIRECTION = "no single direction: its legs pull both ways"
NO_SERIES = "no market data for this underlying"
MONTH = "contract month differs from the near-month series"
NO_MONTH = "the contract's month is not known"
NO_MONTH_RULE = "the series' contract month isn't set for this underlying yet"
WAITING_FOR_DAY = "waiting for this day's data"
NO_DAY = "the broker has no bars for this day"
NO_ENTRY_BAR = "no bar at the minute he clicked"

NEAR_MONTH_SERIES = frozenset({"CRUDEOIL"})
MONTHLY_FUTURES = frozenset({"CRUDEOIL", "GOLD", "SILVER"})


# ---------- what is measured ----------

@dataclass(frozen=True)
class Leg:
    exchange: str
    symbol: str
    segment: str  # EQ, FUT or OPT
    direction: str  # LONG (bought) or SHORT (sold)
    option_type: str | None
    strike: Decimal | None
    quantity: int
    expiry: date | None
    entry_ts: datetime
    exit_ts: datetime


@dataclass(frozen=True)
class Position:
    trip_id: str
    legs: tuple[Leg, ...]

    @property
    def entry_ts(self) -> datetime:
        return min(leg.entry_ts for leg in self.legs)

    @property
    def exit_ts(self) -> datetime:
        return max(leg.exit_ts for leg in self.legs)


@dataclass(frozen=True)
class Measured:
    trip_id: str
    underlying: str | None
    direction: int  # +1 needs the market up, -1 down, 0 no single direction
    entry_minute: datetime | None
    reason: str | None = None
    way: Decimal | None = None
    against: Decimal | None = None
    took: Decimal | None = None
    path: tuple[Decimal, ...] = ()
    short: bool = False
    after_exit: tuple[Decimal, ...] = ()
    """The close at +1 ... +30 minutes after the exit minute, less the exit's close, in his
    direction; index 0 is the exit itself. Cut at the session end, like ``path``."""
    waiting: tuple[date, ...] = ()
    days_read: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class RandomPath:
    underlying: str
    moment: datetime
    direction: int
    path: tuple[Decimal, ...]
    short: bool


@dataclass(frozen=True)
class Summary:
    underlying: str
    measured: int
    randoms: int
    his_median: tuple[Decimal | None, ...]
    his_q25: tuple[Decimal | None, ...]
    his_q75: tuple[Decimal | None, ...]
    random_median: tuple[Decimal | None, ...]
    random_lo: tuple[Decimal | None, ...]
    random_hi: tuple[Decimal | None, ...]
    faint: tuple[tuple[Decimal, ...], ...]


def minute(ts: datetime) -> datetime:
    """The minute a time falls in, as the series stamps it: IST, naive, start of the minute."""
    return ts.astimezone(IST).replace(tzinfo=None, second=0, microsecond=0)


def direction(position: Position) -> int:
    """+1, -1 or 0 by the shared rule, read from the stored legs."""
    legs = [SimpleNamespace(
        segment=Segment(leg.segment), direction=Direction(leg.direction), strike=leg.strike,
        option_type=OptionType(leg.option_type) if leg.option_type else None,
        quantity=leg.quantity, expiry=leg.expiry) for leg in position.legs]
    try:
        answer = od.of_legs(legs)
    except ValueError:
        return 0
    return {od.Underlying.LONG: 1, od.Underlying.SHORT: -1}.get(answer, 0)


def crude_future_expiry(year: int, month: int, closed: frozenset[date]) -> date:
    """The 19th of the contract month, or the working day before when MCX is shut then."""
    d = date(year, month, 19)
    while d.weekday() >= 5 or d in closed:
        d -= timedelta(days=1)
    return d


def near_month(day: date, closed: frozenset[date]) -> tuple[int, int]:
    """The (year, month) of the nearest unexpired crude future on this day."""
    if day <= crude_future_expiry(day.year, day.month, closed):
        return day.year, day.month
    return (day.year + 1, 1) if day.month == 12 else (day.year, day.month + 1)


def mcx_closed() -> frozenset[date]:
    return frozenset(d for d, e in ms.load_calendar().items() if e.kind == "closed")


def _path(series, start: datetime, ref: Decimal, sign: int, ends: time) -> tuple[tuple[Decimal, ...], bool]:
    out, last = [Decimal(0)], ref
    for k in range(1, HORIZON + 1):
        t = start + timedelta(minutes=k)
        if t.date() != start.date() or t.time() >= ends:
            return tuple(out), True
        bar = series.bar(t)
        if bar is not None:
            last = bar.close
        out.append((last - ref) * sign)
    return tuple(out), False


def _span(first: date, last: date) -> list[date]:
    return [first + timedelta(days=i) for i in range((last - first).days + 1)]


def measure(position: Position, prices: layer.Prices, *, closed: frozenset[date] | None = None) -> Measured:
    """One position's figures, or the reason it has none."""
    first = position.legs[0]
    underlying = prices.underlying_of(first.exchange, first.symbol)
    entry, exit_ = minute(position.entry_ts), minute(position.exit_ts)
    sign = direction(position)
    base = {"trip_id": position.trip_id, "underlying": underlying, "direction": sign, "entry_minute": entry}
    if underlying is None:
        return Measured(**base, reason=NO_SERIES)
    if sign == 0:
        return Measured(**base, reason=NO_DIRECTION)
    if underlying in MONTHLY_FUTURES:
        if underlying not in NEAR_MONTH_SERIES:
            return Measured(**base, reason=NO_MONTH_RULE)
        months = {(leg.expiry.year, leg.expiry.month) if leg.expiry else None for leg in position.legs}
        if None in months:
            return Measured(**base, reason=NO_MONTH)
        if months != {near_month(entry.date(), mcx_closed() if closed is None else closed)}:
            return Measured(**base, reason=MONTH)

    series = prices.series(underlying)
    stock = underlying not in sync.KEPT_WHOLE
    ends = (entry.date(), exit_.date())
    if series is None:
        if stock:
            return Measured(**base, reason=WAITING_FOR_DAY, waiting=tuple(sorted(set(ends))))
        return Measured(**base, reason=NO_SERIES)
    if not isinstance(series, layer.DaySeries):  # a synthetic fixture series: every day is there
        held = covers = lambda day: series.covers(day)
    else:
        held, covers = series.held, series.manifest.covers
    missing = [d for d in sorted(set(ends)) if not held(d) and (stock or not covers(d))]
    if missing:
        return Measured(**base, reason=WAITING_FOR_DAY, waiting=tuple(missing))
    for d in _span(entry.date(), exit_.date()):
        problem = series.problem(d) if isinstance(series, layer.DaySeries) else ""
        if problem:
            return Measured(**base, reason=problem)

    ref_bar = series.bar(entry)
    if ref_bar is None:
        return Measured(**base, reason=NO_ENTRY_BAR)
    ref = ref_bar.close
    hi = lo = last = ref
    read: list[tuple[str, str]] = []
    for d in _span(entry.date(), exit_.date()):
        if isinstance(series, layer.DaySeries):
            if not series.held(d):
                continue
            read.append((d.isoformat(), series.manifest.days[d.isoformat()].sha256))
            minutes = series.minutes(d)
        else:
            minutes = [t for t in (datetime.combine(d, time()) + timedelta(minutes=i) for i in range(24 * 60))
                       if series.bar(t) is not None]
        for t in minutes:
            if entry < t <= exit_:
                bar = series.bar(t)
                hi, lo, last = max(hi, bar.high), min(lo, bar.low), bar.close
    up, down = hi - ref, ref - lo
    way, against = (up, down) if sign > 0 else (down, up)
    ends_at = prices.session(underlying)[1]
    path, short = _path(series, entry, ref, sign, ends_at)
    after_exit, _cut = _path(series, exit_, last, sign, ends_at)
    return Measured(**base, way=max(way, Decimal(0)), against=max(against, Decimal(0)),
                    took=(last - ref) * sign, path=path, short=short, after_exit=after_exit,
                    days_read=tuple(read))


# ---------- the comparison ----------

def random_paths(measured: list[Measured], prices: layer.Prices, *, key: str) -> list[RandomPath]:
    """One random moment per measured trade: same underlying, month and hour, away from his entries."""
    rng = random.Random(f"{blind.SEED}:{key}")
    taken = [x for x in measured if x.reason is None]
    near: dict[str, set[datetime]] = defaultdict(set)
    for x in taken:
        for k in range(-KEEP_AWAY_MINUTES_MINUS_ONE, KEEP_AWAY_MINUTES_MINUS_ONE + 1):
            near[x.underlying].add(x.entry_minute + timedelta(minutes=k))
    pools: dict[tuple, list[datetime]] = {}
    out: list[RandomPath] = []
    for x in taken:
        series = prices.series(x.underlying)
        group = (x.underlying, x.entry_minute.year, x.entry_minute.month, x.entry_minute.hour)
        if group not in pools:
            month = f"{group[1]:04d}-{group[2]:02d}"
            days = sorted(k for k in getattr(series, "manifest", SimpleNamespace(days={})).days if k[:7] == month)
            pools[group] = [t for k in days for t in series.minutes(date.fromisoformat(k))
                            if t.hour == group[3] and t not in near[x.underlying]]
        pool = pools[group]
        if not pool:
            continue
        moment = rng.choice(pool)
        path, short = _path(series, moment, series.bar(moment).close, x.direction,
                            prices.session(x.underlying)[1])
        out.append(RandomPath(x.underlying, moment, x.direction, path, short))
    return out



def _quantile(values: list[Decimal], q: Decimal) -> Decimal | None:
    if not values:
        return None
    v = sorted(values)
    pos = (len(v) - 1) * q
    low = int(pos)
    high = min(low + 1, len(v) - 1)
    return v[low] + (v[high] - v[low]) * (pos - low)


def _at(paths: list[tuple[Decimal, ...]], q: Decimal) -> tuple[Decimal | None, ...]:
    return tuple(_quantile([p[k] for p in paths if len(p) > k], q) for k in range(HORIZON + 1))


def evenly(items: list, k: int) -> list:
    """Up to k items, chosen evenly through the list: never the best or the worst."""
    n = len(items)
    if n <= k:
        return list(items)
    picks = sorted({round(i * (n - 1) / (k - 1)) for i in range(k)})
    return [items[i] for i in picks]


def summarise(underlying: str, measured: list[Measured], randoms: list[RandomPath]) -> Summary:
    his = [x.path for x in measured if x.reason is None and x.underlying == underlying]
    rand = [r.path for r in randoms if r.underlying == underlying]
    return Summary(
        underlying=underlying, measured=len(his), randoms=len(rand),
        his_median=_at(his, Decimal("0.5")), his_q25=_at(his, Decimal("0.25")), his_q75=_at(his, Decimal("0.75")),
        random_median=_at(rand, Decimal("0.5")), random_lo=_at(rand, Decimal("0.025")),
        random_hi=_at(rand, Decimal("0.975")), faint=tuple(evenly(his, FAINT)))


# ---------- the job ----------

def _text(value: Decimal | None) -> str | None:
    return None if value is None else f"{value.normalize():f}"


def _series_json(values) -> str:
    return json.dumps([_text(v) for v in values])


def positions_of(sess: Session, imp: m.Import) -> list[Position]:
    """The import's trips as positions, grouped the way the loader groups them."""
    rows = sess.scalars(select(m.Trip).where(m.Trip.import_id == imp.id).order_by(m.Trip.entry_ts)).all()
    try:
        expiries = loader.expiries_for(sess, imp)
    except (KeyError, ValueError):
        expiries = {}
    grouped: dict[object, list[m.Trip]] = {}
    for row in rows:
        grouped.setdefault(row.position_id or row.id, []).append(row)
    out = []
    for legs in grouped.values():
        out.append(Position(trip_id=legs[0].position_id or legs[0].trip_id, legs=tuple(
            Leg(exchange=r.exchange or "", symbol=r.symbol or "", segment=r.segment or "EQ",
                direction=r.direction or "LONG", option_type=r.option_type, strike=r.strike,
                quantity=r.quantity or 1, expiry=expiries.get(loader.expiry_key(loader._line(r))),
                entry_ts=r.entry_ts, exit_ts=r.exit_ts) for r in legs)))
    return out


def _ask_for_days(sess: Session, measured: list[Measured], now: datetime) -> dict[tuple[str, str], str]:
    """Ask the sync for every stock day a trade is waiting on. Returns each day's request status."""
    status: dict[tuple[str, str], str] = {}
    for x in measured:
        if x.reason != WAITING_FOR_DAY or x.underlying in sync.KEPT_WHOLE:
            continue
        for day in x.waiting:
            k = (x.underlying, day.isoformat())
            if k in status:
                continue
            req = sess.scalars(select(m.MarketDayRequest).where(
                m.MarketDayRequest.underlying == k[0], m.MarketDayRequest.trading_day == k[1])).first()
            if req is None:
                req = m.MarketDayRequest(underlying=k[0], trading_day=k[1], requested_at=now,
                                         status=sync.WAITING, tries=0)
                sess.add(req)
            status[k] = req.status
    sess.flush()
    return status


def work(sess: Session, job: m.BarFigureJob, prices: layer.Prices, *, now: datetime,
         closed: frozenset[date], code_version: str) -> str:
    """Work out one import's figures and store them. Returns the job's new state."""
    imp = sess.get(m.Import, job.import_id)
    measured = [measure(p, prices, closed=closed) for p in positions_of(sess, imp)]
    asked = _ask_for_days(sess, measured, now)
    settled = []
    for x in measured:
        if (x.reason == WAITING_FOR_DAY and x.underlying not in sync.KEPT_WHOLE
                and all(asked.get((x.underlying, d.isoformat())) == sync.GAVE_UP for d in x.waiting)):
            x = Measured(x.trip_id, x.underlying, x.direction, x.entry_minute, reason=NO_DAY)
        settled.append(x)
    randoms = random_paths(settled, prices, key=f"bars:{imp.trader_id}:{imp.id}")

    for model in (m.BarTradeFigure, m.BarPathSummary):
        sess.execute(delete(model).where(model.import_id == imp.id))
    for x in settled:
        sess.add(m.BarTradeFigure(
            import_id=imp.id, trip_id=x.trip_id, underlying=x.underlying, reason=x.reason,
            way=_text(x.way), against=_text(x.against), took=_text(x.took),
            path=_series_json(x.path) if x.path else None, short=x.short,
            after_exit=_series_json(x.after_exit) if x.after_exit else None))
    for underlying in sorted({x.underlying for x in settled if x.reason is None}):
        s = summarise(underlying, settled, randoms)
        sess.add(m.BarPathSummary(
            import_id=imp.id, underlying=underlying, measured=s.measured, randoms=s.randoms,
            his_median=_series_json(s.his_median), his_q25=_series_json(s.his_q25),
            his_q75=_series_json(s.his_q75), random_median=_series_json(s.random_median),
            random_lo=_series_json(s.random_lo), random_hi=_series_json(s.random_hi),
            faint=json.dumps([[_text(v) for v in p] for p in s.faint])))

    waiting = sorted({(x.underlying, d) for x in settled if x.reason == WAITING_FOR_DAY for d in x.waiting})
    days: dict[str, dict[str, str]] = defaultdict(dict)
    for x in settled:
        for day, sha in x.days_read:
            days[x.underlying][day] = sha
    job.state = WAITING if waiting else DONE
    job.waiting_days = len(waiting)
    job.updated_at = now
    job.provenance = json.dumps({
        "code_version": code_version, "measure": MEASURE, "underlying_map": prices.mapping.version,
        "not_measured": dict(Counter(x.reason for x in settled if x.reason)), "days": days,
    }, sort_keys=True)
    sess.flush()
    return job.state


def run(sess: Session, prices: layer.Prices | None = None, *, now: datetime,
        closed: frozenset[date] | None = None, code_version: str | None = None) -> dict[str, int]:
    """Every pending or waiting import, one at a time. Returns how many ended in each state."""
    prices = prices or layer.Prices()
    closed = mcx_closed() if closed is None else closed
    if code_version is None:
        from services.production.api import version
        code_version = version.describe(Path(__file__).resolve().parent, dirty=True)
    jobs = sess.scalars(select(m.BarFigureJob).where(m.BarFigureJob.state.in_((PENDING, WAITING)))
                        .order_by(m.BarFigureJob.id)).all()
    counts: Counter = Counter()
    for job in jobs:
        counts[work(sess, job, prices, now=now, closed=closed, code_version=code_version)] += 1
    return dict(counts)
