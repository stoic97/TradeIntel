"""The challenge: 10 or 20 exchange trading days, one to three rules he set.

Counts only, never a grade. It reads 922's check (``rules.adherence``) restricted to the
challenge's rules and days, so a day is kept or broken exactly as the rules page counts it.

Decided here:

* **It starts on the next exchange trading day after he taps,** and after the last day already
  in a file, so a rule is always dated before the trades it tests (922).
* **Trading days are the exchange's** (``services/shared/market/closures.py``). A day he doesn't
  trade is still a day of the challenge: no trades, nothing broken.
* **A day is broken if any of its rules was broken on any trade that day,** however many times;
  it counts once.
* **A day after his latest file's last trading day is "not in a file yet".**
* **Finished** when the files cover every day; **stopped** when he ends it early.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from services.production.api import formatting
from services.production.rules import adherence as A

LENGTHS = (10, 20)
MAX_RULES = 3

KEPT, BROKEN, NO_TRADES, NOT_YET = "kept", "broken", "no-trades", "not-yet"


def trading_days(after: date, n: int, closed: frozenset[date]) -> list[date]:
    """The n exchange trading days after ``after``: weekdays the exchange didn't shut."""
    out: list[date] = []
    day = after
    while len(out) < n:
        day += timedelta(days=1)
        if day.weekday() < 5 and day not in closed:
            out.append(day)
    return out


def start_day(today: date, last_file_day: date | None, closed: frozenset[date]) -> date:
    """The next trading day after today and after any day already in a file."""
    base = max(today, last_file_day) if last_file_day else today
    return trading_days(base, 1, closed)[0]


@dataclass(frozen=True)
class Day:
    day: date
    state: str


@dataclass(frozen=True)
class RuleProgress:
    rule: A.Rule
    days: int                       # days of the challenge in a file so far
    broken_days: list[date] = field(default_factory=list)
    broken_trades: list[str] = field(default_factory=list)

    @property
    def kept_days(self) -> int:
        return self.days - len(self.broken_days)


@dataclass(frozen=True)
class Progress:
    length: int
    days: list[Day]
    rules: list[RuleProgress]

    @property
    def so_far(self) -> int:
        return sum(d.state != NOT_YET for d in self.days)

    @property
    def broken(self) -> int:
        return sum(d.state == BROKEN for d in self.days)

    @property
    def finished(self) -> bool:
        return self.so_far == self.length

    @property
    def status(self) -> str:
        if not self.so_far:
            return "no day of it in a file yet"
        if not self.broken:
            return "kept on every day so far"
        return f"broken on {formatting.count(self.broken)} of {formatting.count(self.so_far)} days"

    @property
    def next_day(self) -> date | None:
        """The first day not in a file yet: the one waiting for his next upload."""
        return next((d.day for d in self.days if d.state == NOT_YET), None)


def progress(days: list[date], rules: list[A.Rule], trips: list, last_file_day: date | None) -> Progress:
    """Each day of the challenge, and each rule's kept and broken days, from his files."""
    in_file = [d for d in days if last_file_day is not None and d <= last_file_day]
    wanted = {d.isoformat() for d in in_file}
    mine = [t for t in trips if t.trading_day in wanted]
    traded = {t.trading_day for t in mine}
    per_rule = []
    broken_any: set[str] = set()
    for c in A.count(rules, mine):
        broken = [ch for ch in sorted(c.trades, key=lambda ch: ch.entry_ts) if not ch.kept]
        days_broken = sorted({date.fromisoformat(ch.trading_day) for ch in broken})
        broken_any |= {d.isoformat() for d in days_broken}
        per_rule.append(RuleProgress(c.rule, len(in_file), days_broken, [ch.trip_id for ch in broken]))
    order = {r.id: i for i, r in enumerate(rules)}
    per_rule.sort(key=lambda rp: order[rp.rule.id])
    out = []
    for d in days:
        iso = d.isoformat()
        if d not in in_file:
            state = NOT_YET
        elif iso in broken_any:
            state = BROKEN
        elif iso not in traded:
            state = NO_TRADES
        else:
            state = KEPT
        out.append(Day(d, state))
    return Progress(len(days), out, per_rule)


def card_line(p: Progress, *, stopped: bool) -> str:
    """The completion card: counts and the rules' own words, never a rupee result or a name."""
    rules = ", ".join(rp.rule.text for rp in p.rules)
    kept = p.so_far - p.broken
    if stopped:
        tail = (f"kept on {formatting.count(kept)} of {formatting.count(p.so_far)} days"
                if p.so_far else "no day of it in a file yet")
        return (f"Stopped on day {formatting.count(p.so_far)} of {formatting.count(p.length)} · "
                f"the rules you set: {rules} · {tail}")
    return (f"{formatting.count(p.length)} trading days · the rules you set: {rules} · "
            f"kept on {formatting.count(kept)} of {formatting.count(p.length)} days")
