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
"""

from __future__ import annotations

from dataclasses import dataclass

MAX_QUESTIONS = 3


@dataclass(frozen=True)
class DayQuestion:
    key: str
    text: str


def _times(n: int) -> str:
    return f"{n} more {'time' if n == 1 else 'times'}"


def _lots(value) -> str:
    return f"{value:g} {'lot' if value == 1 else 'lots'}"


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
    sized = [t["lots"] for t in trades if t["lots"] is not None]
    if len(sized) < 2 or max(sized) <= sized[0]:
        return None
    return DayQuestion("size_up", f"Your size went from {_lots(sized[0])} to {_lots(max(sized))}.")


def questions_for(trades: list[dict]) -> list[DayQuestion]:
    """At most three, in this order of preference. A one-trade day gets its own sentence."""
    if not trades:
        return []
    if len(trades) == 1:
        return [_one_trade(trades)]
    found = [_first_then_more(trades), _loss_run(trades), _after_biggest_loss(trades),
             _size_up(trades)]
    return [q for q in found if q is not None][:MAX_QUESTIONS]