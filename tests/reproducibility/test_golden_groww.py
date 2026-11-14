"""Groww's golden (TICKET-895): its own known input and committed output.

The fixture is a made-up workbook laid out as Groww's real download is: a preamble with a
name and client code, the header on row 6, one row per order, a total value and no price.
It holds the awkward cases:

* an **order filled at several prices** (3 shares, total 4595.50): the trip's gross is
  exactly 204.50, the value carried, never rebuilt from a price
* an **after-market order** stamped 09:00
* a **share on BSE**, read against BSE's cash-equity profile
* a **partial close** that leaves a position open, and a buy left open
* **weekly and monthly options and a future**, in the exchanges' symbol forms
* a **cancelled** and a **rejected** order, and a row nothing can identify
* a **comma** inside a stock name
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from decimal import Decimal
from pathlib import Path

from scripts import make_groww_fixture
from services.production.ctr.adapters.groww_orders import parse
from services.production.ctr.intake import pipeline as pl
from services.production.ctr.reconstruct import reconstruct
from services.production.ctr.snapshot import canonical_json, digest, snapshot

FIXTURE = Path("data/fixtures/groww_orders_sample.xlsx")
GOLDEN = Path("data/golden/groww_orders_sample.ctr.json")


def _import():
    content = FIXTURE.read_bytes()
    parsed = parse(pl.text_of(content).splitlines(), trader_id="FIXTURE",
                   raw_hash=hashlib.sha256(content).hexdigest())
    return parsed, reconstruct(parsed.fills, fees_available=parsed.fees_available)


def test_the_fixture_is_what_its_script_writes():
    assert FIXTURE.read_bytes() == make_groww_fixture.build(), (
        "run: uv run python scripts/make_groww_fixture.py")


def test_parsing_twice_gives_identical_bytes():
    assert digest(snapshot(*_import())) == digest(snapshot(*_import()))


def test_the_import_matches_the_committed_golden():
    """If this fails, a number changed. Read the diff before regenerating."""
    assert canonical_json(snapshot(*_import())) == GOLDEN.read_text(encoding="utf-8"), (
        "run `uv run python scripts/regenerate_golden.py --groww` to see the diff")


def test_the_golden_covers_the_cases_it_claims_to():
    g = json.loads(GOLDEN.read_text(encoding="utf-8"))
    assert (g["parse"]["rows_in"], g["parse"]["fills_parsed"]) == (20, 17)
    assert g["parse"]["fees_available"] is False
    reasons = " ".join(r["reason"] for r in g["parse"]["rejected"])
    assert "Cancelled" in reasons and "Rejected" in reasons and "NOT A CONTRACT" in reasons

    recon = g["reconstruction"]
    trips = recon["round_trips"]
    assert {t["segment"] for t in trips} == {"EQ", "OPT", "FUT"}
    assert any(t["exchange"] == "BSE" for t in trips)
    assert len(recon["open_positions"]) == 2
    assert not recon["skipped"]


def test_the_order_filled_at_several_prices_stays_exact():
    (infy,) = [t for t in _import()[1].round_trips if t.symbol == "INFY"]
    assert infy.gross_pnl == Decimal("204.50")


def test_the_fixture_and_golden_are_not_gitignored():
    for path in (FIXTURE, GOLDEN):
        done = subprocess.run(["git", "check-ignore", "-q", str(path)],
                              capture_output=True, check=False)
        assert done.returncode == 1, f"{path} is gitignored and would never be committed"
