"""Adapter selection, the format check, and the three outcomes (PRD 5.3).

Order matters. Selection is by exact header match: a near-miss is a different export,
not a bad row, so it is a rejection naming the file we need -- never a parse attempt
that produces a hundred rejected rows and an unreadable screen.

The precedence rule is definitions_v1.md section 4: if anything is excluded the
outcome is ACCEPTED_WITH_EXCLUSIONS; ACCEPTED_PARTIAL_FIELDS is the state only when
nothing is excluded and a field some metrics need is absent. A clean file is
ACCEPTED_WITH_EXCLUSIONS with a count of zero. There is no fourth state.
"""

from __future__ import annotations

from pathlib import Path

from services.production.ctr.intake import outcomes as oc
from services.shared.schemas import scope_v1 as s

DUPES = Path("data/fixtures/duplicates")
PNL_LIKE = "Symbol,Realised P&L,Unrealised P&L\nWIDGETOIL,1500.00,0.00\n"
NO_TIME = (
    "Date,Name,Buy/Sell,Order,Exchange,Segment,Quantity/Lot,Trade Price,Trade Value,Status\n"
    "16/10/2026,WIDGETOIL 19 NOV FUT,BUY,INTRADAY,MCX,COMM,1,5000.00,5000.00,Traded\n"
)


def test_a_matching_header_selects_the_adapter():
    chosen = oc.select_adapter((DUPES / "clean.csv").read_text())
    assert chosen is not None
    assert chosen.adapter_id == "dhan_tradebook_v1"


def test_an_unknown_header_selects_nothing_and_is_rejected():
    assert oc.select_adapter(PNL_LIKE) is None
    decision = oc.check_format(PNL_LIKE)
    assert decision.outcome is s.ImportOutcome.REJECTED
    assert "time of day" in decision.missing or "prices" in decision.missing


def test_a_file_without_time_of_day_is_rejected():
    decision = oc.check_format(NO_TIME)
    assert decision.outcome is s.ImportOutcome.REJECTED
    assert decision.missing == "time of day"


def test_a_good_file_passes_the_format_check():
    decision = oc.check_format((DUPES / "clean.csv").read_text())
    assert decision.outcome is not s.ImportOutcome.REJECTED
    assert decision.adapter_id == "dhan_tradebook_v1"


def test_exclusions_beat_partial_fields():
    outcome = oc.decide_outcome(excluded_count=2, missing_fields=["fees"])
    assert outcome is s.ImportOutcome.ACCEPTED_WITH_EXCLUSIONS


def test_partial_fields_only_when_nothing_is_excluded():
    outcome = oc.decide_outcome(excluded_count=0, missing_fields=["fees"])
    assert outcome is s.ImportOutcome.ACCEPTED_PARTIAL_FIELDS


def test_a_clean_file_is_accepted_with_zero_exclusions():
    outcome = oc.decide_outcome(excluded_count=0, missing_fields=[])
    assert outcome is s.ImportOutcome.ACCEPTED_WITH_EXCLUSIONS


def test_a_file_whose_every_row_is_rejected_cannot_proceed():
    """definitions_v1.md section 4: rows but zero parsable fills is a rejection."""
    outcome = oc.decide_outcome(excluded_count=4, missing_fields=[], parsed_count=0)
    assert outcome is s.ImportOutcome.REJECTED


def test_there_are_exactly_three_outcomes_reachable():
    reachable = {
        oc.decide_outcome(excluded_count=0, missing_fields=[]),
        oc.decide_outcome(excluded_count=1, missing_fields=[]),
        oc.decide_outcome(excluded_count=0, missing_fields=["fees"]),
        oc.decide_outcome(excluded_count=0, missing_fields=[], parsed_count=0),
    }
    assert reachable <= set(s.ImportOutcome)
    assert len(reachable) == 3
