"""Which checks this history can support, and which it cannot (PRD 5.6).

> *"From your 180 trades we can run 11 of 17 checks. Six need more history -- the
> ones about repeated same-day behaviour need roughly 300 trades before the
> numbers mean anything."*

Shown before the Mirror, so a trader knows what he is about to read and what he is
not. The minimums come from the pre-registered framework (``prereg.reader``), never
from a number restated here.

**What this module is careful about is the difference between three answers**, and
the whole design is that difference:

*We counted the thing the test needs.* B2's condition is a function the Mirror and
the research library share, so its population and condition are exactly countable
here. So are the tests whose minimum is a plain total -- 200 trips, 40 trading
days -- because the total is the thing.

*We counted something that rules it out.* Most tests have a condition this product
does not implement; the engine does. But a test needing 30 condition and 60
comparison trips cannot possibly run on 50 trips, whatever its condition is. That
is a floor, not a count, and it is reported as one: below it the answer is certain,
above it the honest answer is that nothing here rules the test out.

*We could not count anything useful.* A minimum written per bucket, per regime or
per cell needs strata this product does not build. Saying "not counted" is the
accurate answer, and it is not the same as saying the check is unavailable.

Nothing here decides a test will run. ``NOT_YET_TESTED`` is section 8's state for
"we can run it; we have not", and the absence of a finding is never evidence of
good trading.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from services.production.mirror.metrics import Trip
from services.shared.conditions.b2_condition import Obs, population_and_condition
from services.shared.prereg import reader
from services.shared.prereg.reader import Framework, LibraryTest, Unit
from services.shared.schemas import scope_v1 as s


class Basis(str, Enum):
    """How much the figure beside a test is worth."""

    OWN_COUNT = "own_count"
    """The test's own quantity, counted on this history."""

    POPULATION_FLOOR = "population_floor"
    """A total the test cannot run below, whatever its condition turns out to be."""

    NOT_COUNTED = "not_counted"
    """Nothing here counts this one; the figure is absent rather than guessed."""


@dataclass(frozen=True)
class Verdict:
    test: LibraryTest
    state: s.ResultState
    basis: Basis
    have: int | None
    need: int | None
    unit: Unit
    reason: str

    @property
    def not_ruled_out(self) -> bool:
        """Nothing counted here stops this check running.

        Deliberately not called ``can_run``. For a test whose own condition the
        engine counts, this means the history clears a floor, not that the check
        will produce anything -- and the difference is exactly what section 8's
        NOT_YET_TESTED is for.
        """
        return self.state is s.ResultState.NOT_YET_TESTED


def _unavailable(test: LibraryTest) -> str | None:
    """Why this test cannot run on any history we can read today.

    Each reason is a deferral that already exists, named so the answer on the page
    can be traced to a ticket rather than to someone's memory.
    """
    if test.needs == "tick":
        return ("it needs tick-by-tick prices, and the price history we hold is "
                "one-minute bars (TD-004)")
    if test.requires_class == "conditional_on_stop_orders":
        return ("it needs the stop that was working when the trade was opened, and "
                "no broker export we read carries one (TD-003)")
    if test.n_min.unit is Unit.PER_REGIME or "regime" in test.extras:
        return ("it needs the market-regime labels, which have not reached this "
                "side as data (TD-011)")
    if "events" in test.extras:
        return ("it needs a calendar of the releases it looks at, which has not "
                "reached this side as data (TD-014)")
    return None


def _counted(test: LibraryTest, trips: list[Trip]) -> tuple[int | None, Basis]:
    """What this history has, in the unit the test's minimum is written in."""
    unit = test.n_min.unit

    if unit is Unit.TRIPS:
        return len(trips), (Basis.OWN_COUNT if test.n_min.comparison is None
                            else Basis.POPULATION_FLOOR)
    if unit is Unit.DAYS:
        days = len({t.trading_day for t in trips})
        return days, (Basis.OWN_COUNT if test.n_min.comparison is None
                      else Basis.POPULATION_FLOOR)
    if unit is Unit.WINNERS:
        return sum(1 for t in trips if t.is_win), Basis.OWN_COUNT
    if unit is Unit.LOSERS:
        return sum(1 for t in trips if t.is_loss), Basis.OWN_COUNT
    return None, Basis.NOT_COUNTED


def _b2_counts(trips: list[Trip]) -> tuple[int, int]:
    """B2's population and condition on this history, from the shared function."""
    days = {day: n for n, day in enumerate(sorted({t.trading_day for t in trips}))}
    obs = [
        Obs(day=days[t.trading_day],
            entry_at=t.entry_ts.timestamp(),
            exit_at=t.exit_ts.timestamp(),
            r=float(t.net))
        for t in trips
    ]
    in_pop, condition = population_and_condition(obs)
    return int(in_pop.sum()), int(condition.sum())


def _need(test: LibraryTest) -> int | None:
    n_min = test.n_min
    if n_min.condition is None:
        return None
    if n_min.comparison is None:
        return n_min.condition
    return n_min.condition + n_min.comparison


def assess_one(test: LibraryTest, trips: list[Trip]) -> Verdict:
    unavailable = _unavailable(test)
    if unavailable is not None:
        return Verdict(test, s.ResultState.REQUIRED_DATA_MISSING, Basis.NOT_COUNTED,
                       None, _need(test), test.n_min.unit, unavailable)

    need = _need(test)
    if need is None:
        return Verdict(test, s.ResultState.NOT_YET_TESTED, Basis.NOT_COUNTED,
                       None, None, test.n_min.unit,
                       "this one has no minimum we can read")

    if test.id == "B2":
        population, condition = _b2_counts(trips)
        comparison = population - condition
        enough = (condition >= test.n_min.condition
                  and comparison >= (test.n_min.comparison or 0))
        state = (s.ResultState.NOT_YET_TESTED if enough
                 else s.ResultState.INSUFFICIENT_SAMPLE)
        return Verdict(
            test, state, Basis.OWN_COUNT, condition, test.n_min.condition,
            Unit.TRIPS,
            f"{condition} trades meet the condition and {comparison} do not; "
            f"it needs {test.n_min.condition} and {test.n_min.comparison}",
        )

    have, basis = _counted(test, trips)
    if basis is Basis.NOT_COUNTED:
        # Even a minimum written per bucket or per cell has a floor in trades: a
        # test wanting 30 in each bucket cannot run on 20 altogether. Skipping
        # this was how an empty history came back with two checks that nothing
        # ruled out.
        if len(trips) < need:
            return Verdict(test, s.ResultState.INSUFFICIENT_SAMPLE, basis,
                           len(trips), need, Unit.TRIPS,
                           f"{len(trips)} trades, and its minimum of "
                           f"{test.n_min.raw} needs at least {need} of them")
        return Verdict(test, s.ResultState.NOT_YET_TESTED, basis, None, need,
                       test.n_min.unit,
                       f"its minimum is written {test.n_min.raw}, and this page "
                       "does not build those groups")

    if have is not None and have < need:
        return Verdict(test, s.ResultState.INSUFFICIENT_SAMPLE, basis, have, need,
                       test.n_min.unit,
                       f"{have} of the {need} {test.n_min.unit.value} it needs")

    reason = (f"{have} {test.n_min.unit.value}, and it needs {need}"
              if basis is Basis.OWN_COUNT else
              f"{have} {test.n_min.unit.value} is above the {need} it cannot run "
              "below; whether enough of them meet its condition is the engine's "
              "count, not this page's")
    return Verdict(test, s.ResultState.NOT_YET_TESTED, basis, have, need,
                   test.n_min.unit, reason)


@dataclass(frozen=True)
class Eligibility:
    framework: Framework
    verdicts: tuple[Verdict, ...]

    @property
    def enough(self) -> tuple[Verdict, ...]:
        """Checks whose history clears a minimum we actually counted.

        Separated from ``undetermined`` after reading the page: with both in one
        group, a 40-trade history announced that two checks had "enough to work
        with", and the two it named were the only two the page cannot count. A
        headline assembled out of what we do not know is worse than no headline.
        """
        return tuple(v for v in self.verdicts
                     if v.not_ruled_out and v.basis is not Basis.NOT_COUNTED)

    @property
    def undetermined(self) -> tuple[Verdict, ...]:
        """Checks this page cannot judge, which is not the same as can or cannot."""
        return tuple(v for v in self.verdicts
                     if v.not_ruled_out and v.basis is Basis.NOT_COUNTED)

    @property
    def short(self) -> tuple[Verdict, ...]:
        """Counted, and the history is not big enough yet. His to change."""
        return tuple(v for v in self.verdicts
                     if v.state is s.ResultState.INSUFFICIENT_SAMPLE)

    @property
    def waiting(self) -> tuple[Verdict, ...]:
        """Waiting on something that is not his trades. Ours to change."""
        return tuple(v for v in self.verdicts
                     if v.state is s.ResultState.REQUIRED_DATA_MISSING)

    @property
    def runnable(self) -> tuple[Verdict, ...]:
        return tuple(v for v in self.verdicts if v.not_ruled_out)

    @property
    def blocked(self) -> tuple[Verdict, ...]:
        return tuple(v for v in self.verdicts if not v.not_ruled_out)

    @property
    def total(self) -> int:
        return len(self.verdicts)


def assess(trips: list[Trip], framework: Framework | None = None) -> Eligibility:
    """Every check in the library, against this history."""
    framework = framework or reader.load()
    return Eligibility(
        framework=framework,
        verdicts=tuple(assess_one(t, trips) for t in framework.tests),
    )
