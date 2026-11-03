"""What a Journal covers: the unit, and which periods are complete.

PRD 7.2. The unit is the trading day unless the upload's median eligible day is
thinner than two trips, in which case it is per 10 trips; the trader's own setting
overrides either. A period is written only when it is complete, because a Journal
for half a day would be rewritten by the next upload and a trader who read the first
one was told something that is no longer true.

Completeness is the subtle part. A day is complete when the upload contains a later
trading day, or the export date is after it. The last day of an upload with no
export date is NOT complete: more of it may exist in the broker's records.
"""

from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from services.production.journal import periods as pd
from services.production.mirror.metrics import Trip
from services.shared.schemas import scope_v1 as s

FIXTURE = Path("tests/fixtures/mirror_contract/main.json")


def load() -> list[Trip]:
    return [
        Trip(trip_id=r["trip_id"], trading_day=r["trading_day"],
             entry_ts=datetime.fromisoformat(r["entry_ts"]),
             exit_ts=datetime.fromisoformat(r["exit_ts"]),
             holding_seconds=r["holding_seconds"], net=Decimal(r["net"]),
             lots=r["lots"],
             risk_unit_source=s.RiskUnitSourceV1(r["risk_unit_source"]),
             symbol=r["symbol"])
        for r in json.loads(FIXTURE.read_text())
    ]


def thin(days: int, trips_per_day: int) -> list[Trip]:
    """A history with a fixed number of trips on each day."""
    out = []
    for d in range(days):
        for i in range(trips_per_day):
            day = f"2026-09-{d + 1:02d}"
            entry = datetime.fromisoformat(f"{day}T09:{i * 5:02d}:00+05:30")
            out.append(Trip(trip_id=f"d{d}t{i}", trading_day=day, entry_ts=entry,
                            exit_ts=entry, holding_seconds=60, net=Decimal(-100),
                            lots=1,
                            risk_unit_source=s.RiskUnitSourceV1.UNAVAILABLE,
                            symbol="WIDGETOIL"))
    return out


def test_a_dense_history_journals_by_day():
    assert pd.default_unit(load()).unit is s.JournalUnit.DAY


def test_a_thin_history_journals_per_ten_trips():
    assert pd.default_unit(thin(days=20, trips_per_day=1)).unit is s.JournalUnit.PER_N_TRIPS


def test_exactly_two_trips_a_day_is_dense_enough():
    """The threshold is >= 2, not > 2. A boundary silently wrong either way would
    change which product a whole archetype sees."""
    assert pd.default_unit(thin(days=10, trips_per_day=2)).unit is s.JournalUnit.DAY


def test_the_traders_own_setting_overrides_the_rule():
    trips = thin(days=20, trips_per_day=1)
    chosen = pd.resolve_unit(trips, preference=s.JournalUnit.DAY, preference_n=None)
    assert chosen.unit is s.JournalUnit.DAY
    assert chosen.from_preference is True


def test_a_week_preference_is_honoured():
    chosen = pd.resolve_unit(load(), preference=s.JournalUnit.WEEK, preference_n=None)
    assert chosen.unit is s.JournalUnit.WEEK


def test_days_are_complete_when_a_later_day_exists():
    periods = pd.periods_for(load(), unit=s.JournalUnit.DAY, export_date=None)
    complete = [p for p in periods if p.complete]
    assert len(complete) == 7, "eight days, the last incomplete without an export date"
    assert periods[-1].complete is False


def test_an_export_date_completes_the_last_day():
    periods = pd.periods_for(load(), unit=s.JournalUnit.DAY,
                             export_date="2026-09-11")
    assert all(p.complete for p in periods)
    assert len(periods) == 8


def test_an_export_date_on_the_last_day_does_not_complete_it():
    """The export ran during that day; more of it may exist."""
    periods = pd.periods_for(load(), unit=s.JournalUnit.DAY,
                             export_date="2026-09-10")
    assert periods[-1].complete is False


def test_a_period_carries_the_trips_it_covers():
    periods = pd.periods_for(load(), unit=s.JournalUnit.DAY, export_date=None)
    first = periods[0]
    assert first.period_start == "2026-09-01"
    assert first.period_end == "2026-09-01"
    assert [t.trip_id for t in first.trips] == ["t01", "t02", "t03"]


def test_weeks_run_monday_to_sunday():
    periods = pd.periods_for(load(), unit=s.JournalUnit.WEEK,
                             export_date="2026-09-20")
    assert periods[0].period_start == "2026-08-31", "the Monday of that ISO week"
    assert periods[0].period_end == "2026-09-06"
    assert len(periods) == 2, "01-04 Sep in one week, 07-10 Sep in the next"


def test_trip_groups_are_runs_of_n_in_entry_order():
    periods = pd.periods_for(load(), unit=s.JournalUnit.PER_N_TRIPS,
                             export_date=None, n=10)
    assert len(periods) == 4
    assert all(len(p.trips) == 10 for p in periods)
    assert periods[0].trips[0].trip_id == "t01"


def test_a_trailing_group_of_fewer_than_n_is_incomplete():
    periods = pd.periods_for(load()[:25], unit=s.JournalUnit.PER_N_TRIPS,
                             export_date=None, n=10)
    assert len(periods) == 3
    assert periods[-1].complete is False
    assert len(periods[-1].trips) == 5
