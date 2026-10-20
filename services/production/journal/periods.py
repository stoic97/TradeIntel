"""What a Journal covers: the unit, and which periods are complete.

PRD 7.2. Two decisions, and the second is the one that protects the trader.

**The unit** is the trading day unless the upload's median eligible day is thinner
than two trips, in which case it is per 10 trips. That is a counted density rule on
the upload, not an inferred archetype (PRD decision 13) -- nothing here stores or
displays a style, and the trader's own setting overrides it from the moment he makes
one.

**A period is written only when it is complete.** A Journal for half a day would be
rewritten by the next upload, and a trader who read the first one was told something
that is no longer true. Complete means: the upload contains a later trading day, or
the export date is after this one. The last day of an upload with no export date is
not complete, because more of it may exist in the broker's records, and an export
date falling ON the last day does not complete it either -- the export ran during
that day.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from statistics import median

from services.production.journal import constants as k
from services.production.mirror.metrics import Trip
from services.shared.schemas import scope_v1 as s


@dataclass(frozen=True)
class UnitChoice:
    unit: s.JournalUnit
    n: int | None
    from_preference: bool
    median_trips_per_day: float


@dataclass(frozen=True)
class Period:
    """One Journal's worth of trading, and whether it is finished."""

    unit: s.JournalUnit
    period_start: str
    period_end: str
    trips: tuple[Trip, ...]
    complete: bool

    @property
    def key(self) -> str:
        """Stable identity for a period, so a later upload supersedes the same one."""
        return f"{self.unit.value}:{self.period_start}:{self.period_end}"


def _by_day(trips: list[Trip]) -> dict[str, list[Trip]]:
    days: dict[str, list[Trip]] = {}
    for trip in sorted(trips, key=lambda t: (t.entry_ts, t.trip_id)):
        days.setdefault(trip.trading_day, []).append(trip)
    return dict(sorted(days.items()))


def default_unit(trips: list[Trip]) -> UnitChoice:
    """The density rule. Nothing about the trader, only about this upload."""
    days = _by_day(trips)
    if not days:
        return UnitChoice(s.JournalUnit.PER_N_TRIPS, k.DEFAULT_TRIPS_PER_JOURNAL,
                          False, 0.0)
    per_day = median(len(day_trips) for day_trips in days.values())
    if per_day >= k.DENSITY_THRESHOLD_TRIPS_PER_DAY:
        return UnitChoice(s.JournalUnit.DAY, None, False, float(per_day))
    return UnitChoice(s.JournalUnit.PER_N_TRIPS, k.DEFAULT_TRIPS_PER_JOURNAL,
                      False, float(per_day))


def resolve_unit(
    trips: list[Trip],
    *,
    preference: s.JournalUnit | None,
    preference_n: int | None,
) -> UnitChoice:
    """The trader's setting if he has made one, otherwise the density rule."""
    rule = default_unit(trips)
    if preference is None:
        return rule
    return UnitChoice(
        unit=preference,
        n=preference_n or (k.DEFAULT_TRIPS_PER_JOURNAL
                           if preference is s.JournalUnit.PER_N_TRIPS else None),
        from_preference=True,
        median_trips_per_day=rule.median_trips_per_day,
    )


def _day_is_complete(day: str, later_days: list[str], export_date: str | None) -> bool:
    if later_days:
        return True
    return export_date is not None and export_date > day


def periods_for(
    trips: list[Trip],
    *,
    unit: s.JournalUnit,
    export_date: str | None,
    n: int | None = None,
) -> list[Period]:
    """Every period this upload covers, in order, each marked complete or not."""
    if not trips:
        return []
    if unit is s.JournalUnit.DAY:
        return _day_periods(trips, export_date)
    if unit is s.JournalUnit.WEEK:
        return _week_periods(trips, export_date)
    return _trip_group_periods(trips, n or k.DEFAULT_TRIPS_PER_JOURNAL)


def _day_periods(trips: list[Trip], export_date: str | None) -> list[Period]:
    days = _by_day(trips)
    ordered = list(days)
    return [
        Period(
            unit=s.JournalUnit.DAY,
            period_start=day,
            period_end=day,
            trips=tuple(days[day]),
            complete=_day_is_complete(day, ordered[i + 1:], export_date),
        )
        for i, day in enumerate(ordered)
    ]


def _week_periods(trips: list[Trip], export_date: str | None) -> list[Period]:
    """ISO weeks, Monday to Sunday. A week is complete once its Sunday has passed."""
    weeks: dict[tuple[str, str], list[Trip]] = {}
    for trip in sorted(trips, key=lambda t: (t.entry_ts, t.trip_id)):
        day = date.fromisoformat(trip.trading_day)
        monday = day - timedelta(days=day.weekday())
        sunday = monday + timedelta(days=6)
        weeks.setdefault((monday.isoformat(), sunday.isoformat()), []).append(trip)

    ordered = sorted(weeks)
    out = []
    for i, (monday, sunday) in enumerate(ordered):
        later = bool(ordered[i + 1:])
        complete = later or (export_date is not None and export_date > sunday)
        out.append(Period(s.JournalUnit.WEEK, monday, sunday,
                          tuple(weeks[(monday, sunday)]), complete))
    return out


def _trip_group_periods(trips: list[Trip], n: int) -> list[Period]:
    """Consecutive runs of n trips by entry time. A trailing partial run waits."""
    ordered = sorted(trips, key=lambda t: (t.entry_ts, t.trip_id))
    out = []
    for start in range(0, len(ordered), n):
        group = ordered[start:start + n]
        out.append(Period(
            unit=s.JournalUnit.PER_N_TRIPS,
            period_start=group[0].trading_day,
            period_end=group[-1].trading_day,
            trips=tuple(group),
            complete=len(group) == n,
        ))
    return out
