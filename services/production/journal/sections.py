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

from decimal import Decimal
from typing import Any

from services.production.journal.periods import Period
from services.production.mirror import metrics as mx
from services.production.mirror.metrics import Trip


def _net(trips: tuple[Trip, ...] | list[Trip]) -> Decimal:
    return sum((t.net for t in trips), Decimal(0))


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

    # The day against his own normal day, from the whole history he has uploaded.
    day_counts = mx.day_counts(history)

    # The behaviour, by the shared definition, today and across everything he has.
    today_condition = mx.two_straight_losses(trips)
    history_condition = mx.two_straight_losses(history)
    condition_ids = set(history_condition.condition_trip_ids)
    days_with_it = len({
        t.trading_day for t in history if t.trip_id in condition_ids
    })

    hours = sorted({t.entry_ts.hour for t in trips})

    return {
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
            "all_before_noon": bool(hours) and hours[-1] < 12,
        },
        "against_your_normal": {
            "trades_today": len(trips),
            "your_normal_day": str(day_counts.normal_day),
            "lots_today": str(mx.average_lots(trips).mean or "0"),
            "lots_usually": str(mx.average_lots(history).mean or "0"),
        },
        "after_two_straight_losses": {
            "today": today_condition.condition,
            "today_net": str(today_condition.condition_net),
            "days_it_happened": days_with_it,
            "your_trading_days": len(day_counts.counts),
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
