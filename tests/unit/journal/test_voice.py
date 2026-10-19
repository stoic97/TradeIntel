"""The Journal's voice (PRD 7.3, 7.5).

Counted prose, comparative to himself, never causal, never evaluative. The two
rejected examples are the useful ones: not "You revenge-traded after two losses" --
a claim -- and not "Three trades, net -0.4R, size stable" -- a table with full
stops, using a symbol v1 does not print.

These tests render real facts through the real templates and read the result,
because the voice is a property of the output, not of the template source.
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from decimal import Decimal
from pathlib import Path

import pytest

from services.production.journal import periods as pd
from services.production.journal import prose
from services.production.journal import sections as sec
from services.production.mirror.metrics import Trip
from services.shared.schemas import scope_v1 as s

NEVER_USED = ["tilt", "revenge", "emotional", "psychology", "disease", "cure",
              "signal", "tip", "edge", "alpha", "expectancy", "discipline",
              "mistake", "should have", "well done", "unfortunately"]

CLAIMS = [
    (r"\byou\b[^.]{0,80}\bbecause\b", "asserts a cause"),
    (r"\bcaused by\b", "asserts a cause"),
    (r"\byou should\b", "recommends"),
    (r"\bwe recommend\b", "recommends"),
    (r"\btry to\b", "recommends"),
    (r"\byou tend to\b", "generalises past the count"),
    (r"\bthis means\b", "interprets"),
    (r"\bgood\b|\bbad\b|\bpoor\b|\bstrong\b", "evaluates"),
]

UNQUALIFIED_R = re.compile(r"\b\d+(\.\d+)?\s*R\b")


def load() -> list[Trip]:
    return [
        Trip(trip_id=r["trip_id"], trading_day=r["trading_day"],
             entry_ts=datetime.fromisoformat(r["entry_ts"]),
             exit_ts=datetime.fromisoformat(r["exit_ts"]),
             holding_seconds=r["holding_seconds"], net=Decimal(r["net"]),
             lots=r["lots"],
             risk_unit_source=s.RiskUnitSourceV1(r["risk_unit_source"]))
        for r in json.loads(Path("tests/fixtures/mirror_contract/main.json").read_text())
    ]


def rendered(which: str) -> str:
    trips = load()
    period = next(p for p in pd.periods_for(trips, unit=s.JournalUnit.DAY,
                                            export_date="2026-09-30")
                  if p.period_start == which)
    facts = sec.build(period, history=trips, fees_available=False)
    return prose.render(facts)


ALL_DAYS = ["2026-09-01", "2026-09-02", "2026-09-03", "2026-09-04",
            "2026-09-07", "2026-09-08", "2026-09-09", "2026-09-10"]


def test_it_reads_as_prose_not_a_table():
    text = rendered("2026-09-02")
    assert text.count(".") >= 4, "sentences, not fragments"
    assert "|" not in text and "\t" not in text


def test_the_counts_are_the_facts():
    text = rendered("2026-09-02")
    assert "Six trades" in text or "6 trades" in text
    assert "8,000" in text
    assert "gross" in text.lower()


def test_the_behaviour_is_stated_with_his_own_baseline():
    """The baseline must be his, and must say that it is his whole history.

    Not a substring check on "of your": the sentence moved the possessive to
    "everything you have uploaded" and the old assertion failed on wording that was
    better, not worse. What matters is that the baseline is tied to him and that no
    population is invoked -- v1 has none, and "traders like you" needs fifty per
    stratum.
    """
    text = rendered("2026-09-02")
    assert "two trades before them had both closed at a loss" in text.lower()
    assert "you have uploaded" in text.lower(), "the baseline is his own history"
    # "average" alone is not a population word: "your average size" is his own.
    # The ban is on comparing him to anyone else.
    for population in ("other traders", "traders like you", "the average trader",
                       "most people", "the typical", "compared to others"):
        assert population not in text.lower(), f"invokes {population!r}"


def test_a_day_without_the_behaviour_does_not_mention_it():
    text = rendered("2026-09-01")
    assert "closed at a loss" not in text.lower()


def test_the_blank_stop_is_said_once_without_comment(  ):
    text = rendered("2026-09-02")
    assert text.lower().count("planned stop") == 1
    for word in ("should", "remember", "important"):
        assert word not in text.lower()


@pytest.mark.parametrize("day", ALL_DAYS)
def test_no_journal_uses_a_never_use_word(day):
    text = rendered(day).lower()
    for word in NEVER_USED:
        assert re.search(rf"\b{re.escape(word)}\b", text) is None, f"{day}: {word!r}"


@pytest.mark.parametrize("day", ALL_DAYS)
def test_no_journal_makes_a_claim(day):
    text = rendered(day).lower()
    for pattern, why in CLAIMS:
        found = re.search(pattern, text)
        assert found is None, f"{day} {why}: {found.group(0)!r}"


@pytest.mark.parametrize("day", ALL_DAYS)
def test_no_journal_prints_an_unqualified_r(day):
    assert UNQUALIFIED_R.search(rendered(day)) is None


@pytest.mark.parametrize("day", ALL_DAYS)
def test_every_journal_is_renderable_and_non_empty(day):
    text = rendered(day)
    assert len(text.strip()) > 80, f"{day} rendered almost nothing"
    assert "None" not in text, "an unfilled value reached the page"
    assert "{{" not in text, "an unrendered placeholder"
