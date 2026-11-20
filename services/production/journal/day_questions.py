"""TICKET-915: up to three questions a day, written from that day's own trades.

The rule every question is held to (gate 2, and it goes in the PR): a question describes
the order and timing of the day and never leads. "Your first trade lost and you traded 8
more times." is a fact he can answer. "Why did you revenge trade?" is a verdict wearing a
question mark. So each question is a plain sentence about what his file shows - no cause,
no grade, no advice, no money, no tally of wins and losses, nothing about how the day
ended (Pawan, 17 Nov 2026) - and all we ask of it is "Did you know this?".
tests/unit/journal/test_day_questions_915.py checks every sentence this module can write
over more than a thousand days.

Ask, never score (founder, 12 Nov 2026): nothing pairs an answer with a result.

**More of the day's order and timing.** Six more kinds, each from times, sizes
and sides only: the pace after the open, going straight back in, size steps with their times,
switching sides, the last hour of the session, and the first trade after the open. They come
after 915's own in the order of preference, so a day 915 already asked three of asks the
same three. Where one needs a line to cross, the line is his own median from his record
(``context``, from ``journal/day_timing.medians``) or the instrument's session, never a number
of ours. A trade carries its timing only when ``day_timing.enrich`` added it; without it these
kinds stay silent.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from itertools import pairwise

MAX_QUESTIONS = 3
OPENING_MINUTES = 30
"""The first half hour of a session, the same first half hour the Your numbers page counts."""
SIDE_PAIRS = (("calls", "puts"), ("long", "short"))


@dataclass(frozen=True)
class DayQuestion:
    key: str
    text: str


def _times(n: int) -> str:
    return f"{n} more {'time' if n == 1 else 'times'}"


def _lots(value) -> str:
    return f"{value:g} {'lot' if value == 1 else 'lots'}"


def _span(minutes: float) -> str:
    """Whole minutes, and hours from an hour on: "2 minutes", "1 hour 15 minutes"."""
    m = int(minutes)
    if m < 60:
        return f"{m} {'minute' if m == 1 else 'minutes'}"
    h, r = divmod(m, 60)
    hours = f"{h} {'hour' if h == 1 else 'hours'}"
    return hours if not r else f"{hours} {r} {'minute' if r == 1 else 'minutes'}"


def _timed(trades: list[dict]) -> list[dict]:
    return [t for t in trades if t.get("entry") is not None]


def _since_open(t: dict) -> float | None:
    """Minutes from the session's open to this trade's entry; None in an MCX evening session."""
    if t.get("opens") is None or t.get("evening"):
        return None
    opened = datetime.combine(t["entry"].date(), t["opens"], t["entry"].tzinfo)
    return (t["entry"] - opened).total_seconds() / 60


def _one_trade(trades: list[dict]) -> DayQuestion:
    lots = trades[0]["lots"]
    at = f", at {_lots(lots)}" if lots is not None else ""
    return DayQuestion("one_trade", f"You took one trade this day{at}.")


def _first_then_more(trades: list[dict]) -> DayQuestion:
    first = trades[0]["net"]
    how = "lost" if first < 0 else "made money" if first > 0 else "was flat"
    return DayQuestion(
        "first_then_more",
        f"Your first trade {how} and you traded {_times(len(trades) - 1)}.")


def _loss_run(trades: list[dict]) -> DayQuestion | None:
    best = run = 0
    for trade in trades:
        run = run + 1 if trade["net"] < 0 else 0
        best = max(best, run)
    if best < 2:
        return None
    return DayQuestion("loss_run", f"You had {best} losing trades in a row.")


def _after_biggest_loss(trades: list[dict]) -> DayQuestion | None:
    losses = [(t["net"], i) for i, t in enumerate(trades) if t["net"] < 0]
    if not losses:
        return None
    at = min(losses)[1]
    if at in (0, len(trades) - 1):
        return None
    return DayQuestion(
        "after_biggest_loss",
        f"After the day's biggest loss you traded {_times(len(trades) - 1 - at)}.")


def _size_up(trades: list[dict]) -> DayQuestion | None:
    sized = [t for t in trades if t["lots"] is not None]
    if len(sized) < 2 or max(t["lots"] for t in sized) <= sized[0]["lots"]:
        return None
    first, top = sized[0], max(sized, key=lambda t: t["lots"])
    text = f"Your size went from {_lots(first['lots'])} to {_lots(top['lots'])}"
    if first.get("entry") is not None and top.get("entry") is not None:  # when
        text += f" between {first['entry']:%H:%M} and {top['entry']:%H:%M}"
    return DayQuestion("size_up", text + ".")


def _pace(trades: list[dict]) -> DayQuestion | None:
    """trades opened in the session's first half hour, when two or more."""
    early = [t for t in _timed(trades)
             if (s := _since_open(t)) is not None and 0 <= s < OPENING_MINUTES]
    if len(early) < 2:
        return None
    last = max(_since_open(t) for t in early)
    return DayQuestion("pace", f"You took {len(early)} trades in the {_span(max(last, 1))} "
                               f"after {early[0]['opens']:%H:%M}.")


def _back_in(trades: list[dict], context: dict) -> DayQuestion | None:
    """the day's shortest gap to the next trade, when below his own median gap."""
    median_gap = context.get("median_gap")
    timed = sorted(_timed(trades), key=lambda t: t["entry"])
    gaps = []
    for i, trade in enumerate(timed):
        nxt = next((t for t in timed[i + 1:] if t["entry"] > trade["exit"]), None)
        if nxt is not None:
            gaps.append((nxt["entry"] - trade["exit"]).total_seconds() / 60)
    if median_gap is None or not gaps or min(gaps) >= median_gap:
        return None
    gap = min(gaps)
    if gap < 1:
        return DayQuestion("back_in", "Your next trade came within a minute of you closing the one before.")
    return DayQuestion("back_in", f"Your next trade came {_span(gap)} after you closed the one before.")


def _switching(trades: list[dict]) -> DayQuestion | None:
    """how often consecutive trades changed side, calls and puts or long and short."""
    sides = [t["side"] for t in sorted(_timed(trades), key=lambda t: t["entry"]) if t.get("side")]
    best: tuple[int, tuple[str, str]] | None = None
    for pair in SIDE_PAIRS:
        run = [s for s in sides if s in pair]
        n = sum(1 for a, b in pairwise(run) if a != b)
        if n and (best is None or n > best[0]):
            best = (n, pair)
    if best is None:
        return None
    n, (a, b) = best
    return DayQuestion("switching", f"You switched between {a} and {b} {n} {'time' if n == 1 else 'times'} today.")


def _last_hour(trades: list[dict]) -> DayQuestion | None:
    """trades opened in the last hour of their own session."""
    late = []
    for t in _timed(trades):
        if t.get("closes") is None:
            continue
        closes = datetime.combine(t["entry"].date(), t["closes"], t["entry"].tzinfo)
        if closes - timedelta(hours=1) <= t["entry"] < closes:
            late.append(t)
    if not late:
        return None
    n = len(late)
    return DayQuestion("last_hour", f"You opened {n} {'trade' if n == 1 else 'trades'} in the last hour of the session.")


def _first_minutes(trades: list[dict], context: dict) -> DayQuestion | None:
    """how soon after the open the day's first trade came, when sooner than his
    own median; never for an MCX evening session, which is not the open."""
    median_first = context.get("median_first")
    timed = sorted(_timed(trades), key=lambda t: t["entry"])
    if median_first is None or not timed:
        return None
    since = _since_open(timed[0])
    if since is None or since < 0 or since >= median_first:
        return None
    if since < 1:
        return DayQuestion("first_minutes", "Your first trade came in the first minute after the open.")
    return DayQuestion("first_minutes", f"Your first trade came {_span(since)} after the open.")


def questions_for(trades: list[dict], context: dict | None = None) -> list[DayQuestion]:
    """At most three, in this order of preference. A one-trade day gets its own sentence."""
    if not trades:
        return []
    if len(trades) == 1:
        return [_one_trade(trades)]
    context = context or {}
    found = [_first_then_more(trades), _loss_run(trades), _after_biggest_loss(trades),
             _size_up(trades),
             # after 915's own, the timing questions: the day's pace, gaps, sides and session ends
             _pace(trades), _back_in(trades, context), _switching(trades), _last_hour(trades),
             _first_minutes(trades, context)]
    return [q for q in found if q is not None][:MAX_QUESTIONS]
