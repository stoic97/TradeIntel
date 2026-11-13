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

from collections import Counter
from dataclasses import dataclass, replace
from datetime import datetime
from decimal import ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP, Decimal
from functools import lru_cache
from itertools import pairwise
from math import ceil
from statistics import median
from typing import Any

from services.shared.conditions import b2_shuffle
from services.shared.conditions.b2_condition import Obs, population_and_condition
from services.shared.schemas import scope_v1 as s

SMALL_SAMPLE_TRIPS = 5
"""Below this, an hour is shown with a small-sample flag rather than hidden.

Appendix A: hours with fewer than five trips are still shown. Hiding a thin hour
would make the remaining ones look more solid than they are.
"""

CLOCK_MINIMUM_TRADES = 30
"""Below this, an hour on a book's clock shows ₹ and the count but no win rate (ruling).

Also where a book's clock gets a chart of its own, and which hours a ₹ per trade is set
beside: a rate has a minimum, and ₹ per trade does not, but one trade is not a comparison.
"""


@dataclass(frozen=True)
class Leg:
    """One leg of a position, as a trader reads it: "Bought 5000 CE" and its result."""

    label: str
    net: Decimal


@dataclass(frozen=True)
class TradeLine:
    """One leg as the broker's file has it: what a trader knows his trade by (TICKET-822)."""

    symbol: str
    segment: str  # EQ, FUT or OPT
    side: str  # "Buy" or "Sell": how it was opened
    quantity: int | None
    entry_price: Decimal | None
    exit_price: Decimal | None
    net: Decimal
    strike: Decimal | None = None
    option_type: str | None = None
    entry_ts: datetime | None = None

    @property
    def instrument(self) -> str:
        """As the trader knows it: WIDGETOIL 5000 CE. A leg stored before Annex H has no strike."""
        if self.strike is None or not self.option_type:
            return self.symbol
        return f"{self.symbol} {self.strike.normalize():f} {self.option_type}"


@dataclass(frozen=True)
class Trip:
    """One decision as the Mirror sees it: a round trip, or a position of several legs."""

    trip_id: str
    symbol: str  # the instrument, as the broker's file names it (B1: trade records)
    trading_day: str
    entry_ts: datetime
    exit_ts: datetime
    holding_seconds: int
    net: Decimal
    lots: int
    risk_unit_source: s.RiskUnitSourceV1
    number_in_force: Decimal | None = None  # his number that day, in rupees (TICKET-831)
    is_option: bool = True  # size is counted in lots on options only (TICKET-797)
    legs: tuple[Leg, ...] = ()  # empty for a single leg
    lines: tuple[TradeLine, ...] = ()  # every leg, one for a single trade; none in old fixtures
    uncapped: bool = False  # can lose without limit, whatever it is measured against
    premium: Decimal | None = None  # price x quantity on one bought option, never a denominator

    @property
    def is_win(self) -> bool:
        return self.net > 0

    @property
    def is_loss(self) -> bool:
        return self.net < 0

    @property
    def is_scratch(self) -> bool:
        return self.net == 0

    @property
    def closed_same_day(self) -> bool:
        """Closed on the date it was opened, in the instrument's zone.

        trading_day is the entry's date in that zone and the loader gives exit_ts in the
        same zone (definitions 1), so the two compare without a clock of their own.
        """
        return self.exit_ts.date().isoformat() == self.trading_day

    @property
    def instrument(self) -> str:
        """The trade's name on a row. A position of several legs is named by its underlying."""
        if len(self.lines) == 1:
            return self.lines[0].instrument
        return f"{self.symbol} · {len(self.lines)} legs" if self.lines else self.symbol

    @property
    def result_percent(self) -> Decimal | None:
        """The result as a share of the premium, to one decimal. Shown beside what was paid
        and never used as R (feedback 12)."""
        return _round(self.net / self.premium * 100, "0.1") if self.premium else None


def load_trips(rows: list[dict[str, Any]]) -> list[Trip]:
    """Build trips from fixture or database rows, in entry order."""
    trips = [
        Trip(
            trip_id=row["trip_id"],
            symbol=row["symbol"],
            trading_day=row["trading_day"],
            entry_ts=datetime.fromisoformat(row["entry_ts"]),
            exit_ts=datetime.fromisoformat(row["exit_ts"]),
            holding_seconds=int(row["holding_seconds"]),
            net=Decimal(str(row["net"])),
            lots=int(row["lots"]),
            risk_unit_source=s.RiskUnitSourceV1(row["risk_unit_source"]),
            is_option=row.get("segment", "OPT") == "OPT",
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
    return Decimal(format(value.normalize(), "f"))  # 50, not 5E+1


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
class ShareOfLosses:
    five_day_sum: Decimal
    total: Decimal
    share_percent: Decimal | None
    shown_as_percentage: bool
    other_days_count: int
    other_days_net: Decimal
    state: s.ResultState
    worst_day_count: int = 0
    trading_day_count: int = 0
    days_percent: Decimal | None = None


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
    outside: int = 0  # TICKET-836: trips outside the B2 population, Table 1's third row
    outside_net: Decimal = Decimal(0)
    outside_mean: Decimal | None = None


@dataclass(frozen=True)
class BreakEven:
    """The win rate at which these average winners and losers would net to nothing."""

    average_winner: Decimal | None
    average_loser: Decimal | None
    percent: Decimal | None


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
class HoldingSeries:
    """Seconds each trade was held, in entry order, split by how it ended."""

    winners_seconds: list[int]
    losers_seconds: list[int]


@dataclass(frozen=True)
class HourResult:
    hour: int
    net: Decimal
    trips: int
    small_sample: bool


@dataclass(frozen=True)
class ClockHour:
    """One hour on one book's clock."""

    hour: int
    net: Decimal
    trips: int
    per_trade: Decimal
    small_sample: bool
    win_rate: Decimal | None  # as strike_rate reads it; none under CLOCK_MINIMUM_TRADES
    win_rate_state: s.ResultState


@dataclass(frozen=True)
class BookClock:
    book: str  # trade_book's name for it
    hours: list[ClockHour]
    trips: int
    net: Decimal
    largest: ClockHour
    larger_per_trade: ClockHour | None


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
class TradesPastNumber:
    """Same-day trades that lost more than the number in force the day they were opened."""

    count: int
    trip_ids: list[str]
    measured: int  # same-day trades with a number in force
    before_number: int  # same-day trades with none in force yet
    held_past_day: int  # positions left out, as every same-day figure leaves them out
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


def daily_series(trips: list[Trip]) -> list[DayNet]:
    """Net and trade count for every trading day with a trade, in date order.

    The one place a day's net is decided: the worst-days and busiest-day charts draw
    it (B2), and five_worst_days picks from it.
    """
    return [
        DayNet(day, sum((t.net for t in day_trips), Decimal(0)), len(day_trips))
        for day, day_trips in _by_day(trips).items()
    ]


def five_worst_days(trips: list[Trip]) -> FiveWorstDays:
    """Sum of net per trading day, ascending, first five. Ties: earlier date first."""
    if not trips:
        return FiveWorstDays((), Decimal(0), s.ResultState.INSUFFICIENT_SAMPLE)
    worst = sorted(daily_series(trips), key=lambda d: (d.net, d.trading_day))[:5]
    return FiveWorstDays(
        days=tuple(worst),
        sum=sum((d.net for d in worst), Decimal(0)),
        state=s.ResultState.COUNTED_FACT,
    )


def _whole_percent(part: Decimal, whole: Decimal) -> Decimal:
    """A whole number, and never 0 for a part that is really there: "about 13%", not 12.87%."""
    return max(Decimal(1), (part / whole * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def share_of_losses(trips: list[Trip]) -> ShareOfLosses:
    """The five worst days' losses as a share of all losing days (definitions 1).

    Never of the net result. Gains and losses cancel in a net, so it has no floor or
    ceiling: the same five days could read 80%, 930% or a negative number, and a large
    winning day would move a figure about losses. A history with no losing day has
    nothing to measure, so it has no percentage and the pages give the rupees alone.
    """
    worst = five_worst_days(trips)
    if worst.state is not s.ResultState.COUNTED_FACT:
        return ShareOfLosses(Decimal(0), Decimal(0), None, False, 0, Decimal(0),
                             s.ResultState.INSUFFICIENT_SAMPLE)

    series = daily_series(trips)
    total = sum((t.net for t in trips), Decimal(0))
    worst_days = {d.trading_day for d in worst.days}
    other_trips = [t for t in trips if t.trading_day not in worst_days]
    other_days = {t.trading_day for t in other_trips}
    other_net = sum((t.net for t in other_trips), Decimal(0))

    all_losses = sum((d.net for d in series if d.net < 0), Decimal(0))
    worst_losses = sum((d.net for d in worst.days if d.net < 0), Decimal(0))
    shown = all_losses < 0

    return ShareOfLosses(
        five_day_sum=worst.sum, total=total,
        share_percent=_whole_percent(worst_losses, all_losses) if shown else None,
        shown_as_percentage=shown,
        other_days_count=len(other_days), other_days_net=other_net,
        state=s.ResultState.COUNTED_FACT,
        worst_day_count=len(worst.days),
        trading_day_count=len(series),
        days_percent=_whole_percent(Decimal(len(worst.days)), Decimal(len(series))),
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


@dataclass(frozen=True)
class HeldPastDay:
    """Positions closed on a later date than they were opened, winners and losers alike."""

    trips: list[Trip]
    count: int
    net: Decimal


def same_day_trips(trips: list[Trip]) -> list[Trip]:
    return [t for t in trips if t.closed_same_day]


def held_past_day(trips: list[Trip]) -> HeldPastDay:
    held = [t for t in trips if not t.closed_same_day]
    return HeldPastDay(trips=held, count=len(held), net=sum((t.net for t in held), Decimal(0)))


@dataclass(frozen=True)
class OptionResult:
    """What the option trades came to, and the largest held gain outside them."""

    net: Decimal
    count: int
    held_gain: Trip | None
    held_gain_days: int | None


def option_result(trips: list[Trip]) -> OptionResult | None:
    """Options only; None when there are none. Stated side by side, never netted."""
    options = [t for t in trips if t.is_option]
    if not options:
        return None
    gains = [t for t in trips if not t.is_option and not t.closed_same_day and t.is_win]
    gain = max(gains, key=lambda t: t.net, default=None)
    days = (gain.exit_ts.date() - gain.entry_ts.date()).days if gain else None
    return OptionResult(
        net=sum((t.net for t in options), Decimal(0)), count=len(options),
        held_gain=gain, held_gain_days=days,
    )


def best_five(trips: list[Trip]) -> list[Trip]:
    """Highest net, descending. Ties: earlier entry first. No winsorising."""
    return sorted(trips, key=lambda t: (-t.net, t.entry_ts))[:5]


def worst_five(trips: list[Trip]) -> list[Trip]:
    """Lowest net, ascending. Ties: earlier entry first."""
    return sorted(trips, key=lambda t: (t.net, t.entry_ts))[:5]


HOLDING_AT_LEAST_SECONDS = 30 * 24 * 60 * 60
"""A stock or ETF held this long is a holding, not a trade, for the money fact's headline.

An option held overnight or a share held for a week is still a trade to the person who
placed it, and "your best trades weren't trades" would be false of him.
"""
MOST_OF_FIVE = 3
FIVE = 5
EVENING_FROM_HOUR = 17  # the equity markets have shut; only the commodity evening is open
LATE_EVENING_FROM_HOUR = 20


@dataclass(frozen=True)
class TopHolding:
    """The one instrument that made most of what was held past the day."""

    instrument: str
    net: Decimal
    longest_seconds: int


@dataclass(frozen=True)
class MoneyFound:
    """What the best and worst lists found, so a sentence is said only when it is true.

    best_were_holdings: most of the five biggest results in the whole file are winning stocks
    or ETFs held a month or more. same_place: both lists are full, share no trade and sit in
    one book. evening_told: most of each list opened in the evening; worst_late then says how
    many of the worst opened later still. durations_told: the best five all made money and the
    worst five all lost it, so "ran" and "lost" are true of every row; the medians are None
    otherwise. Describes what happened; says nothing about what to do.
    """

    same_day_count: int
    same_day_net: Decimal
    best_net: Decimal
    worst_net: Decimal
    holdings_in_best: int
    best_were_holdings: bool
    same_place: str | None
    best_books: tuple[tuple[str, int], ...]
    worst_books: tuple[tuple[str, int], ...]
    best_evening: int
    worst_evening: int
    worst_late: int
    evening_told: bool
    worst_mostly_late: bool
    durations_told: bool
    best_median_seconds: int | None
    worst_median_seconds: int | None
    worst_median_loss: Decimal | None
    top_holding: TopHolding | None


def _is_holding(t: Trip) -> bool:
    return (
        not t.closed_same_day
        and t.is_win
        and trade_book(t) == "Stocks and ETFs"
        and t.holding_seconds >= HOLDING_AT_LEAST_SECONDS
    )


def _books(trips: list[Trip]) -> tuple[tuple[str, int], ...]:
    return tuple(Counter(trade_book(t) for t in trips).most_common())


def _top_holding(held: HeldPastDay) -> TopHolding | None:
    """The instrument that made more than half of a positive total, and no more than all of it."""
    if held.net <= 0:
        return None
    by_instrument: dict[str, list[Trip]] = {}
    for t in held.trips:
        by_instrument.setdefault(t.instrument, []).append(t)
    name, trips = max(by_instrument.items(), key=lambda kv: sum(t.net for t in kv[1]))
    net = sum((t.net for t in trips), Decimal(0))
    if net * 2 <= held.net or net > held.net:
        return None
    return TopHolding(name, net, max(t.holding_seconds for t in trips))


def money_found(trips: list[Trip]) -> MoneyFound:
    same_day = same_day_trips(trips)
    best, worst = best_five(same_day), worst_five(same_day)
    full = len(best) == FIVE and len(worst) == FIVE
    apart = {t.trip_id for t in best}.isdisjoint(t.trip_id for t in worst)
    books = {trade_book(t) for t in best + worst}
    holdings = sum(_is_holding(t) for t in best_five(trips))
    best_evening = sum(t.entry_ts.hour >= EVENING_FROM_HOUR for t in best)
    worst_evening = sum(t.entry_ts.hour >= EVENING_FROM_HOUR for t in worst)
    worst_late = sum(t.entry_ts.hour >= LATE_EVENING_FROM_HOUR for t in worst)
    durations = full and all(t.is_win for t in best) and all(t.is_loss for t in worst)
    return MoneyFound(
        same_day_count=len(same_day),
        same_day_net=sum((t.net for t in same_day), Decimal(0)),
        best_net=sum((t.net for t in best), Decimal(0)),
        worst_net=sum((t.net for t in worst), Decimal(0)),
        holdings_in_best=holdings,
        best_were_holdings=bool(same_day) and holdings >= MOST_OF_FIVE,
        same_place=books.pop() if full and apart and len(books) == 1 else None,
        best_books=_books(best),
        worst_books=_books(worst),
        best_evening=best_evening,
        worst_evening=worst_evening,
        worst_late=worst_late,
        evening_told=full and best_evening >= MOST_OF_FIVE and worst_evening >= MOST_OF_FIVE,
        worst_mostly_late=worst_late >= MOST_OF_FIVE,
        durations_told=durations,
        best_median_seconds=median(t.holding_seconds for t in best) if durations else None,
        worst_median_seconds=median(t.holding_seconds for t in worst) if durations else None,
        worst_median_loss=median(-t.net for t in worst) if durations else None,
        top_holding=_top_holding(held_past_day(trips)),
    )


def b2_observations(trips: list[Trip]) -> list[Obs]:
    """The trips as the shared B2 definition and its shuffle test read them, in net rupees."""
    day_index = {day: i for i, day in enumerate(sorted({t.trading_day for t in trips}))}
    return [
        Obs(day=day_index[t.trading_day],
            entry_at=t.entry_ts.timestamp(),
            exit_at=t.exit_ts.timestamp(),
            r=float(t.net))
        for t in trips
    ]


def two_straight_losses(trips: list[Trip]) -> TwoStraightLosses:
    """The research library's B2 population and condition, on this trader's trips.

    One function decides this, in services/shared/conditions. The library passes R
    where this passes net rupees; the condition reads only the sign, so both get
    the same answer on the same trips (PRD 6.3).
    """
    if not trips:
        return TwoStraightLosses(0, 0, 0, [], Decimal(0), Decimal(0), None, None,
                                 s.ResultState.INSUFFICIENT_SAMPLE)

    in_pop, cond = population_and_condition(b2_observations(trips))

    condition_trips = [t for t, flag in zip(trips, cond, strict=True) if flag]
    comparison_trips = [
        t for t, pop, flag in zip(trips, in_pop, cond, strict=True) if pop and not flag
    ]
    condition_net = sum((t.net for t in condition_trips), Decimal(0))
    comparison_net = sum((t.net for t in comparison_trips), Decimal(0))
    # TICKET-836: every trip outside the population, so the table has a row for trades not down.
    outside_trips = [t for t, pop in zip(trips, in_pop, strict=True) if not pop]
    outside_net = sum((t.net for t in outside_trips), Decimal(0))

    return TwoStraightLosses(
        population=int(in_pop.sum()),
        condition=len(condition_trips),
        comparison=len(comparison_trips),
        condition_trip_ids=[t.trip_id for t in condition_trips],
        condition_net=condition_net,
        comparison_net=comparison_net,
        condition_mean=_trim(_round(condition_net / len(condition_trips))) if condition_trips else None,
        comparison_mean=_trim(_round(comparison_net / len(comparison_trips))) if comparison_trips else None,
        outside=len(outside_trips),
        outside_net=outside_net,
        outside_mean=_trim(_round(outside_net / len(outside_trips))) if outside_trips else None,
        state=s.ResultState.COUNTED_FACT,
    )


@lru_cache(maxsize=64)
def _post_loss_gate(obs: tuple[Obs, ...]) -> bool:
    return b2_shuffle.shuffle_test(obs).passes


def post_loss_sentence_may_show(trips: list[Trip]) -> bool:
    """May a page state a direction for trades after two straight losses?

    Only if B2's shuffle test passes on this trader's own file, in B2's own direction. Every page
    of a record asks, so a file is tested once per process; the test's seed is fixed, so a
    restart gets the same answer. Closed, the page says "No difference we can stand behind."
    beside the same numbers, and that isn't a finding about the trader.
    """
    return _post_loss_gate(tuple(b2_observations(trips))) if trips else False


def subset(trips: list[Trip], trip_ids: list[str]) -> list[Trip]:
    """The named trips, in their original order. For comparing a group to the rest."""
    wanted = set(trip_ids)
    return [t for t in trips if t.trip_id in wanted]


def complement(trips: list[Trip], trip_ids: list[str]) -> list[Trip]:
    """Everything but the named trips."""
    wanted = set(trip_ids)
    return [t for t in trips if t.trip_id not in wanted]


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


def break_even(trips: list[Trip]) -> BreakEven:
    """Average loser over average winner plus average loser. Scratches are in neither.

    Needs a winner and a loser: with one side empty there is nothing to balance.
    """
    wins = [t.net for t in trips if t.is_win]
    losses = [-t.net for t in trips if t.is_loss]
    if not wins or not losses:
        return BreakEven(None, None, None)
    winner = sum(wins, Decimal(0)) / len(wins)
    loser = sum(losses, Decimal(0)) / len(losses)
    return BreakEven(winner, loser, _trim(_round(loser / (winner + loser) * 100, "0.1")))


def average_lots(trips: list[Trip]) -> AverageLots:
    """Mean lots on option trades only. A share's "lot" is one share, not a size."""
    options = [t for t in trips if t.is_option]
    if not options:
        return AverageLots(0, None, s.ResultState.INSUFFICIENT_SAMPLE)
    total = sum(t.lots for t in options)
    return AverageLots(
        total_lots=total,
        mean=_trim(_round(Decimal(total) / Decimal(len(options)), "0.001")),
        state=s.ResultState.COUNTED_FACT,
    )


def holding_series(trips: list[Trip]) -> HoldingSeries:
    """Each trade's hold in entry order, winners and losers apart; scratches in neither.

    The one place a hold is sorted by outcome: the hold chart draws a dot per value
    (B2), and holding_time takes its medians from the same two lists.
    """
    return HoldingSeries(
        winners_seconds=[t.holding_seconds for t in trips if t.is_win],
        losers_seconds=[t.holding_seconds for t in trips if t.is_loss],
    )


def holding_time(trips: list[Trip]) -> HoldingTime:
    """Median hold by outcome. Scratches excluded; a zero median gives no ratio."""
    held = holding_series(trips)
    winners, losers = held.winners_seconds, held.losers_seconds
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


def clock_hour_of(hour: int, trips: list[Trip]) -> ClockHour:
    """One hour on one book's clock. ₹ per trade is arithmetic and shows at any count.

    The total is back to the paise a broker reports in: a fill split across parcels sums to
    -99.99...9, and the whole-rupee cut would then print a rupee less than the file has.
    """
    rate = strike_rate(trips) if len(trips) >= CLOCK_MINIMUM_TRADES else None
    net = _round(sum((t.net for t in trips), Decimal(0)))
    return ClockHour(
        hour=hour,
        net=net,
        trips=len(trips),
        per_trade=net / len(trips),
        small_sample=len(trips) < SMALL_SAMPLE_TRIPS,
        win_rate=rate.rate_percent if rate else None,
        win_rate_state=rate.state if rate else s.ResultState.INSUFFICIENT_SAMPLE,
    )


def _larger_per_trade(hours: list[ClockHour], largest: ClockHour) -> ClockHour | None:
    """The hour larger per trade than the largest total, among hours of 30 trades or more.

    A one-trade hour is always "large per trade", so it is not set beside a total. Whole
    rupees, as the page prints them: two hours that read the same are not larger or smaller.
    """
    counted = [h for h in hours if h.trips >= CLOCK_MINIMUM_TRADES]
    if not counted:
        return None
    other = max(counted, key=lambda h: (abs(h.per_trade), h.trips))
    return other if int(abs(other.per_trade)) > int(abs(largest.per_trade)) else None


def clocks_by_book(trips: list[Trip]) -> list[BookClock]:
    """One clock per book, most trades first. Hours are the instrument's own, as result_by_hour's.

    The largest hour is the largest result either way, in rupees; two the same size read
    the one with more trades, then the earlier. It says what happened and calls no hour good.
    """
    books: dict[str, dict[int, list[Trip]]] = {}
    for trip in trips:
        books.setdefault(trade_book(trip), {}).setdefault(trip.entry_ts.hour, []).append(trip)
    clocks = []
    for book, by_hour in books.items():
        hours = [clock_hour_of(hour, by_hour[hour]) for hour in sorted(by_hour)]
        largest = max(hours, key=lambda h: (abs(h.net), h.trips, -h.hour))
        clocks.append(BookClock(
            book=book,
            hours=hours,
            trips=sum(h.trips for h in hours),
            net=sum((h.net for h in hours), Decimal(0)),
            largest=largest,
            larger_per_trade=_larger_per_trade(hours, largest),
        ))
    return sorted(clocks, key=lambda c: (-c.trips, c.book))


def lead_clock(clocks: list[BookClock]) -> BookClock | None:
    """The clock whose largest hour is the largest across the books; the fact leads with it."""
    if not clocks:
        return None
    return max(clocks, key=lambda c: (abs(c.largest.net), c.largest.trips, c.trips))


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


def costliest_losing_run(trips: list[Trip]) -> LosingRun:
    """The losing run that lost the most rupees, read as longest_losing_run reads a run.

    Two that cost the same read the one with more trades, then the earlier. Each run is
    said alone: the rupees are never added up across runs, because the winners between
    them are left out and the total would mislead.
    """
    runs: list[list[Trip]] = []
    current: list[Trip] = []
    for trip in trips:
        if trip.is_loss:
            current.append(trip)
        else:
            current = []
            continue
        if len(current) == 1:
            runs.append(current)
    if not runs:
        return LosingRun(0, [], False, [], s.ResultState.INSUFFICIENT_SAMPLE)
    worst = min(runs, key=lambda run: (_run_net(run), -len(run)))
    days = sorted({t.trading_day for t in worst})
    return LosingRun(
        length=len(worst), trip_ids=[t.trip_id for t in worst],
        crosses_days=len(days) > 1, days=days, state=s.ResultState.COUNTED_FACT,
    )


def _run_net(trips: list[Trip]) -> Decimal:
    """Back to the paise a broker reports in: a fill split across parcels sums just short."""
    return _round(sum((t.net for t in trips), Decimal(0)))


RE_ENTRY_SECONDS = 120
""""Back in within 2 minutes", from the previous trade's exit. Exactly two minutes counts.

A count on one day in one book, as the ruling on TICKET-820 allows. How fast a trader goes
back in across days or books is pre-registered research, and no page says it."""


@dataclass(frozen=True)
class SizeRise:
    """The first time a run's size went up, and how far it climbed before it next fell."""

    losses_before: int
    steps: list[int]


@dataclass(frozen=True)
class BackIn:
    within: int  # of those, how many inside RE_ENTRY_SECONDS
    of: int  # re-entries on the day: a trade opened after the last one closed


@dataclass(frozen=True)
class RunStory:
    """One losing run, as what happened: when, in what, what it cost, and what came next."""

    trades: list[Trip]
    length: int
    net: Decimal
    days: list[str]
    books: list[str]  # most trades first, then as they came
    same_day: bool  # opened and closed on one date, so a span of time can be said
    span_seconds: int
    gaps: dict[str, int]  # trip_id: seconds since the previous exit; negative if it was still open
    flips: int
    size: SizeRise | None
    back_in: BackIn | None
    after: Trip | None  # the first trade after the run
    last_day: str
    last_day_net: Decimal
    running: list[tuple[Trip, Decimal]]  # the run and the trade after, each as it closed
    lowest: Decimal
    last: Decimal


def call_or_put(trip: Trip) -> str | None:
    """"CE" or "PE" on one option. A position of several legs is neither, and nor is a share."""
    if not trip.is_option or len(trip.lines) != 1:
        return None
    return trip.lines[0].option_type or None


def _gaps(trades: list[Trip]) -> dict[str, int]:
    """Seconds from each trade back to the exit of the one before, on the same trading day.

    A night is not a gap, so a day's first trade has none. Negative when the one before was
    still open.
    """
    return {
        cur.trip_id: int((cur.entry_ts - prev.exit_ts).total_seconds())
        for prev, cur in pairwise(trades)
        if cur.trading_day == prev.trading_day
    }


def _flips(trades: list[Trip]) -> int:
    """Calls to puts and back, between neighbouring trades on one underlying."""
    return sum(
        1
        for prev, cur in pairwise(trades)
        if call_or_put(prev) and call_or_put(cur)
        and call_or_put(prev) != call_or_put(cur)
        and book_of(prev.symbol) == book_of(cur.symbol)
    )


def _size_rise(trades: list[Trip]) -> SizeRise | None:
    """The first rise in quantity, and the climb until it next fell.

    Quantities compare only on one instrument, each trade with one size: 100 of one contract
    against 200 of another is not a rise, and a position of several legs has no one size.
    """
    if len({t.symbol for t in trades}) != 1 or any(len(t.lines) != 1 for t in trades):
        return None
    sizes = [t.lines[0].quantity for t in trades]
    if not all(sizes):
        return None
    first = next((i for i in range(1, len(sizes)) if sizes[i] > sizes[i - 1]), None)
    if first is None:
        return None
    steps = [sizes[first - 1], sizes[first]]
    for size in sizes[first + 1:]:
        if size < steps[-1]:
            break
        if size > steps[-1]:
            steps.append(size)
    return SizeRise(losses_before=first, steps=steps)


def _back_in(gaps: dict[str, int], days: list[str], books: list[str]) -> BackIn | None:
    """How many re-entries came inside two minutes: one day and one book, or nothing is said."""
    if len(days) != 1 or len(books) != 1:
        return None
    returns = [g for g in gaps.values() if g >= 0]
    within = sum(g <= RE_ENTRY_SECONDS for g in returns)
    return BackIn(within=within, of=len(returns)) if within else None


def run_story(trips: list[Trip], trip_ids: list[str]) -> RunStory | None:
    """A run's facts, computed from its own trades. None for no run. States facts, never causes."""
    trades = subset(trips, trip_ids)
    if not trades:
        return None
    last = trips.index(trades[-1])
    after = trips[last + 1] if last + 1 < len(trips) else None
    days = sorted({t.trading_day for t in trades})
    counts: dict[str, int] = {}
    for t in trades:
        counts[trade_book(t)] = counts.get(trade_book(t), 0) + 1
    books = sorted(counts, key=lambda book: -counts[book])
    gaps = _gaps(trades)
    started, ended = trades[0].entry_ts, max(t.exit_ts for t in trades)
    with_after = _gaps([trades[-1], after]) if after else {}
    running: list[tuple[Trip, Decimal]] = []
    total = Decimal(0)
    for t in sorted([*trades, after] if after else trades, key=lambda t: t.exit_ts):
        total += t.net
        running.append((t, _round(total)))
    return RunStory(
        trades=trades,
        length=len(trades),
        net=_run_net(trades),
        days=days,
        books=books,
        same_day=len(days) == 1 and all(t.closed_same_day for t in trades),
        span_seconds=int((ended - started).total_seconds()),
        gaps={**gaps, **with_after},
        flips=_flips(trades),
        size=_size_rise(trades),
        back_in=_back_in(gaps, days, books),
        after=after,
        last_day=days[-1],
        last_day_net=_run_net([t for t in trips if t.trading_day == days[-1]]),
        running=running,
        lowest=min(value for _, value in running),
        last=running[-1][1],
    )


LOSS_SIZES_MINIMUM = 20
"""Below this, "one in twenty" is not something the file can say."""


@dataclass(frozen=True)
class LossSizes:
    """A trader's losses by size, in whole rupees. Describes them and suggests nothing."""

    half: int
    three_quarters: int
    nine_tenths: int
    one_in_twenty: int
    biggest: int


def loss_sizes(trips: list[Trip]) -> LossSizes | None:
    """Read off the ranked losses. "Or less" rounds up, "more than" down, so both stay true."""
    losses = sorted(-t.net for t in trips if t.is_loss)
    if len(losses) < LOSS_SIZES_MINIMUM:
        return None

    def at(share: Decimal) -> Decimal:
        return losses[ceil(share * len(losses)) - 1]

    def up(value: Decimal) -> int:
        return int(value.to_integral_value(rounding=ROUND_CEILING))

    def down(value: Decimal) -> int:
        return int(value.to_integral_value(rounding=ROUND_FLOOR))

    return LossSizes(
        half=up(at(Decimal("0.5"))),
        three_quarters=up(at(Decimal("0.75"))),
        nine_tenths=up(at(Decimal("0.9"))),
        one_in_twenty=down(at(Decimal("0.95"))),
        biggest=up(losses[-1]),
    )


def book_of(symbol: str) -> str:
    """The book a trade belongs to. CRUDEOIL and CRUDEOILM are one book to a trader."""
    return "crude" if symbol.startswith("CRUDE") else symbol


def trade_book(trip: Trip) -> str:
    """The book a trade belongs to, in a trader's own words: one definition (TICKET-822).

    An option is its underlying's, with crude's two contracts as one. A share or an ETF is
    in one book with the other shares and ETFs, held or not; a future is in Futures.
    """
    if trip.is_option:
        book = book_of(trip.symbol)
        return "Crude options" if book == "crude" else f"{book} options"
    if trip.lines and trip.lines[0].segment == "EQ":
        return "Stocks and ETFs"
    return "Futures"


BOOK_ROW_MINIMUM = 30
"""Below this a book row, or a year of one, says "not enough trades to say". The framework's
standard n_min (framework_v1.yaml, B-series), reused rather than invented."""

QUICK_CLOSE_SECONDS = 300
"""Closed within five minutes, five itself included."""

BIG_LOSS_RUPEES = Decimal(1000)
"""A loss past this, not at it, is in the biggest-losers line. A plain round line, not a
figure from anyone's record."""


@dataclass(frozen=True)
class MathRow:
    """One book, or one year of a book: the sizes, and the two ways to break even.

    Below the minimum only the label, the count and the state are set, so a page has no
    figure to print by mistake.
    """

    label: str
    trades: int
    state: s.ResultState
    wins: int = 0
    losses: int = 0
    scratches: int = 0
    decided: int = 0  # winners and losers: a level trade is in neither
    win_percent: Decimal | None = None
    average_winner: Decimal | None = None
    average_loser: Decimal | None = None
    median_winner: Decimal | None = None
    median_loser: Decimal | None = None
    winners_median_seconds: int | None = None
    losers_median_seconds: int | None = None
    break_even_percent: Decimal | None = None
    more_winners: int | None = None
    winner_needed: Decimal | None = None
    winner_gap: Decimal | None = None


@dataclass(frozen=True)
class QuickCloses:
    """How many of a book's losers and winners were closed within five minutes, as shares."""

    losers_percent: int
    winners_percent: int

    @property
    def has_a_comparison(self) -> bool:
        """Zero against zero is no measured result, and reads as one (TICKET-859)."""
        return bool(self.losers_percent or self.winners_percent)


@dataclass(frozen=True)
class TopWinners:
    """The biggest tenth of a book's winners, and their share of what its winners made."""

    count: int
    winners: int
    percent: int


@dataclass(frozen=True)
class BiggestLosers:
    """Losers past the line, against the book's other losers. Each median is its own."""

    above: Decimal
    count: int
    trades_percent: int
    losses_percent: int
    median_seconds: int
    others_median_seconds: int | None
    median_lots: int | None  # options only: a share's "lot" is one share, not a size
    others_median_lots: int | None


@dataclass(frozen=True)
class BookMath:
    """A book's row, its years, and the lines under it. Only a counted book has the rest."""

    whole: MathRow
    years: tuple[MathRow, ...] = ()
    quick_closes: QuickCloses | None = None
    top_winners: TopWinners | None = None
    biggest_losers: BiggestLosers | None = None


def _share(part: Decimal | int, whole: Decimal | int) -> int:
    """A whole percentage. Unlike _whole_percent, nothing at all reads 0, not 1."""
    return int(_round(Decimal(part) / Decimal(whole) * 100, "1")) if part else 0


def _more_winners(row_wins: list[Decimal], row_losses: list[Decimal], be: BreakEven) -> int | None:
    """Winners that would have to be losers' places for the win rate to reach break-even, with
    the trades and the averages as they are. None when the book is already at or past it,
    which is the same as winners having made at least what losers lost. Exact from there on:
    a book short by less than half a winner still says one."""
    if sum(row_wins, Decimal(0)) >= sum(row_losses, Decimal(0)):
        return None
    rate = be.average_loser / (be.average_winner + be.average_loser)
    decided = len(row_wins) + len(row_losses)
    return max(1, int(_round(rate * decided - len(row_wins), "1")))


def math_row(label: str, trips: list[Trip]) -> MathRow:
    """The row for these trades. Break-even is average loser / (average winner + average
    loser); the average winner needed is the same identity solved for the winner instead,
    average loser x losers / winners. Both come from the averages break_even() decides."""
    strike = strike_rate(trips)
    if len(trips) < BOOK_ROW_MINIMUM or strike.state is not s.ResultState.COUNTED_FACT:
        return MathRow(label, len(trips), s.ResultState.INSUFFICIENT_SAMPLE)
    wins = [t.net for t in trips if t.is_win]
    losses = [-t.net for t in trips if t.is_loss]
    be = break_even(trips)
    held = holding_time(trips)
    balanced = be.percent is not None
    needed = be.average_loser * len(losses) / len(wins) if balanced else None
    return MathRow(
        label=label,
        trades=len(trips),
        state=s.ResultState.COUNTED_FACT,
        wins=strike.wins,
        losses=strike.losses,
        scratches=strike.scratches,
        decided=strike.wins + strike.losses,
        win_percent=strike.rate_percent,
        average_winner=sum(wins, Decimal(0)) / len(wins) if wins else None,
        average_loser=sum(losses, Decimal(0)) / len(losses) if losses else None,
        median_winner=median(wins) if wins else None,
        median_loser=median(losses) if losses else None,
        winners_median_seconds=held.winners_median_seconds,
        losers_median_seconds=held.losers_median_seconds,
        break_even_percent=be.percent,
        more_winners=_more_winners(wins, losses, be) if balanced else None,
        winner_needed=needed,
        winner_gap=needed - be.average_winner if balanced else None,
    )


def _quick_closes(trips: list[Trip]) -> QuickCloses:
    def quick(side: list[Trip]) -> int:
        closed = sum(1 for t in side if t.holding_seconds <= QUICK_CLOSE_SECONDS)
        return _share(closed, len(side)) if side else 0

    return QuickCloses(
        losers_percent=quick([t for t in trips if t.is_loss]),
        winners_percent=quick([t for t in trips if t.is_win]),
    )


def _top_winners(trips: list[Trip]) -> TopWinners | None:
    wins = sorted((t.net for t in trips if t.is_win), reverse=True)
    if not wins:
        return None
    count = ceil(len(wins) / 10)
    return TopWinners(count, len(wins), _share(sum(wins[:count]), sum(wins)))


def _biggest_losers(trips: list[Trip]) -> BiggestLosers | None:
    losers = [t for t in trips if t.is_loss]
    big = [t for t in losers if -t.net > BIG_LOSS_RUPEES]
    if not big:
        return None
    others = [t for t in losers if -t.net <= BIG_LOSS_RUPEES]

    def lots(side: list[Trip]) -> int | None:
        sized = [t.lots for t in side if t.is_option]
        return int(median(sized)) if sized else None

    return BiggestLosers(
        above=BIG_LOSS_RUPEES,
        count=len(big),
        trades_percent=_share(len(big), len(trips)),
        losses_percent=_share(sum(-t.net for t in big), sum(-t.net for t in losers)),
        median_seconds=int(median(t.holding_seconds for t in big)),
        others_median_seconds=int(median(t.holding_seconds for t in others)) if others else None,
        median_lots=lots(big),
        others_median_lots=lots(others),
    )


def math_by_book(trips: list[Trip]) -> list[BookMath]:
    """A book's math, per book by trade_book and per year, biggest book first. Pass the
    same-day trades: a holding is not a trade the day's decisions made."""
    books: dict[str, list[Trip]] = {}
    for trip in trips:
        books.setdefault(trade_book(trip), []).append(trip)
    out = []
    for book, book_trips in sorted(books.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        whole = math_row(book, book_trips)
        if whole.state is not s.ResultState.COUNTED_FACT:
            out.append(BookMath(whole))
            continue
        years: dict[str, list[Trip]] = {}
        for trip in book_trips:
            years.setdefault(trip.trading_day[:4], []).append(trip)
        out.append(BookMath(
            whole=whole,
            years=tuple(math_row(year, years[year]) for year in sorted(years)),
            quick_closes=_quick_closes(book_trips),
            top_winners=_top_winners(book_trips),
            biggest_losers=_biggest_losers(book_trips),
        ))
    return out


@dataclass(frozen=True)
class StripTrade:
    """One trade on the call/put strip. side is CE, PE, or both for a position of several legs."""

    side: str
    net: Decimal


@dataclass(frozen=True)
class BusiestDayStory:
    """What a day was made of, for any trader (TICKET-827). A part that is not true of the day
    is None, and the page says something plainer: nothing here assumes one strike or one book.

    book is the book with more than half of the day's trades, at least two of them. Everything
    from book_net to held_past_day reads that book's trades only. net is the whole day, every
    book, which is what the list under the story adds up to.
    """

    day: str
    trades: int
    net: Decimal
    book: str | None = None
    book_trades: int = 0
    book_net: Decimal | None = None
    strike: Decimal | None = None  # the one strike every leg was on
    strikes: int = 0  # how many strikes, when every leg has one
    lots: int | None = None  # the one size of every trade, options with a single leg only
    lots_low: int | None = None
    lots_high: int | None = None
    switches: int | None = None  # call to put or back, one single-leg trade to the next
    one_side: str | None = None  # CE or PE, when every trade in the book was that side
    only_positions: bool = False
    started: datetime | None = None  # the book's first entry
    ended: datetime | None = None  # its last exit, or last entry if one stayed open past the day
    median_hold_seconds: int | None = None  # None if one stayed open past the day
    longest_hold_seconds: int | None = None
    holds_alike: bool = False  # every hold within a factor of two of the median
    held_past_day: int = 0
    strip: tuple[StripTrade, ...] = ()
    strip_is_the_book: bool = False


def _strip_side(trip: Trip) -> str | None:
    if len(trip.lines) > 1:
        return "both"
    if trip.lines and trip.lines[0].option_type in ("CE", "PE"):
        return trip.lines[0].option_type
    return None


def busiest_day_story(trips: list[Trip], day: str) -> BusiestDayStory:
    """One day told in its own terms: which book, which strike, what size, how often the side
    changed, how long each was held. See BusiestDayStory for what each part covers."""
    on_day = sorted((t for t in trips if t.trading_day == day), key=lambda t: (t.entry_ts, t.trip_id))
    by_book: dict[str, list[Trip]] = {}
    for t in on_day:
        by_book.setdefault(trade_book(t), []).append(t)
    book = next((b for b, ts in by_book.items() if len(ts) >= 2 and len(ts) * 2 > len(on_day)), None)
    book_trips = by_book[book] if book else []
    book_is_options = bool(book_trips) and book_trips[0].is_option
    drawn = book_trips if book_is_options else [t for t in on_day if t.is_option]
    story = BusiestDayStory(
        day=day,
        trades=len(on_day),
        net=sum((t.net for t in on_day), Decimal(0)),
        strip=tuple(StripTrade(side, t.net) for t in drawn if (side := _strip_side(t))),
        strip_is_the_book=book_is_options,
    )
    if not book_trips:
        return story

    open_past_day = sum(not t.closed_same_day for t in book_trips)
    parts: dict[str, Any] = {
        "book": book,
        "book_trades": len(book_trips),
        "book_net": sum((t.net for t in book_trips), Decimal(0)),
        "started": book_trips[0].entry_ts,
        "ended": book_trips[-1].entry_ts if open_past_day else max(t.exit_ts for t in book_trips),
        "held_past_day": open_past_day,
    }
    if not open_past_day:
        holds = [t.holding_seconds for t in book_trips]
        middle = int(median(holds))
        parts.update(
            median_hold_seconds=middle,
            longest_hold_seconds=max(holds),
            holds_alike=all(middle <= 2 * h and h <= 2 * middle for h in holds),
        )
    if book_is_options and all(t.lines for t in book_trips):
        parts.update(_option_parts(book_trips))
    return replace(story, **parts)


def _option_parts(trips: list[Trip]) -> dict[str, Any]:
    """Strike, size and side, each only when every trade in the book can answer it."""
    parts: dict[str, Any] = {}
    strikes = {line.strike for t in trips for line in t.lines}
    if None not in strikes:
        parts["strikes"] = len(strikes)
        if len(strikes) == 1:
            parts["strike"] = next(iter(strikes))
    single = [t for t in trips if len(t.lines) == 1]
    if len(single) == len(trips):
        sizes = {t.lots for t in trips}
        if len(sizes) == 1:
            parts["lots"] = next(iter(sizes))
        else:
            parts.update(lots_low=min(sizes), lots_high=max(sizes))
    sides = [side for t in single if (side := _strip_side(t))]
    parts["only_positions"] = not single
    if sides:
        parts["switches"] = sum(a != b for a, b in pairwise(sides))
        if len(sides) == len(trips) and len(set(sides)) == 1:
            parts["one_side"] = sides[0]
    return parts


@dataclass(frozen=True)
class PremiumPaid:
    """What a typical bought option cost in one book, and how much of it a result was."""

    book: str
    paid: Decimal
    percent: int


def premium_by_book(trips: list[Trip]) -> list[PremiumPaid]:
    """Medians per book, biggest book first. Recorded for reading, never a denominator.

    Per book because a blend describes none of them. A book below the minimum is left out
    rather than pooled: a handful of unrelated instruments has no typical trade.
    """
    books: dict[str, list[Trip]] = {}
    for trip in trips:
        if trip.is_option and trip.premium:
            books.setdefault(book_of(trip.symbol), []).append(trip)
    read = []
    for book, options in sorted(books.items(), key=lambda kv: -len(kv[1])):
        results = [abs(t.net) / t.premium * 100 for t in options if not t.is_scratch]
        if len(results) < LOSS_SIZES_MINIMUM:
            continue
        read.append(PremiumPaid(
            book=book,
            paid=median(t.premium for t in options),
            percent=int(median(results).to_integral_value()),
        ))
    return read


NAMED_BOOK_MINIMUM = 20
"""Below this a book has no row of its own and goes in with the other options."""


@dataclass(frozen=True)
class Standout:
    """The one instrument that made at least half of what the non-option trades made."""

    symbol: str
    net: Decimal
    held_days: int  # calendar days, the longest it was held; 0 if closed the day it opened


@dataclass(frozen=True)
class BookResult:
    label: str
    net: Decimal
    trades: int
    worst_day: str | None  # the day this book lost most; None if it never lost a day
    worst_net: Decimal | None
    standout: Standout | None = None


@dataclass(frozen=True)
class Verdict:
    """The whole result, split the way the trader thinks of it. The books add up to it."""

    options_net: Decimal
    options_trades: int
    others_net: Decimal
    others_trades: int
    books: tuple[BookResult, ...]
    standout: Standout | None

    @property
    def options_size(self) -> Decimal:
        return abs(self.options_net)

    @property
    def others_size(self) -> Decimal:
        return abs(self.others_net)

    @property
    def made_back(self) -> bool:
        """"Made back" is only true of a part of what the options lost."""
        return bool(self.standout and self.options_net < 0 and self.standout.net < -self.options_net)


def _worst_of_book(trips: list[Trip]) -> tuple[str | None, Decimal | None]:
    days: dict[str, Decimal] = {}
    for trip in trips:
        days[trip.trading_day] = days.get(trip.trading_day, Decimal(0)) + trip.net
    day, net = min(days.items(), key=lambda kv: (kv[1], kv[0]))
    return (day, net) if net < 0 else (None, None)


def _book_result(label: str, trips: list[Trip], standout: Standout | None = None) -> BookResult:
    worst_day, worst_net = _worst_of_book(trips)
    return BookResult(label, sum((t.net for t in trips), Decimal(0)), len(trips), worst_day, worst_net, standout)


def _standout(others: list[Trip]) -> Standout | None:
    """Named only when the group made money and this one made at least half of it."""
    total = sum((t.net for t in others), Decimal(0))
    if total <= 0:
        return None
    by_symbol: dict[str, list[Trip]] = {}
    for trip in others:
        by_symbol.setdefault(trip.symbol, []).append(trip)
    symbol, trips = max(by_symbol.items(), key=lambda kv: sum(t.net for t in kv[1]))
    net = sum((t.net for t in trips), Decimal(0))
    if net * 2 < total:
        return None
    held = max((t.exit_ts.date() - t.entry_ts.date()).days for t in trips)
    return Standout(symbol, net, held)


def verdict(trips: list[Trip]) -> Verdict:
    """The result by book: every named option book, the other options, then the rest.

    Whole history, not same-day: this is what the file came to. A figure pooled into "other"
    is only a sum, which is why a book under the minimum can go there (a median could not).
    """
    options = [t for t in trips if t.is_option]
    others = [t for t in trips if not t.is_option]
    by_book: dict[str, list[Trip]] = {}
    for trip in options:
        by_book.setdefault(trade_book(trip), []).append(trip)
    named = {b: ts for b, ts in by_book.items() if len(ts) >= NAMED_BOOK_MINIMUM}
    pooled = [t for b, ts in by_book.items() if b not in named for t in ts]
    rows = sorted(
        (_book_result(b, ts) for b, ts in named.items()),
        key=lambda r: (r.net, r.label),
    )
    if pooled:
        rows.append(_book_result("Other options", pooled))
    standout = _standout(others)
    other_books: dict[str, list[Trip]] = {}
    for trip in others:
        other_books.setdefault(trade_book(trip), []).append(trip)
    for book, ts in sorted(other_books.items()):
        holds_it = standout is not None and any(t.symbol == standout.symbol for t in ts)
        rows.append(_book_result(book, ts, standout if holds_it else None))
    return Verdict(
        options_net=sum((t.net for t in options), Decimal(0)), options_trades=len(options),
        others_net=sum((t.net for t in others), Decimal(0)), others_trades=len(others),
        books=tuple(rows), standout=standout,
    )


@dataclass(frozen=True)
class WorstDayRow:
    trading_day: str
    books: tuple[str, ...]
    trades: int
    net: Decimal


@dataclass(frozen=True)
class WorstDayStory:
    """How the worst day went, from its first trade."""

    trading_day: str
    first_net: Decimal
    later: int
    net: Decimal

    @property
    def first_size(self) -> Decimal:
        return abs(self.first_net)

    @property
    def down(self) -> Decimal:
        return -self.net


@dataclass(frozen=True)
class FiveDaysRead:
    """What the five worst days were and what they share. Counts from the file, no cause."""

    rows: tuple[WorstDayRow, ...]
    first_lost_days: int
    lost_after_first: Decimal
    shared_book: str | None
    past_nine: int
    story: WorstDayStory | None


def five_days_read(trips: list[Trip]) -> FiveDaysRead | None:
    """The five worst days named, with what the record says they have in common.

    A day counts as "first trade lost, and more lost after it" only if the rest of the day also
    lost, so a day that recovered isn't described as carrying on losing.
    """
    worst = five_worst_days(trips).days
    if not worst:
        return None
    by_day = _by_day(trips)
    rows, lost_days, lost_after = [], 0, Decimal(0)
    for day in worst:
        ordered = sorted(by_day[day.trading_day], key=lambda t: t.entry_ts)
        rows.append(WorstDayRow(
            day.trading_day, tuple(dict.fromkeys(trade_book(t) for t in ordered)), day.trips, day.net,
        ))
        rest = sum((t.net for t in ordered[1:]), Decimal(0))
        if ordered[0].is_loss and rest < 0:
            lost_days += 1
            lost_after += -rest
    shared = set(rows[0].books).intersection(*(r.books for r in rows))
    worst_first = sorted(by_day[worst[0].trading_day], key=lambda t: t.entry_ts)
    story = None
    if len(worst_first) > 1 and worst[0].net < 0:
        story = WorstDayStory(
            worst[0].trading_day, worst_first[0].net, len(worst_first) - 1, worst[0].net,
        )
    return FiveDaysRead(
        rows=tuple(rows),
        first_lost_days=lost_days,
        lost_after_first=lost_after,
        shared_book=next((b for b in rows[0].books if b in shared), None),
        past_nine=sum(
            any(t.entry_ts.hour >= 21 for t in by_day[day.trading_day]) for day in worst
        ),
        story=story,
    )


@dataclass(frozen=True)
class DayBlock:
    """One of the five worst days, as the worst-days page reads it. Counts only, no cause."""

    trading_day: str
    books: tuple[str, ...]
    book: str | None  # the book with the most trades that day; None on a tie
    trades: int
    net: Decimal
    first_in: datetime
    last_out: datetime
    running: tuple[Decimal, ...]  # the result after each trade, first to last
    first_net: Decimal
    later: int
    later_lost: int
    longest_run: int  # the most losses in a row within the day


def _longest_run_in(ordered: list[Trip]) -> int:
    longest = current = 0
    for trip in ordered:
        current = current + 1 if trip.is_loss else 0
        longest = max(longest, current)
    return longest


def _main_book(ordered: list[Trip]) -> str | None:
    counts = Counter(trade_book(t) for t in ordered).most_common(2)
    if len(counts) == 2 and counts[0][1] == counts[1][1]:
        return None
    return counts[0][0]


def worst_day_blocks(trips: list[Trip]) -> tuple[DayBlock, ...]:
    """The five worst days, worst first, on the entry date as every other page counts them."""
    by_day = _by_day(trips)
    blocks = []
    for day in five_worst_days(trips).days:
        ordered = sorted(by_day[day.trading_day], key=lambda t: t.entry_ts)
        running, total = [], Decimal(0)
        for trip in ordered:
            total += trip.net
            running.append(total)
        blocks.append(DayBlock(
            trading_day=day.trading_day,
            books=tuple(dict.fromkeys(trade_book(t) for t in ordered)),
            book=_main_book(ordered),
            trades=len(ordered),
            net=day.net,
            first_in=ordered[0].entry_ts,
            last_out=max(t.exit_ts for t in ordered),
            running=tuple(running),
            first_net=ordered[0].net,
            later=len(ordered) - 1,
            later_lost=sum(t.is_loss for t in ordered[1:]),
            longest_run=_longest_run_in(ordered),
        ))
    return tuple(blocks)


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


def trades_past_number(trips: list[Trip]) -> TradesPastNumber:
    """How many trades lost more than his number. The one place this count is decided.

    A count, not a score: he chose the number. "More than" is strict, so a loss exactly
    equal to the number, in paise, is not counted. It reads rupees and never
    risk_unit_source, so a sold option with no risk figure counts the same as any other
    trade (Annex H section 6).
    """
    same_day = same_day_trips(trips)
    measured = [t for t in same_day if t.number_in_force is not None]
    past = [t for t in measured if _round(-t.net) > t.number_in_force]
    return TradesPastNumber(
        count=len(past),
        trip_ids=[t.trip_id for t in past],
        measured=len(measured),
        before_number=len(same_day) - len(measured),
        held_past_day=len(trips) - len(same_day),
        state=s.ResultState.COUNTED_FACT if measured else s.ResultState.INSUFFICIENT_SAMPLE,
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
