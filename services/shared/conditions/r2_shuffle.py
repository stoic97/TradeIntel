"""R2's shuffle test, run with B2's on one shuffle and corrected together (TICKET-996).

A page may say "you trade bigger after a loss" only if this passes on the trader's own file. The
bar is the one ``b2_shuffle`` documents (TICKET-909), and R2's place in it is the framework's own
core-list row: ``R2 post_loss_size_change``, null N-B, at least 30 in each group.

* **N-B, the groups worked out again on every draw.** Each day's outcomes move to random trades
  of that day; each trade keeps its size and its times. Which earlier trade is "last" doesn't
  move, but whether it lost does, so the groups are recomputed from the shuffled outcomes on
  every draw (DECISIONS, 12 Nov). Shuffling only the labels would test something easier.
* **One shuffle, every check that runs.** B2 and R2 are measured on the same draws, in the same
  order, and the step-down min-p corrects them together over the whole fixed family; a check
  that can't run stays in it at p = 1. While R2 can't run for a file, B2's draws and its answer
  are exactly what ``b2_shuffle.shuffle_test`` gives, and a test holds that.
* **One direction:** the mean lots after a loss above the mean after a win. A gap the other way
  keeps the claim closed, however strong.
* **And the same way in both halves** of his own trading days, in date order.

Plain numpy, no research import, so production and research may both read it.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np

from services.shared.conditions import b2_shuffle, multiplicity, r2_condition
from services.shared.conditions.b2_condition import Obs
from services.shared.conditions.b2_shuffle import (
    FINDING,
    NOTHING,
    WORTH_WATCHING,
    ShuffleResult,
)

CHECK = "R12"  # its own registered row (TICKET-1063), not R2; pending its signature (PR #263)
MIN_GROUP = 30
DRAWS = b2_shuffle.DRAWS
SEED = b2_shuffle.SEED  # the same draws as B2's, so the two are corrected on one shuffle
ALPHA = b2_shuffle.ALPHA


def _gap(r: np.ndarray, lots: np.ndarray, sized: np.ndarray,
         prior: np.ndarray) -> tuple[float, int, int]:
    """Mean lots after a loss less mean lots after a win, on the sized trades, and the counts."""
    after_loss, after_win = r2_condition.groups(r, prior)
    loss, win = after_loss & sized, after_win & sized
    n_loss, n_win = int(loss.sum()), int(win.sum())
    if not n_loss or not n_win:
        return 0.0, n_loss, n_win
    return float(lots[loss].mean() - lots[win].mean()), n_loss, n_win


def halves(obs: Sequence[Obs], lots: np.ndarray, sized: np.ndarray) -> tuple[float | None, float | None]:
    """The gap in each half of his own trading days, in date order; None for a half that has
    no trade after a loss or none after a win."""
    days = sorted({o.day for o in obs})
    cut = (len(days) + 1) // 2
    out: list[float | None] = []
    for part in (set(days[:cut]), set(days[cut:])):
        keep = [i for i, o in enumerate(obs) if o.day in part]
        if not keep:
            out.append(None)
            continue
        sub = [obs[i] for i in keep]
        r = np.array([o.r for o in sub], dtype=float)
        gap, n_loss, n_win = _gap(r, lots[keep], sized[keep], r2_condition.last_resolved(sub))
        out.append(gap if n_loss and n_win else None)
    return out[0], out[1]


def null_draws(obs: Sequence[Obs], lots: np.ndarray, sized: np.ndarray,
               draws: int = DRAWS) -> tuple[np.ndarray, np.ndarray]:
    """R2's null on its own: each draw's gap, and how many sized trades came after a loss on it."""
    r = np.array([o.r for o in obs], dtype=float)
    day = np.array([o.day for o in obs])
    prior = r2_condition.last_resolved(obs)
    rng = np.random.default_rng(SEED)
    null, counts = np.empty(draws), np.empty(draws, dtype=np.int64)
    for b in range(draws):
        moved = b2_shuffle.shuffle_within_days(r, day, rng)
        null[b], counts[b], _ = _gap(moved, lots, sized, prior)
    return null, counts


def shuffle_family(obs: Sequence[Obs], lots: Sequence[float], sized: Sequence[bool],
                   draws: int = DRAWS,
                   checks: tuple[str, ...] | None = None) -> dict[str, ShuffleResult]:
    """B2 and R2 on this file, on one shuffle, corrected together. ``lots`` and ``sized`` run
    beside ``obs``: a trip's size, and whether its size is in lots (options and futures)."""
    checks = checks or multiplicity.family()
    fam = len(checks)
    if not obs:
        empty = ShuffleResult(0, 0, None, None, family_size=fam)
        return {b2_shuffle.CHECK: empty, CHECK: empty}
    lots = np.asarray(lots, dtype=float)
    sized = np.asarray(sized, dtype=bool)
    r = np.array([o.r for o in obs], dtype=float)
    day = np.array([o.day for o in obs])

    pop, first, second = b2_shuffle.last_two_resolved(obs)
    b2_observed, n_cond, n_comp = b2_shuffle._difference(r, pop, first, second)
    b2_runs = n_cond >= b2_shuffle.MIN_CONDITION and n_comp >= b2_shuffle.MIN_COMPARISON

    prior = r2_condition.last_resolved(obs)
    r2_observed, n_loss, n_win = _gap(r, lots, sized, prior)
    # R12 runs only once it is in the registered family (TICKET-1063, PR #263); until then
    # its groups are counted and nothing is tested.
    r2_runs = n_loss >= MIN_GROUP and n_win >= MIN_GROUP and CHECK in checks

    out = {
        b2_shuffle.CHECK: ShuffleResult(n_cond, n_comp, None, None, family_size=fam),
        CHECK: ShuffleResult(n_loss, n_win, None, None, family_size=fam),
    }
    if not (b2_runs or r2_runs):
        return out

    rng = np.random.default_rng(SEED)
    b2_null, r2_null = np.empty(draws), np.empty(draws)
    for b in range(draws):
        moved = b2_shuffle.shuffle_within_days(r, day, rng)
        if b2_runs:
            b2_null[b], _, _ = b2_shuffle._difference(moved, pop, first, second)
        if r2_runs:
            r2_null[b], _, _ = _gap(moved, lots, sized, prior)

    # Both read "one-sided, below": B2's gap is below zero when it fires; R2's is above, so
    # it is turned over.
    observed: dict[str, float | None] = {}
    null: dict[str, np.ndarray] = {}
    if b2_runs:
        observed[b2_shuffle.CHECK], null[b2_shuffle.CHECK] = b2_observed, b2_null
    if r2_runs:
        observed[CHECK], null[CHECK] = -r2_observed, -r2_null
    adjusted = multiplicity.step_down_min_p(observed, null, checks)

    if b2_runs:
        p = multiplicity.raw_p(b2_observed, b2_null)
        split = b2_shuffle.halves(obs)
        adj = adjusted[b2_shuffle.CHECK]
        if b2_observed < 0 and adj <= ALPHA and b2_shuffle._same_way(split):
            level = FINDING
        elif b2_observed < 0 and p <= ALPHA:
            level = WORTH_WATCHING
        else:
            level = NOTHING
        out[b2_shuffle.CHECK] = ShuffleResult(n_cond, n_comp, b2_observed, p, adj, split, level, fam)
    if r2_runs:
        p = multiplicity.raw_p(-r2_observed, -r2_null)
        split = halves(obs, lots, sized)
        adj = adjusted[CHECK]
        same_way = all(g is not None and g > 0 for g in split)
        if r2_observed > 0 and adj <= ALPHA and same_way:
            level = FINDING
        elif r2_observed > 0 and p <= ALPHA:
            level = WORTH_WATCHING
        else:
            level = NOTHING
        out[CHECK] = ShuffleResult(n_loss, n_win, r2_observed, p, adj, split, level, fam)
    return out

