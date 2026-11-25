"""Your process: one sheet of counted rows, the way an evaluation desk reads a trader.

Risk, Sizing, Under drawdown, Day control and Consistency. **Every line is a count of what he
did, opening the trades behind it**: no grade, no advice, no would-have money, no adjective.

**The rows are a registry.** ``ROWS`` is a list of row builders, each taking a ``Reading`` (his
trades, and the capital he told us if he did) and returning a ``Row`` of ``Line``s. The page
draws whatever the list holds, in its order, and the trade list opens any line's trades through
one quiet filter (``line``) by asking the same builders (``members``). A later row (Execution,
Market) is one more builder appended here; neither the page nor the trade list changes.

Decided here, and each threshold is his own:

* **Worst trades:** the worst tenth of his losing trades, at least 3. Against them, the fewest
  of his best wins whose sum reaches their loss.
* **Average winner** is ``mx.break_even``'s. **Days** are the day he closed, as the calendar
  counts them. **Usual size** is his median lots (the lower middle, so it is a size he traded);
  **biggest** is his top tenth by lots, from the smallest size among them up.
* **Lots** are counted on option trades, as ``mx.average_lots`` counts them; every other trade
  is left out of the Sizing row and counted.
* **The biggest drop** is ``mx.running_result``'s, by the day he closed, inside from its high's
  day to its low's day.
* **His usual losing day** is the median result of his losing days, a trading day's running
  result read in order of exit time.
* **A rate needs 30 trades** in its group (``mx.CLOCK_MINIMUM_TRADES``); a thinner group shows
  its count and "too few for a rate".
* **What moved:** each line's figure beside the earlier reading's, only when both meet the line's
  minimum. No arrow, no colour, no "better" or "worse".
"""
from __future__ import annotations

import dataclasses
import statistics
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal
from math import ceil

from markupsafe import Markup, escape

from services.production.api import formatting
from services.production.api import scope_map as S
from services.production.api.figures import Figure
from services.production.mirror import metrics as mx

RATE_AT = mx.CLOCK_MINIMUM_TRADES
WORST_AT_LEAST = 3
BEST_DAYS = 3

LABELS: dict[str, str] = {
    "worst": "Your worst trades",
    "best-wins": "Your best wins, as many as reach them",
    "losses": "Your losing trades",
    "small-losses": "Losses smaller than your average winner",
    "best-days": "Your best days",
    "usual": "At your usual size",
    "biggest": "At your biggest sizes",
    "left-out": "Not in option lots",
    "drop": "Inside your biggest drop",
    "rest": "Outside your biggest drop",
    "dipped": "Days down more than your usual losing day",
    "fell": "Days that finished lower than that",
    "months": "Months that made money",
}
"""What the trade list's filter says a line's trades are. A later row adds its own keys here."""


@dataclass(frozen=True)
class Reading:
    trips: list
    capital: Decimal | None = None


@dataclass(frozen=True)
class Measure:
    """The one figure a line is compared on, earlier against today."""

    value: Decimal | int
    noun: str
    how: str
    signed: bool = False


@dataclass(frozen=True)
class Line:
    key: str
    parts: tuple            # words and written figures, in order
    sets: dict[str, frozenset[str]] = field(default_factory=dict)  # what each figure opens
    measure: Measure | None = None
    meets: bool = True      # this reading meets the line's minimum
    was: Markup | None = None

    @property
    def text(self) -> Markup:
        out = Markup("").join(escape(p) for p in self.parts)
        return out + Markup(" ") + self.was if self.was else out


@dataclass(frozen=True)
class Row:
    key: str
    name: str
    lines: tuple[Line, ...]
    empty: str | None = None      # why the row has nothing to show
    notes: tuple[str, ...] = ()


def href(key: str) -> str:
    """Every trade behind a line's figure, on the trade list."""
    return S.see_all_href("risk", line=key)


def _write(value, noun: str, how: str, opens: str | None = None, *, signed: bool = False) -> Markup:
    figure = Figure(value, noun, opens=href(opens) if opens else None)
    write = formatting._FIGURE_FILTERS[how]
    written = write(figure, signed=signed) if how == "rupees" else write(figure)
    return Markup('<span class="num">{}</span>').format(written)


def _count(n: int, noun: str, opens: str | None = None) -> Markup:
    return _write(n, noun, "count", opens if n else None)


def _rupees(value: Decimal, opens: str | None = None, *, signed: bool = False) -> Markup:
    return _write(value, "rupees", "rupees", opens, signed=signed)


def _rate(part: int, whole: int, opens: str | None = None) -> Markup:
    return _write(Decimal(part) * 100 / Decimal(whole), "percent", "out_of_a_hundred", opens)


def _amount(value: Decimal, noun: str) -> Markup:
    """A count when whole, else to one decimal (lots and trades a day are averages)."""
    if value == value.to_integral_value():
        return _write(int(value), noun, "count")
    return _write(value, noun, "lots")


def _ids(trips) -> frozenset[str]:
    return frozenset(t.trip_id for t in trips)


def _s(n, one: str, many: str) -> str:
    return one if n == 1 else many


def _closed(t) -> str:
    return t.exit_ts.date().isoformat()


def _made_money(group, key: str) -> tuple:
    """"you made money N of 100", or the group's count and "too few for a rate"."""
    if len(group) >= RATE_AT:
        return ("you made money ", _rate(sum(t.is_win for t in group), len(group), key))
    return (_count(len(group), "trades", key), f" {_s(len(group), 'trade', 'trades')}: too few for a rate")


# ---------- Risk ----------

def _worst(trips) -> Line:
    losses = sorted((t for t in trips if t.is_loss), key=lambda t: (t.net, t.trip_id))
    if len(losses) < WORST_AT_LEAST:
        return Line("worst", (_count(len(losses), "losing trades", "losses" if losses else None),
                              f" losing {_s(len(losses), 'trade', 'trades')}: too few for this line."),
                    {"losses": _ids(losses)}, meets=False)
    n = max(WORST_AT_LEAST, ceil(len(losses) / 10))
    worst = losses[:n]
    lost = -sum((t.net for t in worst), Decimal(0))
    wins = sorted((t for t in trips if t.is_win), key=lambda t: (-t.net, t.trip_id))
    reached, m = Decimal(0), 0
    for t in wins:
        if reached >= lost:
            break
        reached += t.net
        m += 1
    parts = ["Your ", _count(n, "trades", "worst"), " worst trades lost ", _rupees(lost, "worst")]
    sets = {"worst": _ids(worst)}
    if reached >= lost:
        parts += [", as much as your best ", _count(m, "wins", "best-wins"), f" {_s(m, 'win', 'wins')} made."]
        sets["best-wins"] = _ids(wins[:m])
    else:
        parts.append(", more than all your wins made.")
    return Line("worst", tuple(parts), sets, Measure(lost, "rupees", "rupees"))


def _small_losses(trips) -> Line:
    losses = [t for t in trips if t.is_loss]
    winner = mx.break_even(trips).average_winner
    if winner is None:
        return Line("small-losses", ("No winners to set your losses against.",), meets=False)
    if len(losses) < RATE_AT:
        return Line("small-losses", (_count(len(losses), "losses", "losses"),
                                     f" {_s(len(losses), 'loss', 'losses')} against your average winner: too few for a rate."),
                    {"losses": _ids(losses)}, meets=False)
    smaller = [t for t in losses if -t.net < winner]
    rate = Decimal(len(smaller)) * 100 / len(losses)
    return Line("small-losses", (_rate(len(smaller), len(losses), "small-losses"),
                                 " losses were smaller than your average winner."),
                {"small-losses": _ids(smaller)}, Measure(rate, "percent", "out_of_a_hundred"))


def _best_days(trips) -> Line:
    by_day: dict[str, Decimal] = defaultdict(Decimal)
    for t in trips:
        by_day[_closed(t)] += t.net
    if len(by_day) < BEST_DAYS:
        return Line("best-days", (_count(len(by_day), "days"),
                                  f" {_s(len(by_day), 'day', 'days')} with a trade closed: too few for this line."),
                    meets=False)
    best = sorted(by_day, key=lambda d: (-by_day[d], d))[:BEST_DAYS]
    made = sum((by_day[d] for d in best), Decimal(0))
    total = sum((t.net for t in trips), Decimal(0))
    sets = {"best-days": _ids(t for t in trips if _closed(t) in best)}
    parts = ["Your ", _count(BEST_DAYS, "days", "best-days"), " best days made ",
             _rupees(made, "best-days", signed=made < 0)]
    if total > 0:
        parts += [", ", _write(made * 100 / total, "percent", "out_of_a_hundred"), " of your total."]
    else:
        parts += ["; your record overall ", _rupees(total, signed=True), "."]
    return Line("best-days", tuple(parts), sets, Measure(made, "rupees", "rupees", signed=made < 0))


def risk(reading: Reading) -> Row:
    trips = reading.trips
    return Row("risk", "Risk", (_worst(trips), _small_losses(trips), _best_days(trips)))


# ---------- Sizing ----------

def _lots(n) -> str:
    return _s(n, "lot", "lots")


def sizing(reading: Reading) -> Row:
    opts = [t for t in reading.trips if t.is_option]
    others = [t for t in reading.trips if not t.is_option]
    if not opts:
        return Row("sizing", "Sizing", (), empty="No trades in lots.")
    usual = statistics.median_low(t.lots for t in opts)
    top = sorted((t.lots for t in opts), reverse=True)[ceil(len(opts) / 10) - 1]
    at_usual = [t for t in opts if t.lots == usual]
    sets = {"usual": _ids(at_usual)}
    parts: list = []
    if top > usual:
        biggest = [t for t in opts if t.lots >= top]
        sets["biggest"] = _ids(biggest)
        parts += ["At your biggest sizes, ", _count(top, "lots"), f" {_lots(top)} or more, ",
                  *_made_money(biggest, "biggest"), "; at your usual size, "]
    else:
        parts.append("At your usual size, ")
    parts += [_count(usual, "lots"), f" {_lots(usual)}, ", *_made_money(at_usual, "usual"), "."]
    measure = (Measure(Decimal(sum(t.is_win for t in at_usual)) * 100 / len(at_usual), "percent",
                       "out_of_a_hundred") if len(at_usual) >= RATE_AT else None)
    lines = [Line("sizes", tuple(parts), sets, measure, meets=measure is not None)]

    if len(opts) >= RATE_AT:
        rest = [t.lots for t in opts if t.lots != usual]
        share = ["", _rate(len(at_usual), len(opts), "usual"), " trades at your usual ",
                 _count(usual, "lots"), f" {_lots(usual)}"]
        if not rest:
            share.append("; every other trade too.")
        elif min(rest) == max(rest):
            share += ["; the rest at ", _count(min(rest), "lots"), f" {_lots(min(rest))}."]
        else:
            share += ["; the rest from ", _count(min(rest), "lots"), " to ", _count(max(rest), "lots"), " lots."]
        lines.append(Line("usual-share", tuple(share), {"usual": _ids(at_usual)},
                          Measure(Decimal(len(at_usual)) * 100 / len(opts), "percent", "out_of_a_hundred")))
    else:
        lines.append(Line("usual-share", (_count(len(opts), "trades"),
                                          f" {_s(len(opts), 'trade', 'trades')} in lots: too few for a rate."),
                          meets=False))
    if others:
        kinds = " or ".join(sorted({"futures" if t.lines and t.lines[0].segment == "FUT" else "shares"
                                    for t in others}, reverse=True))
        lines.append(Line("left-out", (_count(len(others), "trades", "left-out"),
                                       (f" {_s(len(others), 'trade', 'trades')} in {kinds} "
                                        f"{_s(len(others), 'is', 'are')} left out of this row.")),
                          {"left-out": _ids(others)}))
    if "size" in S.FACTS:
        lines.append(Line("size-after", (Markup('<a class="link" href="{}">Your size after a loss</a>')
                                         .format(S.fact_href("size")),)))
    return Row("sizing", "Sizing", tuple(lines))


# ---------- Under drawdown ----------

def _group(trips, key: str) -> tuple:
    days = len({_closed(t) for t in trips})
    per_day = Decimal(len(trips)) / days
    lots = mx.average_lots(trips).mean
    out = [_amount(per_day, "trades a day"), f" {_s(per_day, 'trade', 'trades')} a day, "]
    if lots is None:
        out.append("no trades in lots, ")
    else:
        out += [_amount(Decimal(lots), "lots on average"), f" {_s(lots, 'lot', 'lots')} on average, "]
    return (*out, *_made_money(trips, key))


def under_drawdown(reading: Reading) -> Row:
    trips = reading.trips
    drop = mx.running_result(trips).drop
    notes = () if reading.capital else ("No capital told.",)
    if not drop.value or drop.to_day is None:
        return Row("drawdown", "Under drawdown", (), empty="No drop: your result never fell from a high.",
                   notes=notes)
    start = drop.from_day or min(_closed(t) for t in trips)
    inside = [t for t in trips if start <= _closed(t) <= drop.to_day]
    rest = [t for t in trips if t not in inside]
    parts = ["In your biggest drop, ", formatting.day(start), " to ", formatting.day(drop.to_day), ": ",
             *_group(inside, "drop"), ". The rest of your record: "]
    parts += [*_group(rest, "rest"), "."] if rest else ["no trades."]
    per_day = Decimal(len(inside)) / len({_closed(t) for t in inside})
    lines = [Line("drop", tuple(parts), {"drop": _ids(inside), "rest": _ids(rest)},
                  Measure(per_day, "trades a day", "lots"))]
    if reading.capital:
        lines.append(Line("capital", ("Your biggest drop was ",
                                      _write(drop.value * 100 / reading.capital, "percent", "out_of_a_hundred", "drop"),
                                      " of the capital you told us."),
                          {"drop": _ids(inside)},
                          Measure(drop.value * 100 / reading.capital, "percent", "out_of_a_hundred")))
    return Row("drawdown", "Under drawdown", tuple(lines), notes=notes)


# ---------- Day control ----------

def day_control(reading: Reading) -> Row:
    by_day: dict[str, list] = defaultdict(list)
    for t in sorted(reading.trips, key=lambda t: (t.exit_ts, t.trip_id)):
        by_day[t.trading_day].append(t)
    low, final = {}, {}
    for day, day_trips in by_day.items():
        running, lowest = Decimal(0), Decimal(0)
        for t in day_trips:
            running += t.net
            lowest = min(lowest, running)
        low[day], final[day] = lowest, running
    losing = [v for v in final.values() if v < 0]
    if not losing:
        return Row("day-control", "Day control", (), empty="No losing days.")
    usual = statistics.median(losing)
    dipped = [d for d in by_day if low[d] < usual]
    fell = [d for d in dipped if final[d] < usual]
    sets = {"dipped": _ids(t for d in dipped for t in by_day[d]),
            "fell": _ids(t for d in fell for t in by_day[d])}
    parts = ("Your usual losing day: ", _rupees(usual, signed=True), ". On ",
             _count(len(dipped), "days", "dipped"), (f" {_s(len(dipped), 'day', 'days')} you were down more than "
              "that at some point; on "), _count(len(fell), "days", "fell"),
             " of them you finished lower than that.")
    return Row("day-control", "Day control", (Line("day-control", parts, sets,
                                                   Measure(usual, "rupees", "rupees", signed=True)),))


# ---------- Consistency ----------

def consistency(reading: Reading) -> Row:
    months = mx.running_result(reading.trips).candles["month"]
    made = {c.period for c in months if c.net > 0}
    lines = [Line("months", ("Made money in ", _count(len(made), "months", "months"), " of ",
                             _count(len(months), "months"), f" {_s(len(months), 'month', 'months')}."),
                  {"months": _ids(t for t in reading.trips if _closed(t)[:7] in made)},
                  Measure(len(made), "months", "count")),
             Line("halves", (Markup('<a class="link" href="{}">What your tradebook has been hiding</a>')
                             .format(S.fact_href("hidden")), ": each book's first half against its second."))]
    return Row("consistency", "Consistency", tuple(lines))


ROWS: list[Callable[[Reading], Row]] = [risk, sizing, under_drawdown, day_control, consistency]
"""The page's rows, in order. A later row is one more builder here."""

HOME_ROWS = ("risk", "sizing", "consistency")


def _was(today: Line, earlier: Line | None) -> Line:
    if earlier is None or not (today.meets and earlier.meets) or not (today.measure and earlier.measure):
        return today
    m, e = today.measure, earlier.measure
    was = Markup("{}, was {}.").format(_write(m.value, m.noun, m.how, signed=m.signed),
                                       _write(e.value, e.noun, e.how, signed=e.signed))
    return dataclasses.replace(today, was=was)


def build(reading: Reading, earlier: Reading | None = None) -> list[Row]:
    rows = [builder(reading) for builder in ROWS]
    if earlier is None or not earlier.trips:
        return rows
    before = {ln.key: ln for row in (builder(earlier) for builder in ROWS) for ln in row.lines}
    return [dataclasses.replace(row, lines=tuple(_was(ln, before.get(ln.key)) for ln in row.lines))
            for row in rows]


def members(trips, key: str) -> frozenset[str] | None:
    """The trades behind one figure, asked of the same builders the page drew it from."""
    reading = Reading(list(trips))
    for builder in ROWS:
        for ln in builder(reading).lines:
            if key in ln.sets:
                return ln.sets[key]
    return None


def home_preview(trips) -> list[Row]:
    """Home's three rows, each with its first line, over his whole record (Home has no filter)."""
    rows = [row for row in build(Reading(list(trips))) if row.key in HOME_ROWS]
    return [dataclasses.replace(row, lines=row.lines[:1]) for row in rows]
