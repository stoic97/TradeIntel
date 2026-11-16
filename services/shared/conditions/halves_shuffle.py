"""The control beside the plain-counts page's change in net per trade (TICKET-910).

The page sets a book's first half of its own trading days beside its second. Its one control,
ruled by the founder (13 Nov), is the one T-001 used himself: shuffle whole days between the two
halves and ask how often the change in net per trade comes out at least as far from zero, either
way. The number of draws and the fixed seed are b2_shuffle's own, so one file always gets one
answer, and p = (b + 1) / (N + 1) is never zero.

It is a count of shuffles, shown beside the count it checks. It is not a finding, it is not in
the family the finding bar corrects for (multiplicity), and it promotes nothing. Plain numpy:
production may not import research (methodology Rule 5).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

from services.shared.conditions import b2_shuffle

DRAWS = b2_shuffle.DRAWS
SEED = b2_shuffle.SEED
_CHUNK = DRAWS // 10  # draws per batch, to keep the shuffled table small


@dataclass(frozen=True)
class HalvesResult:
    change: float | None  # net per trade, second half less first
    p: float | None  # two-sided; None when there is no control to show
    draws: int = DRAWS
    seed: int = SEED


def first_half_size(n_days: int) -> int:
    """How many of a book's days, in date order, are its first half: an odd count puts the
    middle day in the second half."""
    return n_days // 2


def _per_trade_change(net: np.ndarray, trades: np.ndarray, first: np.ndarray) -> np.ndarray:
    """Net per trade of the days not in `first`, less that of the days in it, row by row."""
    a_net, a_trades = net[first].sum(axis=-1), trades[first].sum(axis=-1)
    return (net.sum() - a_net) / (trades.sum() - a_trades) - a_net / a_trades


def halves_test(day_net: Sequence[float], day_trades: Sequence[int], draws: int = DRAWS,
                seed: int = SEED) -> HalvesResult:
    """The change between the halves, and how often whole days shuffled between them move it at
    least as far from zero, either way. The days come in date order, one net and one count each."""
    net = np.asarray(day_net, dtype=float)
    trades = np.asarray(day_trades, dtype=float)
    k = first_half_size(len(net))
    if k == 0:
        return HalvesResult(None, None, draws, seed)
    observed = float(_per_trade_change(net, trades, np.arange(k)))
    rng = np.random.default_rng(seed)
    hits = done = 0
    while done < draws:
        size = min(_CHUNK, draws - done)
        order = rng.permuted(np.tile(np.arange(len(net)), (size, 1)), axis=1)[:, :k]
        moved = _per_trade_change(net, trades, order)
        hits += int(np.count_nonzero(np.abs(moved) >= abs(observed) - 1e-9))
        done += size
    return HalvesResult(observed, (hits + 1) / (draws + 1), draws, seed)