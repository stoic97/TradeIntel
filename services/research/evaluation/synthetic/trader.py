"""The base trader: a plain, flaw-free policy that the seventeen behaviours modify.

Research Spec v1.0 §12.2: "a base policy with a tunable edge". This is that policy,
and with no behaviours passed in, nothing else. Each trade:

* **Entry.** Each day the number of entry attempts is Poisson(``trades_per_day``);
  attempt minutes are uniform over the day's bars, excluding the last
  ``no_entry_last_min`` minutes. An attempt while a position is open is skipped -
  one position at a time. Entry is at the open of the chosen bar.
* **Direction.** With probability ``skill`` the trader takes the side the price
  actually moves over the next ``skill_horizon`` bars; otherwise a fair coin. The
  edge is therefore real - it comes from the price path, not from adding R to the
  outcome. ``skill=0`` is a zero-edge trader.
* **Risk.** Stop distance = ``stop_atr`` x ATR, where ATR is the mean high-low range
  of the ``atr_bars`` bars *before* the entry bar - point-in-time (§4.3). One R is
  that distance per unit. Target at ``target_r`` R.
* **Exit.** The first of: stop, target, or the close of the bar at the end of a
  log-normal holding time (median ``hold_median_min``), capped at the day's last
  bar. The base trader never carries overnight; S6 adds that later. If one bar
  touches both stop and target, the stop is assumed first (conservative) and the
  trip is flagged ``ambiguous``. A stop gapped through between bars fills at that
  bar's open, so a loss can exceed 1R.

Randomness comes from five independent streams spawned from the seed (entries,
direction, holding, behaviour, re-entry). Every stream is drawn once per entry attempt,
taken or skipped, so a history run with and without a behaviour stays paired
draw-for-draw - that pairing is what the twin run (§12.2) needs to measure the
true avoidable cost. With no behaviours the trader is exactly the base policy.

**The three hooks (§12.2).** The seventeen planted behaviours reduce to three
mechanisms, each switched on by a condition flag evaluated on what the trader
knew at entry (resolved trips only):

* ``DRIFT`` - with probability ``strength`` the trader takes the side *against*
  the realised move (chasing, revenge entries). The worse result comes from the
  price path, exactly as skill's better result does.
* ``SIZE`` - position size is multiplied by ``strength``. R per unit is untouched;
  money at risk is not.
* ``EXIT`` - winners are cut early: at ``strength`` x the planned holding time, a
  trip that is in profit is closed. Losers run to the planned exit.

Cycle 5b adds six mechanisms for behaviours that change the shape of a trade, not
just its side or size:

* ``SIZE_SPREAD`` - size is log-normal with sigma ``strength`` and mean 1 (R1).
* ``STOP_WIDEN`` - when price reaches the stop, the stop is moved ``strength`` R
  further away (R7 with a stop order on record; E4' without one). 1R stays the
  original stop distance, so a loss can run past -1R. ``stop_moved`` records it.
* ``GIVEBACK`` - no target; once the trade has been ``GIVEBACK_ARM_R`` in profit,
  it exits when price gives back ``strength`` of its best excursion (E2).
* ``LATENCY`` - after a losing trip, the trader re-enters ``strength`` minutes
  after the exit (B1). Forced re-entries draw from their own stream, so the
  regular attempts stay paired with the twin.
* ``ADD`` - when the trade is ``ADD_AT_R`` against him, he adds ``strength`` x the
  position at that price, same stop (R11). ``adds`` records each extra fill; R is
  the trip's money result over the original risk.
* ``CARRY`` - the position is held overnight (where the series allows carry): no
  exit is acted on until the next session opens, the planned exit is ``hold``
  minutes after that open, and with probability ``strength`` the position is on
  the wrong side of the overnight gap (S6). A gap through the stop fills at the
  open, so carried losses can be several R.

``prevalence`` is the probability the behaviour acts when its condition holds.
Each trip records ``flags`` (conditions true at entry) and ``applied`` (behaviours
that acted) - the ground truth that recall is scored against.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import astuple, dataclass, field, replace
from enum import Enum

import numpy as np

from services.research.evaluation.synthetic.market import Bars

LONG, SHORT = 1, -1
GIVEBACK_ARM_R = 0.5  # the trade must have been this far in profit before giveback can fire
ADD_AT_R = 0.5  # adverse excursion at which R11 adds to the position


@dataclass(frozen=True)
class TraderConfig:
    trades_per_day: float = 3.0
    skill: float = 0.0
    skill_horizon: int = 30
    stop_atr: float = 3.0
    atr_bars: int = 30
    min_atr: float = 1.0  # one MCX crude tick (Rs 1): flat, untraded stretches still have a 1R
    target_r: float = 2.0
    hold_median_min: float = 45.0
    hold_sigma: float = 0.8
    no_entry_last_min: int = 30
    # Trade frequency that drifts over the history (adversarial nulls, §12.2):
    # lambda_d = trades_per_day x exp(rate_wave x sin(2 pi (d - start) / period + phase)).
    # rate_wave = 0 is a constant rate and leaves every draw unchanged.
    rate_wave: float = 0.0
    rate_period_days: float = 120.0
    rate_phase: float = 0.0


class Mechanism(str, Enum):
    DRIFT = "DRIFT"
    SIZE = "SIZE"
    EXIT = "EXIT"
    SIZE_SPREAD = "SIZE_SPREAD"
    STOP_WIDEN = "STOP_WIDEN"
    GIVEBACK = "GIVEBACK"
    LATENCY = "LATENCY"
    ADD = "ADD"
    CARRY = "CARRY"


_PROBABILITY = (Mechanism.DRIFT, Mechanism.CARRY)


@dataclass(frozen=True)
class Trip:
    entry_idx: int  # index into Bars
    exit_idx: int
    day: int  # trading day of entry
    direction: int  # LONG or SHORT
    entry_price: float
    exit_price: float
    stop_price: float  # the stop as first placed
    target_price: float  # NaN when the trip had no target (GIVEBACK)
    risk_per_unit: float  # 1R, in price points
    r_multiple: float
    exit_reason: str  # STOP | TARGET | GIVEBACK | TIME
    ambiguous: bool
    size: float = 1.0  # units at entry; P&L = r_multiple x risk_per_unit x size
    flags: tuple[str, ...] = ()  # behaviour conditions true at entry
    applied: tuple[str, ...] = ()  # behaviours that acted on this trip
    stop_moved: bool = False  # the stop was moved away from price before it filled
    adds: tuple[tuple[int, float, float], ...] = ()  # (bar, price, units) per extra fill
    carried: bool = False  # held across a session close


@dataclass(frozen=True)
class EntryState:
    """What the trader knows at the moment of an entry attempt - nothing later."""

    bar: int
    day: int
    history: tuple[Trip, ...]  # every resolved trip, oldest first
    today: tuple[Trip, ...]  # resolved trips of the current day, oldest first
    minute: int = 0  # minutes since midnight IST of the entry bar
    weekday: int = 0  # 0 = Monday
    atr: float = 0.0  # mean high-low of the atr_bars bars before entry
    vol_tercile: int = 1  # 0 low, 1 mid, 2 high: atr against the previous 5 days' bars
    n_planned: int = 0  # length of the history being generated
    regime: str | None = None  # market regime label at the entry bar, where supplied
    crosses_close: bool = False  # his planned hold runs past today's last bar
    can_carry: bool = False  # the series allows holding into the next day
    forced: bool = False  # this entry is a post-loss re-entry (LATENCY)


@dataclass(frozen=True)
class Behaviour:
    test_id: str
    mechanism: Mechanism
    condition: Callable[[EntryState], bool]
    strength: float
    prevalence: float = 1.0


@dataclass
class _Mods:
    against: bool = False
    size: float = 1.0
    early: float | None = None
    widen: float | None = None
    giveback: float | None = None
    add: float | None = None
    carry: bool = False
    acted: list[str] = field(default_factory=list)


def trips_hash(trips: list[Trip]) -> str:
    h = hashlib.sha256()
    for t in trips:
        h.update(repr(astuple(t)).encode())
    return h.hexdigest()


def _validate(cfg: TraderConfig, seed: int, n_trades: int) -> None:
    if seed < 0:
        raise ValueError("seed must be a non-negative integer")
    if n_trades < 1:
        raise ValueError("n_trades must be at least 1")
    if not 0.0 <= cfg.skill <= 1.0:
        raise ValueError("skill must be in [0, 1]")
    if cfg.trades_per_day <= 0 or cfg.stop_atr <= 0 or cfg.target_r <= 0:
        raise ValueError("trades_per_day, stop_atr and target_r must be positive")


def _day_bounds(bars: Bars) -> tuple[np.ndarray, np.ndarray]:
    """First and one-past-last bar index of each trading day."""
    starts = np.flatnonzero(np.diff(bars.day, prepend=-1))
    ends = np.append(starts[1:], len(bars.day))
    return starts, ends


VOL_LOOKBACK_DAYS = 5


def _vol_cutoffs(rng_hl: np.ndarray, starts: np.ndarray, ends: np.ndarray, n: int) -> np.ndarray:
    """Per day, the 33rd and 67th percentile of bar ATR over the previous 5 days.

    Point-in-time: day d's cutoffs use only bars of days d-5 .. d-1. Day 0 has no
    past, so its cutoffs are NaN and every entry on it is the middle tercile.
    """
    cs = np.concatenate([[0.0], np.cumsum(rng_hl)])
    atr = np.full(len(rng_hl), np.nan)
    atr[n:] = (cs[n:-1] - cs[: -n - 1]) / n
    cut = np.full((len(starts), 2), np.nan)
    for d in range(1, len(starts)):
        lo = starts[max(0, d - VOL_LOOKBACK_DAYS)]
        past = atr[lo : ends[d - 1]]
        past = past[~np.isnan(past)]
        if len(past):
            cut[d] = np.percentile(past, [100 / 3, 200 / 3])
    return cut


def volatility_cutoffs(bars: Bars, atr_bars: int = 30) -> np.ndarray:
    """The per-day tercile cutoffs ``simulate_trader`` uses, for reuse across histories."""
    starts, ends = _day_bounds(bars)
    return _vol_cutoffs(bars.high - bars.low, starts, ends, atr_bars)


def _tercile(atr: float, cut: np.ndarray) -> int:
    if np.isnan(cut[0]):
        return 1
    return int(atr > cut[0]) + int(atr > cut[1])


def _validate_behaviours(behaviours: tuple[Behaviour, ...]) -> None:
    for b in behaviours:
        if not 0.0 <= b.prevalence <= 1.0:
            raise ValueError(f"{b.test_id}: prevalence must be in [0, 1]")
        if b.mechanism in _PROBABILITY and not 0.0 <= b.strength <= 1.0:
            raise ValueError(f"{b.test_id}: {b.mechanism.value} strength is a probability")
        elif b.mechanism is Mechanism.GIVEBACK and not 0.0 < b.strength < 1.0:
            raise ValueError(f"{b.test_id}: GIVEBACK strength is a fraction in (0, 1)")
        elif b.mechanism is Mechanism.LATENCY and b.strength < 0:
            raise ValueError(f"{b.test_id}: LATENCY strength is minutes, not negative")
        elif b.mechanism not in (*_PROBABILITY, Mechanism.LATENCY) and b.strength <= 0:
            raise ValueError(f"{b.test_id}: {b.mechanism.value} strength must be positive")


def _mods(applied: list[tuple[Behaviour, float, float]]) -> _Mods:
    m = _Mods()
    for b, u, z in applied:
        mech = b.mechanism
        if mech is Mechanism.DRIFT:
            m.against = m.against or u < b.strength
        elif mech is Mechanism.SIZE:
            m.size *= b.strength
        elif mech is Mechanism.SIZE_SPREAD:
            m.size *= float(np.exp(b.strength * z - b.strength**2 / 2))
        elif mech is Mechanism.EXIT:
            m.early = b.strength
        elif mech is Mechanism.STOP_WIDEN:
            m.widen = b.strength
        elif mech is Mechanism.GIVEBACK:
            m.giveback = b.strength
        elif mech is Mechanism.ADD:
            m.add = b.strength
        elif mech is Mechanism.CARRY:
            m.carry = True
            m.against = m.against or u < b.strength
        m.acted.append(b.test_id)
    return m


def simulate_trader(
    bars: Bars,
    seed: int,
    n_trades: int,
    config: TraderConfig | None = None,
    start_day: int = 0,
    behaviours: tuple[Behaviour, ...] = (),
    weekdays: np.ndarray | None = None,
    regime: np.ndarray | None = None,
    carry_allowed: np.ndarray | None = None,
    vol_cutoffs: np.ndarray | None = None,
) -> list[Trip]:
    """Generate ``n_trades`` trips.

    ``weekdays`` (per trading day, 0 = Monday) comes from the calendar dates of a
    real series; synthetic bars default to Monday..Friday in turn. ``regime`` (per
    bar) is a market regime label, required only by behaviours that read it.
    ``carry_allowed`` (per day) is ``MarketHistory.carry_allowed`` for the real
    series; synthetic bars allow carry on every day but the last.
    ``vol_cutoffs`` is ``volatility_cutoffs(bars)``, passed in when many histories
    share one series so it is computed once.
    """
    cfg = config or TraderConfig()
    _validate(cfg, seed, n_trades)
    _validate_behaviours(behaviours)
    entries_rng, direction_rng, hold_rng, behaviour_rng, reentry_rng = (
        np.random.Generator(np.random.PCG64(s))
        for s in np.random.SeedSequence(seed).spawn(5)
    )
    starts, ends = _day_bounds(bars)
    n_days = len(starts)
    rng_hl = bars.high - bars.low
    if weekdays is None:
        weekdays = np.arange(n_days) % 5
    if carry_allowed is None:
        carry_allowed = np.arange(n_days) < n_days - 1
    if len(weekdays) != n_days or len(carry_allowed) != n_days:
        raise ValueError("weekdays and carry_allowed must have one entry per trading day")
    if regime is not None and len(regime) != len(bars.day):
        raise ValueError("regime must have one label per bar")
    if vol_cutoffs is not None:
        cutoffs = vol_cutoffs
    elif behaviours:
        cutoffs = _vol_cutoffs(rng_hl, starts, ends, cfg.atr_bars)
    else:
        cutoffs = np.empty((0, 2))
    latency = [b for b in behaviours if b.mechanism is Mechanism.LATENCY]
    nb = len(behaviours)

    trips: list[Trip] = []
    flat_from = 0
    for d in range(start_day, n_days):
        lo, hi = int(starts[d]), int(ends[d])
        last_entry = hi - cfg.no_entry_last_min
        if last_entry <= lo:
            continue
        rate = cfg.trades_per_day
        if cfg.rate_wave:
            angle = 2 * np.pi * (d - start_day) / cfg.rate_period_days + cfg.rate_phase
            rate *= float(np.exp(cfg.rate_wave * np.sin(angle)))
        k = int(entries_rng.poisson(rate))
        attempts = [int(x) for x in np.sort(entries_rng.integers(lo, last_entry, size=k))]
        p = 0
        forced: int | None = None
        today: list[Trip] = []
        while True:
            # Every attempt draws from its streams, taken or skipped, so streams stay paired.
            if forced is not None and (p == len(attempts) or forced <= attempts[p]):
                i, is_forced, forced = forced, True, None
                rng_a = rng_b = rng_c = rng_d = reentry_rng
            elif p < len(attempts):
                i, is_forced = attempts[p], False
                p += 1
                rng_a, rng_b, rng_c, rng_d = direction_rng, hold_rng, behaviour_rng, behaviour_rng
            else:
                break
            coin = rng_a.random(2)
            z = rng_b.standard_normal()
            acts = rng_c.random(2 * nb)
            zs = rng_d.standard_normal(nb)
            hold = int(np.ceil(cfg.hold_median_min * np.exp(cfg.hold_sigma * z)))
            if i < max(flat_from, lo) or i < cfg.atr_bars or i >= last_entry:
                continue

            state = EntryState(bar=i, day=d, history=tuple(trips), today=tuple(today))
            if behaviours:
                atr = float(rng_hl[i - cfg.atr_bars : i].mean())
                state = replace(
                    state,
                    minute=int(bars.minute[i]),
                    weekday=int(weekdays[d]),
                    atr=atr,
                    vol_tercile=_tercile(atr, cutoffs[d]),
                    n_planned=n_trades,
                    regime=None if regime is None else str(regime[i]),
                    crosses_close=i + hold > hi - 1,
                    can_carry=bool(carry_allowed[d]) and d + 1 < n_days,
                    forced=is_forced,
                )
            flags, applied = [], []
            for n, b in enumerate(behaviours):
                if b.condition(state):
                    flags.append(b.test_id)
                    if b.mechanism is Mechanism.LATENCY:
                        if is_forced:
                            applied.append((b, 0.0, 0.0))
                    elif acts[2 * n] < b.prevalence:
                        applied.append((b, acts[2 * n + 1], zs[n]))
            mods = _mods(applied)
            carry_from = int(starts[d + 1]) if mods.carry else None
            if carry_from is not None:  # held overnight: the exit plan starts next session
                last_bar = min(carry_from + hold, int(ends[d + 1]) - 1)
            else:
                last_bar = min(i + hold, hi - 1)
            trip = _one_trip(bars, rng_hl, cfg, i, hi, last_bar, carry_from, coin, hold, d, mods)
            trip = replace(trip, flags=tuple(flags), applied=tuple(mods.acted))
            trips.append(trip)
            today.append(trip)
            flat_from = trip.exit_idx + 1
            if len(trips) == n_trades:
                return trips
            if trip.r_multiple < 0:
                for b in latency:
                    if reentry_rng.random() < b.prevalence and forced is None:
                        forced = trip.exit_idx + 1 + int(b.strength)
    raise ValueError(
        f"history ran out after {len(trips)} of {n_trades} trades - use more days or a later start"
    )


def _first(hits: np.ndarray) -> int | None:
    return int(np.argmax(hits)) if hits.any() else None


def _one_trip(
    bars: Bars,
    rng_hl: np.ndarray,
    cfg: TraderConfig,
    i: int,
    session_end: int,
    last_bar: int,
    carry_from: int | None,
    coin: np.ndarray,
    hold: int,
    d: int,
    m: _Mods,
) -> Trip:
    entry = float(bars.open[i])
    future = bars.close[min(i + cfg.skill_horizon, session_end - 1)]
    with_move = LONG if future >= entry else SHORT
    if coin[0] < cfg.skill:
        direction = with_move
    else:
        direction = LONG if coin[1] < 0.5 else SHORT
    if carry_from is not None:  # what matters overnight is the gap to the next open
        with_move = LONG if bars.open[carry_from] >= entry else SHORT
    if m.against:
        direction = -with_move

    atr = max(float(rng_hl[i - cfg.atr_bars : i].mean()), cfg.min_atr)
    risk = cfg.stop_atr * atr
    stop = entry - direction * risk
    live_stop = stop if m.widen is None else entry - direction * risk * (1 + m.widen)
    target = entry + direction * cfg.target_r * risk

    last = last_bar
    w = slice(i, last + 1)
    hi_, lo_ = bars.high[w], bars.low[w]
    adverse = lo_ if direction == LONG else hi_
    favour = hi_ if direction == LONG else lo_
    if carry_from is not None:  # he holds through: no exit is acted on until the next open
        quiet = np.arange(i, last + 1) < carry_from
        adverse = np.where(quiet, entry, adverse)
        favour = np.where(quiet, entry, favour)

    j_stop = _first(direction * (adverse - live_stop) <= 0)
    j_tgt = None if m.giveback is not None else _first(direction * (favour - target) >= 0)
    j_gb = None
    gb_level = np.empty(0)
    if m.giveback is not None:
        mfe = np.maximum.accumulate(direction * (favour - entry))
        prev = np.concatenate([[0.0], mfe[:-1]])
        gb_level = entry + direction * (1 - m.giveback) * prev
        j_gb = _first((prev >= GIVEBACK_ARM_R * risk) & (direction * (adverse - gb_level) <= 0))

    if m.early is not None:
        e = min(i + int(np.ceil(hold * m.early)), last) - i
        first_hit = min(x for x in (j_stop, j_tgt, j_gb, last - i + 1) if x is not None)
        if e < first_hit and direction * (bars.close[i + e] - entry) > 0:
            j_stop = j_tgt = j_gb = None
            last = i + e

    candidates = [(j, rank, why) for j, rank, why in (
        (j_stop, 0, "STOP"), (j_gb, 1, "GIVEBACK"), (j_tgt, 2, "TARGET")
    ) if j is not None]
    ambiguous = False
    if candidates:
        jj, _, reason = min(candidates)
        ambiguous = reason == "STOP" and j_tgt == jj
        j = i + jj
        gap = float(bars.open[j])
        if reason == "STOP":
            exit_price = min(gap, live_stop) if direction == LONG else max(gap, live_stop)
        elif reason == "GIVEBACK":
            lvl = float(gb_level[jj])
            exit_price = min(gap, lvl) if direction == LONG else max(gap, lvl)
        else:  # a limit target gapped through fills at the better open
            exit_price = max(gap, target) if direction == LONG else min(gap, target)
    else:
        j, reason, exit_price = last, "TIME", float(bars.close[last])

    adds: tuple[tuple[int, float, float], ...] = ()
    if m.add is not None:
        add_level = entry - direction * ADD_AT_R * risk
        j_add = _first(direction * (adverse[: j - i + 1] - add_level) <= 0)
        if j_add is not None:
            a = i + j_add
            gap = float(bars.open[a])
            price = min(gap, add_level) if direction == LONG else max(gap, add_level)
            adds = ((a, price, m.add * m.size),)

    # R per unit of the original position, plus what the added units made or lost,
    # in the same unit. Written so a trip with no adds is bit-identical to the base.
    r = direction * (exit_price - entry) / risk
    r += sum(direction * (exit_price - price) * units for _, price, units in adds) / (
        risk * m.size
    )
    stop_hit_first = _first(direction * (adverse[: j - i + 1] - stop) <= 0) is not None
    return Trip(
        entry_idx=i,
        exit_idx=j,
        day=d,
        direction=direction,
        entry_price=entry,
        exit_price=exit_price,
        stop_price=stop,
        target_price=float("nan") if m.giveback is not None else target,
        risk_per_unit=risk,
        r_multiple=r,
        exit_reason=reason,
        ambiguous=ambiguous,
        size=m.size,
        stop_moved=m.widen is not None and stop_hit_first,
        adds=adds,
        carried=bool(bars.day[j] != bars.day[i]),
    )
