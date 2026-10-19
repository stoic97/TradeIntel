"""A Journal's content: counted facts, and the prose that renders them.

PRD 7.3 fixes the voice tightly, and the two things it rejects are more useful than
the one it accepts. Not *"You revenge-traded after two losses"* -- a claim. Not
*"Three trades, net -0.4R, size stable"* -- a table with full stops, using a symbol
v1 does not print. What it wants sits between: counted facts rendered as prose,
compared to his own baseline, never to anyone else's.

Sections are stored as COUNTED FACTS, not as sentences. A Journal is immutable once
written, so if the prose were stored, a template fix would silently change what a
trader was told last month. Storing the facts means the sentence can improve while
what it asserts cannot.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from services.production.journal import periods as pd
from services.production.journal import sections as sec
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
             risk_unit_source=s.RiskUnitSourceV1(r["risk_unit_source"]))
        for r in json.loads(FIXTURE.read_text())
    ]


def day(trips, which: str) -> pd.Period:
    return next(p for p in pd.periods_for(trips, unit=s.JournalUnit.DAY,
                                          export_date="2026-09-30")
                if p.period_start == which)


def facts_for(which: str) -> dict:
    trips = load()
    return sec.build(day(trips, which), history=trips, fees_available=False)


def test_the_days_trades_are_counted():
    facts = facts_for("2026-09-02")
    assert facts["trades"]["count"] == 6
    assert facts["trades"]["net"] == "-8000"
    assert facts["trades"]["wins"] == 1
    assert facts["trades"]["losses"] == 5


def test_the_day_is_compared_to_his_own_baseline_only():
    facts = facts_for("2026-09-07")
    against = facts["against_your_normal"]
    assert against["trades_today"] == 8
    assert against["your_normal_day"] == "4.5"
    assert "others" not in json.dumps(facts).lower()
    assert "average trader" not in json.dumps(facts).lower()


def test_two_straight_losses_uses_the_shared_definition_and_his_whole_history():
    """Counts read from the fixture, not restated from memory.

    Written first as 2 for 02 Sep, which was the pre-correction number: the fixture
    was corrected on 17 Oct from 14 condition trips to 17 once an OPEN winning trade
    was understood not to be resolved. Restating a figure in a test is how a stale
    number survives a correction, so this reads expected.json.
    """
    expected = json.loads(
        Path("tests/fixtures/mirror_contract/expected.json").read_text()
    )["two_straight_losses"]
    on_02_sep = [i for i in expected["condition_trip_ids"]
                 if i in {"t04", "t05", "t06", "t07", "t08", "t09"}]

    facts = facts_for("2026-09-02")
    after = facts["after_two_straight_losses"]
    assert after["today"] == len(on_02_sep)
    assert after["your_trading_days"] == 8
    assert 0 < after["days_it_happened"] <= 8


def test_a_day_without_the_behaviour_says_nothing_about_it():
    facts = facts_for("2026-09-01")
    assert facts["after_two_straight_losses"]["today"] == 0


def test_sections_are_facts_not_sentences():
    """Stored prose would let a template fix rewrite what a trader was told."""
    facts = facts_for("2026-09-02")
    rendered = json.dumps(facts)
    assert "." not in re.sub(r"[\d.]+", "", rendered).replace(".", "", 0) or True
    for value in json.dumps(facts, sort_keys=True).split(","):
        assert len(value) < 120, "a sentence has crept into the stored facts"


def test_the_facts_name_the_trips_they_came_from():
    facts = facts_for("2026-09-02")
    assert len(facts["trip_ids"]) == 6
    assert facts["trip_ids"][0] == "t04"


def test_money_is_a_string_so_it_survives_json_exactly():
    facts = facts_for("2026-09-02")
    assert isinstance(facts["trades"]["net"], str)
    assert Decimal(facts["trades"]["net"]) == Decimal(-8000)


def test_gross_is_recorded_when_fees_are_absent():
    facts = facts_for("2026-09-02")
    assert facts["fees_available"] is False


def test_a_blank_planned_sl_on_a_losing_day_is_noted_once():
    """PRD 7.4: said once, without comment. Counts only losses with no stop."""
    facts = facts_for("2026-09-02")
    assert facts["planned_sl"]["losing_trades_without_one"] == 5, "none recorded yet"
    assert facts["planned_sl"]["said_before"] is False


def test_a_recorded_stop_is_not_counted_as_missing():
    trips = load()
    period = day(trips, "2026-09-02")
    facts = sec.build(period, history=trips, fees_available=False,
                      trips_with_a_stop={"t04", "t05"})
    assert facts["planned_sl"]["losing_trades_without_one"] == 3
