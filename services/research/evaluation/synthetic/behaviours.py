"""The planted behaviours: one condition flag per core test (Research Spec v1.0 §12.2).

Each factory returns a ``Behaviour`` - a condition on what the trader knew at entry,
plus one of the three mechanisms in ``trader``. Conditions read only resolved trips
(``EntryState``), so a planted behaviour can never use information the engine is
forbidden from using (§4.3). Definitions follow Annex A of the spec.

Built so far (cycle 4): one behaviour per mechanism - B2 (DRIFT), R2 (SIZE),
E5 (EXIT). The remaining fourteen follow the same pattern.
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
