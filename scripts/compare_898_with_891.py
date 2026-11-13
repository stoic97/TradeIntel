"""TICKET-898: the independent count against TICKET-891's, on the same history.

Synthetic data only (README rule 1): the repo's demo tradebook for the trips and seeded
random 1-minute bars for the market. No trader's real data is read or printed here. For a
real history, run scripts/independent_count_898.py locally and compare the figures by hand;
the figures never go in git.

Prints, for the prior minute and each horizon: both figures, both denominators, how many
trips the two scripts classify differently, and each script's reasons for what it could not
measure. The last line is AGREE or DIVERGE; the exit status is 0 only for AGREE.
"""

from __future__ import annotations

import argparse
import hashlib
import random
import sys
from collections import Counter
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from scripts import independent_count_898 as mine
from services.production.ctr.adapters.dhan_tradebook import parse
from services.production.ctr.reconstruct import reconstruct
from services.production.mirror import prior_minute as theirs
from services.shared.positions import group_positions

IST = timezone(timedelta(hours=5, minutes=30))
COUNTS = ("prior", *mine.HORIZONS)
WITH, NOT_WITH = "with", "not with"
REASONS = {
    mine.NO_DIRECTION: theirs.Reason.NO_DIRECTION,
    mine.NO_SERIES: theirs.Reason.NO_SERIES,
    mine.NOT_COVERED: theirs.Reason.NOT_COVERED,
    mine.MISSING_PRIOR_BAR: theirs.Reason.NO_PRIOR_BAR,
    mine.MISSING_ENTRY_BAR: theirs.Reason.NO_ENTRY_BAR,
    mine.MISSING_HORIZON_BAR: theirs.Reason.NO_HORIZON_BAR,
}


def load_demo_trips() -> list:
    csv = REPO / "data" / "fixtures" / "demo" / "scope_demo_tradebook.csv"
    raw_hash = hashlib.sha256(csv.read_bytes()).hexdigest()
    parsed = parse(csv, trader_id="DEMO", raw_hash=raw_hash)
    mode = "short_options=True"
    try:
        recon = reconstruct(parsed.fills, fees_available=parsed.fees_available, short_options=True)
    except Exception as exc:  # noqa: BLE001
        mode = f"short_options refused ({type(exc).__name__}: {exc}); default used"
        recon = reconstruct(parsed.fills, fees_available=parsed.fees_available)
    print(
        f"demo tradebook: {len(parsed.fills)} fills, {mode}; {len(recon.round_trips)} trips, "
        f"{len(recon.skipped)} skipped, {len(recon.open_positions)} open"
    )
    return list(recon.round_trips)


def synthetic_bars(seed: int) -> dict[datetime, tuple[float, float]]:
    """Weekdays 2026-06-01..2026-08-20, 09:00-23:29, about 0.5% of minutes missing."""
    rng = random.Random(seed)
    bars: dict[datetime, tuple[float, float]] = {}
    day, end, price = date(2026, 6, 1), date(2026, 8, 20), 6000
    while day <= end:
        if day.weekday() < 5:
            minute = datetime.combine(day, time(9, 0))
            while minute < datetime.combine(day, time(23, 30)):
                opened = price + rng.choice((-1, 0, 0, 0, 1))
                price = opened + rng.choice((-3, -2, -1, 0, 0, 1, 2, 3))
                if rng.random() > 0.005:
                    bars[minute] = (float(opened), float(price))
                minute += timedelta(minutes=1)
        day += timedelta(days=1)
    return bars


def _kind(trip, multi: set) -> str:
    if trip.trip_id in multi:
        return "MULTI"
    if trip.segment.value == "OPT":
        return "CALL" if trip.option_type.value == "CE" else "PUT"
    return {"FUT": "FUT", "EQ": "STOCK"}[trip.segment.value]


def _naive_ist(ts: datetime) -> datetime:
    return ts.astimezone(IST).replace(tzinfo=None) if ts.tzinfo else ts


def _aware_ist(ts: datetime) -> datetime:
    return ts.astimezone(IST) if ts.tzinfo else ts.replace(tzinfo=IST)


def mine_tags(result) -> dict[str, dict]:
    per_count = {"prior": result.prior.per_trip}
    per_count.update({h: result.after[h].per_trip for h in mine.HORIZONS})
    tags: dict[str, dict] = {}
    for count, per_trip in per_count.items():
        for trip_id, outcome in per_trip.items():
            if outcome == mine.WITH:
                tag = WITH
            elif outcome in (mine.AGAINST, mine.FLAT):
                tag = NOT_WITH
            else:
                tag = REASONS[outcome]
            tags.setdefault(trip_id, {})[count] = tag
    return tags


def theirs_tags(entries: list, tables: dict) -> dict[str, dict]:
    """891 run one trip at a time, so each trip's own outcome is visible."""
    tags: dict[str, dict] = {}
    for entry in entries:
        res = theirs.count([entry], tables)
        row: dict = {}
        trip_level = res.unmeasured[0].reason if res.unmeasured else None
        row["prior"] = trip_level or (
            res.unmeasured_before[0].reason if res.unmeasured_before
            else WITH if res.before.agreed else NOT_WITH
        )
        for h in mine.HORIZONS:
            row[h] = trip_level or (
                res.unmeasured_after[h][0].reason if res.unmeasured_after[h]
                else WITH if res.after[h].agreed else NOT_WITH
            )
        tags[entry.trip_id] = row
    return tags


def _name(tag) -> str:
    return getattr(tag, "name", str(tag))


def _figures(tags: dict[str, dict], count) -> tuple[int, int]:
    column = [row[count] for row in tags.values()]
    return column.count(WITH), column.count(WITH) + column.count(NOT_WITH)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--seed", type=int, default=898, help="seed for the synthetic bars")
    args = ap.parse_args(argv)

    trips = load_demo_trips()
    multi = {leg.trip_id for p in group_positions(trips) if len(p.legs) > 1 for leg in p.legs}
    my_trips = [
        mine.Trip(
            t.trip_id, f"{t.exchange}_{t.symbol}", _kind(t, multi),
            "BUY" if t.direction.value == "LONG" else "SELL", _naive_ist(t.entry_ts),
        )
        for t in trips
    ]
    bars = synthetic_bars(args.seed)
    series = mine.Series(bars)
    result = mine.count(my_trips, {"CRUDE": series})

    entries = [
        theirs.Entry(
            trip_id=t.trip_id,
            underlying="CRUDE" if mine.UNDERLYING.get(mt.profile.upper()) == "CRUDE" else mt.profile,
            entry_ts=_aware_ist(t.entry_ts),
            direction=mine.direction(mt.kind, mt.side) or None,
        )
        for t, mt in zip(trips, my_trips)
    ]
    table = theirs.BarTable(
        bars={k.replace(tzinfo=IST): theirs.Bar(open=v[0], close=v[1]) for k, v in bars.items()},
        first_day=series.first_day,
        last_day=series.last_day,
    )
    whole = theirs.count(entries, {"CRUDE": table})
    a, b = mine_tags(result), theirs_tags(entries, {"CRUDE": table})

    print(f"synthetic bars: {len(bars)} (seed {args.seed});  trips: {len(trips)}")
    print(f"891 whole-history total: {whole.total}")
    print()
    print(f"{'count':>6} | {'mine with/measured':>20} | {'891 with/measured':>19} | differ per trip")
    headline = {"prior": (whole.before.agreed, whole.before.measured)}
    headline.update({h: (whole.after[h].agreed, whole.after[h].measured) for h in mine.HORIZONS})
    diverged = 0
    pairs: dict = {}
    for count in COUNTS:
        mw, mm = _figures(a, count)
        tw, tm = headline[count]
        differ = [(a[t][count], b[t][count]) for t in a if a[t][count] != b[t][count]]
        pairs[count] = Counter(differ)
        diverged += len(differ) + int((mw, mm) != (tw, tm))
        label = "prior" if count == "prior" else f"+{count}"
        print(f"{label:>6} | {mw:>9} / {mm:<8} | {tw:>9} / {tm:<7} | {len(differ)}")
    print()
    for count in COUNTS:
        label = "prior" if count == "prior" else f"+{count}"
        ma = Counter(_name(v[count]) for v in a.values() if v[count] not in (WITH, NOT_WITH))
        tb = Counter(_name(v[count]) for v in b.values() if v[count] not in (WITH, NOT_WITH))
        print(f"unmeasured {label}:  mine {dict(sorted(ma.items()))}")
        print(f"{'':>15}891  {dict(sorted(tb.items()))}")
        for (x, y), n in sorted(pairs[count].items(), key=lambda kv: -kv[1]):
            print(f"{'':>15}differ: mine={_name(x)} 891={_name(y)} x{n}")
    print()
    print("AGREE" if diverged == 0 else "DIVERGE")
    return 0 if diverged == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())