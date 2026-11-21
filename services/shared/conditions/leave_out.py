"""Random sets of the same size: the band a figure is set against (TICKET-919).

The founder's ruling of 16 Nov 2026 for the hiding page: a figure is set against what random
sets of the same number of the same book's trades come to (the research spec's same-size
random null, section 5.4, N-C). The middle 95% of those sums is the band, and a figure on
either end is inside it. The draws and the seed are b2_shuffle's own, so one file always gets
one answer and no new constant enters the code.

``inside`` is read from the band and the figure, never passed in, so the chance line on a page
can only come from a comparison that was run (services/production/api/chance.py). It is a
count of draws beside the figure it checks: not a finding, and it promotes nothing.
Plain numpy: production may not import research (methodology Rule 5).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from functools import lru_cache

import numpy as np

from services.shared.conditions import b2_shuffle

DRAWS = b2_shuffle.DRAWS
SEED = b2_shuffle.SEED
BAND = (2.5, 97.5)  # percentiles of the random sets' sums: the middle 95%
_EDGE = 1e-9  # a figure on the band's end is inside it


@dataclass(frozen=True)
class ChanceBand:
    """A figure, and what random sets of its size from the same trades came to."""

    figure: float
    band: tuple[float, float]
    size: int
    draws: int = DRAWS
    seed: int = SEED

    @property
    def inside(self) -> bool:
        """The figure is what random sets of its size come to, nineteen times in twenty."""
        low, high = self.band
        return bool(low - _EDGE <= self.figure <= high + _EDGE)


def band_of(pool: Sequence[float], figure: float, size: int, draws: int = DRAWS,
            seed: int = SEED) -> ChanceBand:
    """The middle 95% of what ``size`` of the pool's values, drawn at random without
    replacement, add up to, with the figure set against it. The pool comes in a fixed order
    (the book's trades in entry order), so one file always draws the same sets."""
    if not 0 <= size <= len(pool):
        raise ValueError(f"a set of {size} cannot be drawn from {len(pool)} trades")
    return _band(tuple(float(v) for v in pool), float(figure), size, draws, seed)


@lru_cache(maxsize=256)
def _band(pool: tuple[float, ...], figure: float, size: int, draws: int,
          seed: int) -> ChanceBand:
    """Cached: every page of one report reads the same record, so it draws the same sets."""
    if size == 0:
        return ChanceBand(figure, (0.0, 0.0), 0, draws, seed)
    values = np.asarray(pool, dtype=float)
    rng = np.random.default_rng(seed)
    chunk = max(1, draws // 10)  # draws per batch, to keep the shuffled table small
    sums = np.empty(draws)
    done = 0
    while done < draws:
        n = min(chunk, draws - done)
        sets = rng.permuted(np.tile(values, (n, 1)), axis=1)[:, :size]
        sums[done:done + n] = sets.sum(axis=1)
        done += n
    low, high = np.percentile(sums, BAND)
    return ChanceBand(figure, (float(low), float(high)), size, draws, seed)
