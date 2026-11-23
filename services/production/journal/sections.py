"""A Journal's content, as counted facts.

PRD 7.4 lists what a Journal contains. This builds it, and stores **facts, never
sentences**.

That distinction is the one load-bearing decision here. A Journal is immutable once
written (PRD 7.2): corrections are versions, not edits. If the prose were stored, a
template fix next month would silently rewrite what a trader was told last month --
the record would change without a version, which is the one thing immutability
exists to prevent. Storing counted facts means the wording can improve while the
assertion cannot.

Every figure is counted from his own trades and compared only to his own baseline.
Nothing here reaches for a population, an average or another trader: the PRD puts
"traders like you" at fifty per stratum, and v1 has none.

Money is stored as a string. A Decimal through JSON is a float through JSON, and a
float decides no trader-facing number (ctr_v1 6.5).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from services.production.journal.periods import Period
from services.production.mirror import metrics as mx
from services.production.mirror.metrics import Trip


def _net(trips: tuple[Trip, ...] | list[Trip]) -> Decimal:
    return sum((t.net for t in trips), Decimal(0))


# What a Journal stores that isn't about its own period: read against the whole history, or
# against answers given since. One new trade anywhere moves the first on every day, and neither
# is a change to this day, so neither decides whether a new version is written.
NOT_THIS_PERIOD = {
    "against_your_normal": {"your_normal_day", "lots_usually"},
    "after_two_straight_losses": {"days_it_happened", "your_trading_days"},
    "planned_sl": {"losing_trades_without_one", "said_before"},
}


def history_facts(history: list[Trip]) -> dict[str, dict[str, Any]]:
    """The facts a Journal states against his whole history, decided in one place.

    A Journal keeps its version when only these move (``NOT_THIS_PERIOD``), so what it stored
    can be older than his record. The page reads them live through ``with_history``, and so
    does every sentence beside them: one usual size and one count of days on one page.

    The days the behaviour happened are counted on same-day trades, the trades chapter 3 and
    the finding bar read (a position held past the day has not closed when the next trade
    opens), over the days he closed a same-day trade, the days chapter 3 counts (855).
    """
    day_counts = mx.day_counts(history)
    condition = mx.two_straight_losses(mx.same_day_trips(history))
    condition_ids = set(condition.condition_trip_ids)
    return {
        "against_your_normal": {
            "your_normal_day": str(day_counts.normal_day),
            "lots_usually": str(mx.average_lots(history).mean or "0"),
        },
        "after_two_straight_losses": {
            "days_it_happened": len({t.trading_day for t in history if t.trip_id in condition_ids}),
            "your_trading_days": len({t.trading_day for t in mx.same_day_trips(history)}),
        },
    }


def with_history(facts: dict[str, Any], history: list[Trip]) -> dict[str, Any]:
    """A stored Journal's facts with its whole-history facts read from his record now."""
    live = history_facts(history)
    out = dict(facts)
    for name, values in live.items():
        if name in out:
            out[name] = {**out[name], **values}
    return out


def own_facts(facts: dict[str, Any]) -> dict[str, Any]:
    """The stored facts about this period alone."""
    return {
        name: (
            {k: v for k, v in body.items() if k not in NOT_THIS_PERIOD[name]}
            if name in NOT_THIS_PERIOD else body
        )
        for name, body in facts.items()
    }

def _days_held(trip: Trip) -> int:
    """Calendar days from the date it opened to the date it closed."""
    return (trip.exit_ts.date() - date.fromisoformat(trip.trading_day)).days


def build(
    period: Period,
    *,
    history: list[Trip],
    fees_available: bool,
    planned_sl_said_before: bool = False,
    trips_with_a_stop: set[str] | None = None,
) -> dict[str, Any]:
    """The counted facts for one period, against the trader's whole history."""
    trips = list(period.trips)

    wins = sum(1 for t in trips if t.is_win)
    losses = sum(1 for t in trips if t.is_loss)
    scratches = sum(1 for t in trips if t.is_scratch)

    # Against his whole history: one helper, so the page reads it live (with_history).
    against = history_facts(history)

    # The behaviour, by the shared definition, today.
    today_condition = mx.two_straight_losses(trips)

    hours = sorted({t.entry_ts.hour for t in trips})

    facts: dict[str, Any] = {
        "period": {
            "unit": period.unit.value,
            "start": period.period_start,
            "end": period.period_end,
        },
        "trip_ids": [t.trip_id for t in trips],
        "fees_available": fees_available,
        "trades": {
            "count": len(trips),
            "net": str(_net(trips)),
            "wins": wins,
            "losses": losses,
            "scratches": scratches,
            "first_hour": hours[0] if hours else None,
            "last_hour": hours[-1] if hours else None,
            # Exits count too: entry hours alone called a month-long position a morning
            # trade (TICKET-800).
            "all_before_noon": bool(trips) and all(
                t.closed_same_day and t.entry_ts.hour < 12 and t.exit_ts.hour < 12
                for t in trips
            ),
        },
        "against_your_normal": {
            "trades_today": len(trips),
            "lots_today": str(mx.average_lots(trips).mean or "0"),
            **against["against_your_normal"],
        },
        "after_two_straight_losses": {
            "today": today_condition.condition,
            "today_net": str(today_condition.condition_net),
            **against["after_two_straight_losses"],
        },
        "planned_sl": {
            # Only losses with NO stop recorded. Counting every loss would tell a
            # trader who diligently recorded each one that he recorded none -- and
            # the line is meant to show him a gap, not invent one.
            "losing_trades_without_one": sum(
                1 for t in trips
                if t.is_loss and t.trip_id not in (trips_with_a_stop or set())
            ),
            "said_before": planned_sl_said_before,
        },
    }
    # Only on a day with a held trade. A Journal gets a new version when its facts differ,
    # so a key on every day would rewrite every Journal at the next upload.
    held = [t for t in trips if not t.closed_same_day]
    if held:
        longest = max(held, key=_days_held)
        facts["held"] = {
            "count": len(held),
            "opened": longest.trading_day,
            "closed": longest.exit_ts.date().isoformat(),
            "days": _days_held(longest),
        }
    return facts
