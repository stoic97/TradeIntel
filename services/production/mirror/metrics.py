"""Appendix A, as pure functions. One per row of the contract.

A list of trips in, a typed result out. Nothing here reads a database, formats a
rupee or knows what a template is -- the Mirror page formats what these return and
computes nothing of its own, so there is exactly one place each figure is decided.

Every result carries a ``ResultState``. A metric with too little behind it says so
rather than showing a number that looks the same as a well-supported one, and an
empty history never reaches a division.

Money is ``Decimal`` throughout and rounding happens at the presentation boundary
only (ctr_v1 section 6.5). Two straight losses is not computed here: it calls the
shared B2 condition, which the research library calls too (PRD 6.3).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from statistics import median
from typing import Any

from services.shared.conditions.b2_condition import Obs, population_and_condition
from services.shared.schemas import scope_v1 as s

SMALL_SAMPLE_TRIPS = 5
"""Below this, an hour is shown with a small-sample flag rather than hidden.

Appendix A: hours with fewer than five trips are still shown. Hiding a thin hour
would make the remaining ones look more solid than they are.
"""


@dataclass(frozen=True)
class Trip:
    """One reconstructed round trip, as the Mirror sees it."""

    trip_id: str
    trading_day: str
    entry_ts: datetime
    exit_ts: datetime
    holding_seconds: int
    net: Decimal
    lots: int
    risk_unit_source: s.RiskUnitSourceV1

    @property
    def is_win(self) -> bool:
        return self.net > 0

    @property
    def is_loss(self) -> bool:
        return self.net < 0

    @property
    def is_scratch(self) -> bool:
        return self.net == 0


def load_trips(rows: list[dict[str, Any]]) -> list[Trip]:
    """Build trips from fixture or database rows, in entry order."""
    trips = [
        Trip(
            trip_id=row["trip_id"],
            trading_day=row["trading_day"],
            entry_ts=datetime.fromisoformat(row["entry_ts"]),
            exit_ts=datetime.fromisoformat(row["exit_ts"]),
            holding_seconds=int(row["holding_seconds"]),
            net=Decimal(str(row["net"])),
            lots=int(row["lots"]),
            risk_unit_source=s.RiskUnitSourceV1(row["risk_unit_source"]),
        )
        for row in rows
    ]
    return sorted(trips, key=lambda t: (t.entry_ts, t.trip_id))


def _round(value: Decimal, places: str = "0.01") -> Decimal:
    return value.quantize(Decimal(places), rounding=ROUND_HALF_UP)


def _trim(value: Decimal) -> Decimal:
    """Drop trailing zeros, so a median of 4.50 reads as 4.5.

    Used for counts and medians, where a trailing zero is noise. NOT used for the
    holding-time ratio, where 3.0 says "measured" and 3 would say "round number".
    """
    return value.normalize()


@dataclass(frozen=True)
class DayNet:
    trading_day: str
    net: Decimal
    trips: int


@dataclass(frozen=True)
class FiveWorstDays:
    days: tuple[DayNet, ...]
    sum: Decimal
    state: s.ResultState


@dataclass(frozen=True)
class ShareOfTotal:
    five_day_sum: Decimal
    total: Decimal
    share_percent: Decimal | None
    shown_as_percentage: bool
    other_days_count: int
    other_days_net: Decimal
    state: s.ResultState


@dataclass(frozen=True)
class DayCounts:
    counts: list[int]
    normal_day: Decimal
    busiest_day: str
    busiest_trips: int
    busiest_vs_normal: Decimal
    state: s.ResultState


@dataclass(frozen=True)
class TwoStraightLosses:
    population: int
    condition: int
    comparison: int
    condition_trip_ids: list[str]
    condition_net: Decimal
    comparison_net: Decimal
    condition_mean: Decimal | None
    comparison_mean: Decimal | None
    state: s.ResultState


@dataclass(frozen=True)
class StrikeRate:
    wins: int
    losses: int
    scratches: int
    rate_percent: Decimal | None
    state: s.ResultState


@dataclass(frozen=True)
class AverageLots:
    total_lots: int
    mean: Decimal | None
    state: s.ResultState


@dataclass(frozen=True)
class HoldingTime:
    winners_median_seconds: int | None
    losers_median_seconds: int | None
    ratio: Decimal | None
    state: s.ResultState


@dataclass(frozen=True)
class HourResult:
    hour: int
    net: Decimal
    trips: int
    small_sample: bool


@dataclass(frozen=True)
class LosingRun:
    length: int
    trip_ids: list[str]
    crosses_days: bool
    days: list[str]
    state: s.ResultState


@dataclass(frozen=True)
class RiskFigureCounts:
    counts: dict[s.RiskUnitSourceV1, int]
    showable: int
    state: s.ResultState


@dataclass(frozen=True)
class JournalUnitDefault:
    median_trips_per_day: Decimal
    unit: s.JournalUnit
    state: s.ResultState


def _by_day(trips: list[Trip]) -> dict[str, list[Trip]]:
    days: dict[str, list[Trip]] = {}
    for trip in trips:
        days.setdefault(trip.trading_day, []).append(trip)
    return dict(sorted(days.items()))


def five_worst_days(trips: list[Trip]) -> FiveWorstDays:
    """Sum of net per trading day, ascending, first five. Ties: earlier date first."""
    if not trips:
        return FiveWorstDays((), Decimal(0), s.ResultState.INSUFFICIENT_SAMPLE)
    days = [
        DayNet(day, sum((t.net for t in day_trips), Decimal(0)), len(day_trips))
        for day, day_trips in _by_day(trips).items()
    ]
    worst = sorted(days, key=lambda d: (d.net, d.trading_day))[:5]
    return FiveWorstDays(
        days=tuple(worst),
        sum=sum((d.net for d in worst), Decimal(0)),
        state=s.ResultState.COUNTED_FACT,
    )


def share_of_total(trips: list[Trip]) -> ShareOfTotal:
    """A percentage only when 0% < share <= 100%; otherwise both figures, no ratio.

    Appendix A is strict about this because the alternatives mislead. A -100 total
    with -500 worst days would read '500% of your result', and a positive total with
    negative worst days gives a negative percentage -- both arithmetically true and
    both nonsense to read.
    """
    worst = five_worst_days(trips)
    if worst.state is not s.ResultState.COUNTED_FACT:
        return ShareOfTotal(Decimal(0), Decimal(0), None, False, 0, Decimal(0),
                            s.ResultState.INSUFFICIENT_SAMPLE)

    total = sum((t.net for t in trips), Decimal(0))
    worst_days = {d.trading_day for d in worst.days}
    other_trips = [t for t in trips if t.trading_day not in worst_days]
    other_days = {t.trading_day for t in other_trips}
    other_net = sum((t.net for t in other_trips), Decimal(0))

    share = None
    shown = False
    if total != 0:
        candidate = _round(worst.sum / total * 100)
        if Decimal(0) < candidate <= Decimal(100):
            share = candidate
            shown = True

    return ShareOfTotal(
        five_day_sum=worst.sum, total=total,
        share_percent=_trim(share) if share is not None else None,
        shown_as_percentage=shown,
        other_days_count=len(other_days), other_days_net=other_net,
        state=s.ResultState.COUNTED_FACT,
    )


def day_counts(trips: list[Trip]) -> DayCounts:
    """Trip count per eligible day, the normal (median) day, and the busiest."""
    if not trips:
        return DayCounts([], Decimal(0), "", 0, Decimal(0),
                         s.ResultState.INSUFFICIENT_SAMPLE)
    days = _by_day(trips)
    counts = [len(day_trips) for day_trips in days.values()]
    normal = Decimal(str(median(counts)))
    busiest_day, busiest_trips = max(
        ((day, len(day_trips)) for day, day_trips in days.items()),
        key=lambda pair: (pair[1], pair[0]),
    )
    return DayCounts(
        counts=counts, normal_day=_trim(normal),
        busiest_day=busiest_day, busiest_trips=busiest_trips,
        busiest_vs_normal=_round(Decimal(busiest_trips) / normal),
        state=s.ResultState.COUNTED_FACT,
    )


def best_five(trips: list[Trip]) -> list[Trip]:
    """Highest net, descending. Ties: earlier entry first. No winsorising."""
    return sorted(trips, key=lambda t: (-t.net, t.entry_ts))[:5]


def worst_five(trips: list[Trip]) -> list[Trip]:
    """Lowest net, ascending. Ties: earlier entry first."""
    return sorted(trips, key=lambda t: (t.net, t.entry_ts))[:5]


def two_straight_losses(trips: list[Trip]) -> TwoStraightLosses:
    """The research library's B2 population and condition, on this trader's trips.

    One function decides this, in services/shared/conditions. The library passes R
    where this passes net rupees; the condition reads only the sign, so both get
    the same answer on the same trips (PRD 6.3).
    """
    if not trips:
        return TwoStraightLosses(0, 0, 0, [], Decimal(0), Decimal(0), None, None,
                                 s.ResultState.INSUFFICIENT_SAMPLE)

    day_index = {day: i for i, day in enumerate(sorted({t.trading_day for t in trips}))}
    obs = [
        Obs(day=day_index[t.trading_day],
            entry_at=t.entry_ts.timestamp(),
            exit_at=t.exit_ts.timestamp(),
            r=float(t.net))
        for t in trips
    ]
    in_pop, cond = population_and_condition(obs)

    condition_trips = [t for t, flag in zip(trips, cond, strict=True) if flag]
    comparison_trips = [
        t for t, pop, flag in zip(trips, in_pop, cond, strict=True) if pop and not flag
    ]
    condition_net = sum((t.net for t in condition_trips), Decimal(0))
    comparison_net = sum((t.net for t in comparison_trips), Decimal(0))

    return TwoStraightLosses(
        population=int(in_pop.sum()),
        condition=len(condition_trips),
        comparison=len(comparison_trips),
        condition_trip_ids=[t.trip_id for t in condition_trips],
        condition_net=condition_net,
        comparison_net=comparison_net,
        condition_mean=_trim(_round(condition_net / len(condition_trips))) if condition_trips else None,
        comparison_mean=_trim(_round(comparison_net / len(comparison_trips))) if comparison_trips else None,
        state=s.ResultState.COUNTED_FACT,
    )


def strike_rate(trips: list[Trip]) -> StrikeRate:
    """Wins over wins plus losses. Scratches are in neither, and in the totals."""
    wins = sum(1 for t in trips if t.is_win)
    losses = sum(1 for t in trips if t.is_loss)
    scratches = sum(1 for t in trips if t.is_scratch)
    if wins + losses == 0:
        return StrikeRate(wins, losses, scratches, None,
                          s.ResultState.INSUFFICIENT_SAMPLE)
    return StrikeRate(
        wins=wins, losses=losses, scratches=scratches,
        rate_percent=_trim(_round(Decimal(wins) / Decimal(wins + losses) * 100, "0.1")),
        state=s.ResultState.COUNTED_FACT,
    )


def average_lots(trips: list[Trip]) -> AverageLots:
    if not trips:
        return AverageLots(0, None, s.ResultState.INSUFFICIENT_SAMPLE)
    total = sum(t.lots for t in trips)
    return AverageLots(
        total_lots=total,
        mean=_trim(_round(Decimal(total) / Decimal(len(trips)), "0.001")),
        state=s.ResultState.COUNTED_FACT,
    )


def holding_time(trips: list[Trip]) -> HoldingTime:
    """Median hold by outcome. Scratches excluded; a zero median gives no ratio."""
    winners = [t.holding_seconds for t in trips if t.is_win]
    losers = [t.holding_seconds for t in trips if t.is_loss]
    if not winners or not losers:
        return HoldingTime(
            int(median(winners)) if winners else None,
            int(median(losers)) if losers else None,
            None, s.ResultState.INSUFFICIENT_SAMPLE,
        )
    winners_median = int(median(winners))
    losers_median = int(median(losers))
    # Not trimmed: a ratio of exactly three reads as 3.0, not 3. The trailing
    # zero says "this is a ratio, measured" rather than "this is a round number".
    ratio = (
        _round(Decimal(winners_median) / Decimal(losers_median), "0.1")
        if losers_median else None
    )
    return HoldingTime(winners_median, losers_median, ratio, s.ResultState.COUNTED_FACT)


def result_by_hour(trips: list[Trip]) -> list[HourResult]:
    """Net by entry hour in the instrument's timezone. Thin hours flagged, not hidden."""
    hours: dict[int, list[Trip]] = {}
    for trip in trips:
        hours.setdefault(trip.entry_ts.hour, []).append(trip)
    return [
        HourResult(
            hour=hour,
            net=sum((t.net for t in hour_trips), Decimal(0)),
            trips=len(hour_trips),
            small_sample=len(hour_trips) < SMALL_SAMPLE_TRIPS,
        )
        for hour, hour_trips in sorted(hours.items())
    ]


def longest_losing_run(trips: list[Trip]) -> LosingRun:
    """Longest run of consecutive losing trips by entry time, across days.

    Across days on purpose: a run that ends one evening and resumes the next morning
    is one run to the person who lived it. The drawer says so.
    """
    if not trips:
        return LosingRun(0, [], False, [], s.ResultState.INSUFFICIENT_SAMPLE)
    best: list[Trip] = []
    current: list[Trip] = []
    for trip in trips:
        if trip.is_loss:
            current.append(trip)
            if len(current) > len(best):
                best = list(current)
        else:
            current = []
    days = sorted({t.trading_day for t in best})
    return LosingRun(
        length=len(best), trip_ids=[t.trip_id for t in best],
        crosses_days=len(days) > 1, days=days,
        state=s.ResultState.COUNTED_FACT if best else s.ResultState.INSUFFICIENT_SAMPLE,
    )


def risk_figure_counts(trips: list[Trip]) -> RiskFigureCounts:
    """How many trips have a risk unit, by source.

    ``showable`` counts only the two that may ever be a denominator on screen. The
    others are counted and reported; dividing by them is what the PRD forbids.
    """
    counts = {source: 0 for source in s.RiskUnitSourceV1}
    for trip in trips:
        counts[trip.risk_unit_source] += 1
    showable = sum(counts[source] for source in s.SHOWABLE_DENOMINATORS)
    return RiskFigureCounts(
        counts=counts, showable=showable,
        state=s.ResultState.COUNTED_FACT if trips else s.ResultState.INSUFFICIENT_SAMPLE,
    )


def journal_unit_default(trips: list[Trip]) -> JournalUnitDefault:
    """Trading day unless the median eligible day is thinner than two trips."""
    counts = day_counts(trips)
    if counts.state is not s.ResultState.COUNTED_FACT:
        return JournalUnitDefault(Decimal(0), s.JournalUnit.PER_N_TRIPS,
                                  s.ResultState.INSUFFICIENT_SAMPLE)
    from services.production.journal import constants as k
    unit = (
        s.JournalUnit.DAY
        if counts.normal_day >= k.DENSITY_THRESHOLD_TRIPS_PER_DAY
        else s.JournalUnit.PER_N_TRIPS
    )
    return JournalUnitDefault(counts.normal_day, unit, s.ResultState.COUNTED_FACT)
