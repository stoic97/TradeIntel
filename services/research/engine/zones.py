"""The four zones - Research Specification v1.0 section 4.6, PRE-COMMIT, derived.

Applied to each trader's history in trade order:

    N         = reconstructed round trips
    isolation = clamp(round(0.25 N), 30, 200)       the hold-out, read once
    embargo   = max(round(0.05 N), one full trading day)
    training  = N - isolation - embargo             where discovery runs

The isolation count is exact. The embargo is a minimum: it is widened backward until
it begins on a day boundary and contains at least one whole trading day, because
trades within a day share a state (section 6.2) and a state begun in training must
not reach isolation across a too-thin embargo. Training absorbs the widening.

The isolation zone is the most recent trading. Nothing here reads outcomes.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

ISOLATION_FRACTION = 0.25
ISOLATION_MIN = 30
ISOLATION_MAX = 200
EMBARGO_FRACTION = 0.05


@dataclass(frozen=True)
class Zones:
    training: np.ndarray
    embargo: np.ndarray
    isolation: np.ndarray


def isolation_size(n: int) -> int:
    return int(min(max(round(ISOLATION_FRACTION * n), ISOLATION_MIN), ISOLATION_MAX))


def split(days: np.ndarray) -> Zones:
    """``days``: the trading-day label of each round trip, in trade order."""
    day = np.asarray(days).ravel()
    n = int(day.size)
    iso = isolation_size(n)
    iso_start = n - iso
    emb_start = iso_start - max(round(EMBARGO_FRACTION * n), 1)

    def whole_day_inside(start: int) -> bool:
        for d in np.unique(day[start:iso_start]):
            members = np.flatnonzero(day == d)
            if members.min() >= start and members.max() < iso_start:
                return True
        return False

    # Widen backward: to a day boundary, and until a whole day sits inside.
    while emb_start > 0 and (day[emb_start - 1] == day[emb_start] or not whole_day_inside(emb_start)):
        emb_start -= 1

    if emb_start < 1:
        raise ValueError(
            f"{n} round trips leave no training zone: isolation takes {iso} and the "
            f"embargo needs at least one whole trading day before it"
        )
    idx = np.arange(n)
    return Zones(training=idx[:emb_start], embargo=idx[emb_start:iso_start], isolation=idx[iso_start:])
