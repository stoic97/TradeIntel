"""The planted behaviours: one condition flag per core test (Research Spec v1.0 §12.2).

Each factory returns a ``Behaviour`` - a condition on what the trader knew at entry,
plus one of the three mechanisms in ``trader``. Conditions read only resolved trips
(``EntryState``), so a planted behaviour can never use information the engine is
forbidden from using (§4.3). Definitions follow Annex A of the spec.

Built so far: B2, R2, E5 (cycle 4, one per mechanism); B5, B12, S1, S5, S10, S11
and both halves of R8 (cycle 5a, on the existing hooks). R1, R7, R11, E2, E4' (as
E4p), B1 and S6 need new trade mechanics and come in cycle 5b.

Two are approximations of the engine's own inputs and say so:

* **S5** plants on whatever regime labels are passed to the trader. The engine
  reads the fund's regime definition, which crosses as data (ADR 002); until those
  labels are in ``data/market/``, S5 can only be planted on a stand-in labelling.
* **S10** uses the EIA weekly release, Wednesday 10:30 New York time, which is
  20:00 IST while the US is on daylight time and 21:00 IST otherwise. The factory
  takes the release minute; the grid passes the right one per date.
"""

from __future__ import annotations

from services.research.evaluation.synthetic.trader import Behaviour, EntryState, Mechanism


def _two_losses_today(s: EntryState) -> bool:
    """Annex A.1: the two most recent resolved trips before entry, same day, were losses."""
    return len(s.today) >= 2 and all(t.r_multiple < 0 for t in s.today[-2:])


def _prior_trip_lost(s: EntryState) -> bool:
    """Annex A.2, R2: the previous resolved trip was a loss."""
    return bool(s.history) and s.history[-1].r_multiple < 0


def _always(_: EntryState) -> bool:
    return True


def b2_post_loss_expectancy(strength: float, prevalence: float = 1.0) -> Behaviour:
    """After two losses today, the trader chases: adverse direction with p = strength."""
    return Behaviour("B2", Mechanism.DRIFT, _two_losses_today, strength, prevalence)


def r2_post_loss_size_up(multiplier: float, prevalence: float = 1.0) -> Behaviour:
    """After a loss, the next position is ``multiplier`` times the usual size."""
    return Behaviour("R2", Mechanism.SIZE, _prior_trip_lost, multiplier, prevalence)


def e5_holding_asymmetry(early_fraction: float, prevalence: float = 1.0) -> Behaviour:
    """Winners are closed at ``early_fraction`` of the planned hold; losers run."""
    return Behaviour("E5", Mechanism.EXIT, _always, early_fraction, prevalence)


# ---------------------------------------------------------------- cycle 5a

SESSIONS = {  # Research Spec v1.0 §9: MCX crude buckets, minutes since midnight IST
    "morning": (9 * 60, 12 * 60),
    "afternoon": (12 * 60, 17 * 60),
    "us_overlap": (17 * 60, 24 * 60),
}
EIA_WEEKDAY = 2  # Wednesday
EIA_DST_MINUTE = 20 * 60  # 10:30 New York on daylight time
EIA_WINDOW = (-45, 30)  # entry from 45 min before (a median hold) to 30 min after


def b5_sequence_decay(
    strength: float, after_trade: int = 2, prevalence: float = 1.0
) -> Behaviour:
    """Overtrading: from the (after_trade + 1)-th trade of the day, entries chase."""

    def cond(s: EntryState) -> bool:
        return len(s.today) >= after_trade

    return Behaviour("B5", Mechanism.DRIFT, cond, strength, prevalence)


def _bad_start(s: EntryState) -> bool:
    """Annex A.2, B12: the day's first two resolved trips were both losses."""
    return len(s.today) >= 2 and s.today[0].r_multiple < 0 and s.today[1].r_multiple < 0


def b12_bad_start_day(strength: float, prevalence: float = 1.0) -> Behaviour:
    """After a bad start, every remaining entry that day chases."""
    return Behaviour("B12", Mechanism.DRIFT, _bad_start, strength, prevalence)


def s1_session_expectancy(
    strength: float, session: str = "us_overlap", prevalence: float = 1.0
) -> Behaviour:
    """Entries in one crude session bucket chase."""
    if session not in SESSIONS:
        raise ValueError(f"session must be one of {sorted(SESSIONS)}")
    lo, hi = SESSIONS[session]

    def cond(s: EntryState) -> bool:
        return lo <= s.minute < hi

    return Behaviour("S1", Mechanism.DRIFT, cond, strength, prevalence)


def s5_regime_expectancy(strength: float, label: str, prevalence: float = 1.0) -> Behaviour:
    """Entries in one market regime chase. Needs ``regime`` passed to the trader."""

    def cond(s: EntryState) -> bool:
        if s.regime is None:
            raise ValueError("S5 needs regime labels: pass regime= to simulate_trader")
        return s.regime == label

    return Behaviour("S5", Mechanism.DRIFT, cond, strength, prevalence)


def s10_event_trading(
    strength: float, release_minute: int = EIA_DST_MINUTE, prevalence: float = 1.0
) -> Behaviour:
    """Entries around the Wednesday EIA release chase."""
    lo, hi = release_minute + EIA_WINDOW[0], release_minute + EIA_WINDOW[1]

    def cond(s: EntryState) -> bool:
        return s.weekday == EIA_WEEKDAY and lo <= s.minute <= hi

    return Behaviour("S10", Mechanism.DRIFT, cond, strength, prevalence)


def s11_edge_decay(strength: float, recent: int = 100, prevalence: float = 1.0) -> Behaviour:
    """The edge fades: the last ``recent`` trips of the history chase."""

    def cond(s: EntryState) -> bool:
        return len(s.history) >= s.n_planned - recent

    return Behaviour("S11", Mechanism.DRIFT, cond, strength, prevalence)


def _high_vol(s: EntryState) -> bool:
    return s.vol_tercile == 2


def r8_high_vol_size(multiplier: float, prevalence: float = 1.0) -> Behaviour:
    """R8, size half: in the high-volatility tercile, size is ``multiplier`` times usual."""
    return Behaviour("R8", Mechanism.SIZE, _high_vol, multiplier, prevalence)


def r8_high_vol_drift(strength: float, prevalence: float = 1.0) -> Behaviour:
    """R8, R half: in the high-volatility tercile, entries chase."""
    return Behaviour("R8", Mechanism.DRIFT, _high_vol, strength, prevalence)
