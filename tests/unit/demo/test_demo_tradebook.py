"""TICKET-842, gate 2: the demo tradebook is synthetic, reproducible, in Dhan's shape, and
has one of each thing the report talks about.

Read through the production pipeline exactly as an upload is (``plan_import`` with
``production=True``), so "Dhan's shape" means "what the adapter accepts", not what the
file looks like. The report's own functions then count what it would show.
"""

from __future__ import annotations

import importlib.util
import sys
from collections import defaultdict
from pathlib import Path

import pytest

from services.production.ctr.adapters import dhan_tradebook as dhan
from services.production.ctr.intake import pipeline as pl
from services.production.eligibility import assess as el
from services.production.mirror import metrics as mx
from services.shared.prereg import reader

GENERATOR = Path("data/fixtures/demo/scope_demo.py")
FILE = Path("data/fixtures/demo/scope_demo_tradebook.csv")


def generator():
    spec = importlib.util.spec_from_file_location("scope_demo", GENERATOR)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # a dataclass resolves its module by name
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def plan():
    return pl.plan_import(
        FILE.read_text(encoding="utf-8"),
        context=pl.ImportContext(trader_id="demo", source_account="DEMO",
                                 code_version="test", export_date="2026-09-01",
                                 export_date_source="trader"),
        production=True,
    )


@pytest.fixture(scope="module")
def trips(plan):
    """The plan's positions as the report's metrics read a trade: one per position."""
    return mx.load_trips([
        {"trip_id": p.position_id, "symbol": p.legs[0].symbol,
         "trading_day": p.entry_ts.date().isoformat(),
         "entry_ts": p.entry_ts.isoformat(), "exit_ts": p.exit_ts.isoformat(),
         "holding_seconds": int((p.exit_ts - p.entry_ts).total_seconds()),
         "net": str(p.net), "lots": 1, "risk_unit_source": "premium_paid",
         "segment": "OPT"}
        for p in plan.positions
    ])


def test_the_committed_file_is_what_the_seeded_generator_writes():
    """Reproducible: the seed is committed, and the file is its output, byte for byte."""
    assert generator().render() == FILE.read_text(encoding="utf-8")


def test_it_is_in_dhans_shape_newest_first():
    lines = FILE.read_text(encoding="utf-8").splitlines()
    assert lines[0] == ",".join(dhan.HEADER)
    stamps = [line.split(",")[0] + " " + line.split(",")[1] for line in lines[1:]]
    assert stamps == sorted(stamps, reverse=True)


def test_the_production_pipeline_reads_every_row(plan):
    assert plan.rows_in == plan.rows_parsed == len(plan.rows) > 0
    assert {r.status for r in plan.rows} == {"PARSED"}
    assert plan.rows_excluded == 0 and not plan.skipped and plan.open_positions == 0


def test_it_names_no_one_and_trades_only_contracts_scope_reads(plan):
    """README rule 1: synthetic. Two real contracts, chosen because a profile exists."""
    assert {leg.symbol for p in plan.positions for leg in p.legs} == {"CRUDEOIL", "NIFTY"}


def test_it_has_one_of_each_thing_the_report_talks_about(plan, trips):
    assert any(len(p.legs) == 2 for p in plan.positions), "a spread"
    assert any(p.risk_unit_source.value == "UNCAPPED" for p in plan.positions), "a sold option"
    assert any(p.exit_ts.date() > p.entry_ts.date() for p in plan.positions), "a held position"
    books = defaultdict(int)
    for p in plan.positions:
        books[p.legs[0].symbol] += 1
    assert set(books) == {"CRUDEOIL", "NIFTY"} and min(books.values()) >= mx.BOOK_ROW_MINIMUM
    assert mx.longest_losing_run(trips).length >= 5, "a losing run"
    assert len({t.trading_day for t in trips}) >= 5 and len(mx.worst_five(trips)) == 5


def test_it_passes_the_eligibility_rule_on_its_own(trips):
    """Enough trading days (B5) and enough same-day trades (B2) to be checked."""
    enough = {v.test.id for v in el.assess(trips, reader.load()).enough}
    assert {"B2", "B5"} <= enough


def test_its_whole_result_is_a_loss_so_the_reveal_shows_a_share(trips):
    """The reveal's first state needs a losing whole (handoff 7); a demo should show it."""
    assert sum(t.net for t in trips) < 0
