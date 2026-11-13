"""Kept or broken, trade by trade (TICKET-922). Counts and accounting only.

The pre-registered framework gives no verdict at trader level (``change:
trader_level_verdict: none``), so the "verdict" here is about keeping the rule, never
about what the rule did to his results: "kept on 27 of 30 trades", and before the stated
sample, "Not enough trades yet". Nothing here prices a broken trade or names a saving.

A trade is governed by the newest rule of its factor declared before the trade was
opened, and only on the days that rule applies to. A rule set later never reaches back.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from services.production.rules import chips

VERDICT_AT = 30
"""Trades before a rule's count says more than "not enough trades yet": the framework's
own minimum for a condition (``statistics.minimums.condition``), stated here at the start."""


@dataclass(frozen=True)
class Rule:
    id: int
    factor: str
    value: int
    declared_at: datetime
    applies_from: str
    applies_to: str | None
    text: str


@dataclass(frozen=True)
class Checked:
    trip_id: str
    trading_day: str
    entry_ts: datetime
    kept: bool

    @property
    def opened(self) -> str:
        """The time it opened, in its instrument's zone, as the trade lists write it."""
        return self.entry_ts.strftime("%H:%M")


@dataclass(frozen=True)
class Count:
    rule: Rule
    trades: tuple[Checked, ...]
    fees: Decimal | None   # charges on these trades, when his file carries them

    @property
    def kept(self) -> int:
        return sum(c.kept for c in self.trades)

    @property
    def broken(self) -> int:
        return len(self.trades) - self.kept

    @property
    def enough(self) -> bool:
        return len(self.trades) >= VERDICT_AT


def _applies(rule: Rule, day: str) -> bool:
    return rule.applies_from <= day and (rule.applies_to is None or day <= rule.applies_to)


def _kept(rule: Rule, trip, same_day_before: list) -> bool:
    """Whether opening this trade kept the rule, from what was known when it opened."""
    closed = [t for t in same_day_before if t.exit_ts <= trip.entry_ts]
    if rule.factor == "most_trades":
        return len(same_day_before) + 1 <= rule.value
    if rule.factor == "losses_in_a_row":
        run = 0
        for t in sorted(closed, key=lambda t: t.exit_ts, reverse=True):
            if not t.is_loss:
                break
            run += 1
        return run < rule.value
    if rule.factor == "day_down":
        return sum((t.net for t in closed), Decimal(0)) > -Decimal(rule.value * 1000)
    if rule.factor == "last_hour":
        return trip.entry_ts.hour < rule.value
    if rule.factor == "most_lots":
        return trip.lots <= rule.value
    raise KeyError(rule.factor)


def count(rules: list[Rule], trips: list, fees: dict[str, Decimal] | None = None) -> list[Count]:
    """Each rule, with every trade it governed marked kept or broken. Newest rule first."""
    by_day: dict[str, list] = defaultdict(list)
    for t in sorted(trips, key=lambda t: t.entry_ts):
        by_day[t.trading_day].append(t)
    governed: dict[int, list[Checked]] = defaultdict(list)
    for day, day_trips in by_day.items():
        for i, trip in enumerate(day_trips):
            for factor in chips.FACTORS:
                live = [r for r in rules if r.factor == factor and r.declared_at <= trip.entry_ts
                        and _applies(r, day)]
                if not live:
                    continue
                rule = max(live, key=lambda r: (r.declared_at, r.id))
                governed[rule.id].append(Checked(trip.trip_id, day, trip.entry_ts,
                                                 _kept(rule, trip, day_trips[:i])))
    out = []
    for rule in sorted(rules, key=lambda r: (r.declared_at, r.id), reverse=True):
        checked = tuple(governed.get(rule.id, ()))
        paid = None
        if fees is not None:
            paid = sum((fees.get(c.trip_id, Decimal(0)) for c in checked), Decimal(0))
        out.append(Count(rule, checked, paid))
    return out


def match_notes(notes: list, trips: list, book_of, within_minutes: int = 30) -> dict[int, str]:
    """Each note before a click, to the first trade in its book opened within the window
    after it. A trade takes one note at most."""
    taken: set[str] = set()
    matched: dict[int, str] = {}
    for note in sorted(notes, key=lambda n: n.entered_at):
        for trip in sorted(trips, key=lambda t: t.entry_ts):
            gap = (trip.entry_ts - note.entered_at).total_seconds()
            if trip.trip_id in taken or gap < 0 or gap > within_minutes * 60:
                continue
            if note.book != chips.OTHER_BOOK and book_of(trip) != note.book:
                continue
            matched[note.id] = trip.trip_id
            taken.add(trip.trip_id)
            break
    return matched
