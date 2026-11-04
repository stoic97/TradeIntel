"""Which trades of a day to ask about, and the one line about size (Journal, section 14).

Three questions on every trade makes a day of fifteen trades forty-five boxes, and nobody
starts that. So the page asks about the first trade and one other, and the rest stay
reachable behind a toggle: a trader who wants to answer them still can.

The other trade is the day's biggest loss. If that IS the first trade, it's the trade where
size went up, because asking about the same trade twice would waste the second place.

The size line stays on the day on purpose. Worst days are ranked by rupees, and a bigger size
makes any day bigger in rupees, so "your worst days were bigger" would be partly how the days
were picked. What happened inside one day has no such problem.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from services.production.api import formatting

ALL_ASKED_UP_TO = 2
"""A day this short asks about every trade: there is nothing to choose between."""

FIRST = "your first trade"
BIGGEST_LOSS = "the biggest loss of the day"
FIRST_AND_BIGGEST_LOSS = f"{FIRST}, and {BIGGEST_LOSS}"


@dataclass(frozen=True)
class Ask:
    index: int  # into the day's trades, in the order they were opened
    why: str | None  # None when every trade is asked, so no reason is needed


def _size_up(trades: list[dict]) -> int | None:
    """The first trade at the day's largest size, if that is above where the day began.

    Options only: lots is None on a share, whose quantity is not a size.
    """
    sized = [(i, t["lots"]) for i, t in enumerate(trades) if t["lots"] is not None]
    if len(sized) < 2:
        return None
    largest = max(lots for _, lots in sized)
    if largest <= sized[0][1]:
        return None
    return next(i for i, lots in sized if lots == largest)


def trades_to_ask(trades: list[dict]) -> list[Ask]:
    """The trades to ask about: at most two, in the order they were opened."""
    if len(trades) <= ALL_ASKED_UP_TO:
        return [Ask(i, None) for i in range(len(trades))]

    losses = [(t["net"], i) for i, t in enumerate(trades) if t["net"] < 0]
    biggest_loss = min(losses)[1] if losses else None
    if biggest_loss not in (None, 0):
        return [Ask(0, FIRST), Ask(biggest_loss, BIGGEST_LOSS)]

    opening = Ask(0, FIRST if biggest_loss is None else FIRST_AND_BIGGEST_LOSS)
    up = _size_up(trades)
    if up is None:
        return [opening]
    return [opening, Ask(up, f"the trade where you went to {trades[up]['lots']} lots")]


def _times(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


def _climbed_while_losing(climb: list[dict]) -> bool:
    """Size never fell on the way to the top, and every trade before the top lost.

    Without this, 1, 2, 1, 5, 7 lots reads "from 1 lot to 7 after 1 loss": each word true, and
    the sentence says one jump that never happened.
    """
    sizes = [t["lots"] for t in climb if t["lots"] is not None]
    return sizes == sorted(sizes) and all(t["net"] < 0 for t in climb[:-1])


def size_line(day: str, trades: list[dict], usual: Decimal | None) -> str | None:
    """Going bigger after losing, on this day, as a fact. None if that isn't what happened.

    Says nothing rather than something loose: a day with no line loses little, and a line that
    misremembers the day costs the trader's trust in every other figure.
    """
    up = _size_up(trades)
    if up is None or usual is None:
        return None
    began = next(t["lots"] for t in trades if t["lots"] is not None)
    rose_at = next(i for i, t in enumerate(trades) if t["lots"] is not None and t["lots"] > began)
    if not _climbed_while_losing(trades[rose_at:up + 1]):
        return None

    losses = 0
    for trade in reversed(trades[:rose_at]):
        if trade["net"] >= 0:
            break
        losses += 1
    if not losses:
        return None
    return (f"On {formatting.day(day)} you went from {_times(began, 'lot', 'lots')} to "
            f"{trades[up]['lots']} after {_times(losses, 'loss', 'losses')}. "
            f"Your usual is about {formatting.lots(usual)}.")
