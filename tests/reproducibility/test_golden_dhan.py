"""The golden test: a known input, a committed expected output.

Methodology s7 and s12: every transformation runs twice and produces identical
bytes, and matches a committed golden. The unit tests check the cases someone
thought to write down; the golden catches a change to a number nobody thought
about. It is the regression guard for every change after this one.

The fixture deliberately contains the awkward cases:

* an **aggregated fill** (30 units, quoted 153.18, exact total 4595.50) -- price is
  derived from the value, so the per-unit figure is a repeating decimal
* a **December trade against a January expiry** -- the year must roll forward
* a **partial close** that leaves a position open
* a **flip** -- a sell larger than the long position, closing it and opening a short
* a **short option** opened by a SELL -- refused, counted, never guessed
* an **equity hold** -- no risk unit, so no R
* a **cancelled row** and an **unparseable contract name** -- both rejected with reasons
* the file in **reverse chronological order**, as Dhan exports it

Known artifact in the committed golden: the aggregated fill's ``risk_unit`` reads
4595.499999999999999999999999 and its trip's ``gross_pnl`` 204.500000000000000000000001,
because the value is divided to a price and multiplied back. To be fixed by carrying
the value itself; the golden diff will show those two numbers correcting.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from services.production.ctr.adapters.dhan_tradebook import parse
from services.production.ctr.reconstruct import reconstruct
from services.production.ctr.snapshot import canonical_json, digest, snapshot

FIXTURE = Path("data/fixtures/dhan_tradebook_sample.csv")
GOLDEN = Path("data/golden/dhan_tradebook_sample.ctr.json")
TRADER_ID = "FIXTURE"


def _import():
    raw_hash = hashlib.sha256(FIXTURE.read_bytes()).hexdigest()
    parsed = parse(FIXTURE, trader_id=TRADER_ID, raw_hash=raw_hash)
    recon = reconstruct(parsed.fills, fees_available=parsed.fees_available)
    return parsed, recon


def test_the_fixture_and_golden_are_committed():
    assert FIXTURE.exists(), "the fixture must be in the repo, not generated"
    assert GOLDEN.exists(), "run: uv run python scripts/regenerate_golden.py --yes"


def test_parsing_twice_gives_identical_bytes():
    a, b = _import(), _import()
    assert digest(snapshot(*a)) == digest(snapshot(*b))


def test_the_import_matches_the_committed_golden():
    """If this fails, a number changed. Read the diff before regenerating."""
    fresh = canonical_json(snapshot(*_import()))
    committed = GOLDEN.read_text(encoding="utf-8")
    assert fresh == committed, (
        "output differs from the committed golden.\n"
        "Run `uv run python scripts/regenerate_golden.py` to see the diff.\n"
        "Every changed number must be one you meant to change."
    )


def test_the_golden_covers_the_cases_it_claims_to():
    """A golden nobody checks is a photograph of a bug. These assert its shape."""
    g = json.loads(GOLDEN.read_text(encoding="utf-8"))
    assert g["parse"]["rows_in"] == 19
    assert g["parse"]["fills_parsed"] == 17
    assert g["parse"]["fees_available"] is False

    reasons = " ".join(r["reason"] for r in g["parse"]["rejected"])
    assert "Cancelled" in reasons
    assert "NOT A CONTRACT" in reasons

    recon = g["reconstruction"]
    assert len(recon["skipped"]) == 1
    assert "short option" in recon["skipped"][0]["reason"]
    assert len(recon["open_positions"]) == 2
    assert {o["direction"] for o in recon["open_positions"]} == {"LONG", "SHORT"}

    trips = recon["round_trips"]
    assert any(t["symbol"] == "NIFTY" and t["expiry"] == "2027-01-01" for t in trips)
    eq = [t for t in trips if t["segment"] == "EQ"]
    assert eq and all(t["r_multiple"] is None for t in eq)
    opt = [t for t in trips if t["segment"] == "OPT"]
    assert opt and all(t["risk_unit_source"] == "PREMIUM_PAID" for t in opt)


def test_quantity_conservation_holds_on_the_fixture():
    _, recon = _import()
    matched = 2 * sum(t.quantity for t in recon.round_trips)
    refused = 2 * sum(s.quantity for s in recon.skipped)
    still_open = sum(o.quantity for o in recon.open_positions)
    assert matched + refused + still_open == recon.quantity_in


def test_the_fixture_and_golden_are_not_gitignored():
    """A file can exist on disk and still be invisible to git.

    The first .gitignore excluded `data/` outright, which made the
    `!data/fixtures/**` negation useless -- git cannot re-include a file whose
    parent directory is excluded. The fixture and golden would have been silently
    absent from every clone, and nothing would have failed. Caught by hand; this
    is the test that catches it next time.
    """
    import subprocess

    for path in (FIXTURE, GOLDEN):
        done = subprocess.run(
            ["git", "check-ignore", "-q", str(path)],
            capture_output=True,
            check=False,
        )
        # exit 0 = ignored, 1 = not ignored (without -v, the code is the authority)
        assert done.returncode == 1, f"{path} is gitignored and would never be committed"


def test_trader_data_paths_are_gitignored():
    """The other half of the same rule: real tradebooks must never be committable."""
    import subprocess

    for path in ("data/raw/export.csv", "data/partners/t01.xlsx", "private/notes.csv"):
        done = subprocess.run(
            ["git", "check-ignore", "-q", path], capture_output=True, check=False
        )
        assert done.returncode == 0, f"{path} is NOT ignored -- trader data could be committed"


def test_a_fill_consumed_in_whole_keeps_the_brokers_exact_value():
    """The requirement the golden only records: exactness survives the pipeline.

    Dhan's aggregated row reports 30 units at an exact total of 4595.50 with a
    quoted average of 153.18. We derive price = value / quantity, which is a
    repeating decimal, and the reconstructor multiplies it back -- losing the
    exactness the broker handed us. risk_unit is "the premium you paid", a figure
    a trader may see, and for a fill consumed in whole it is known exactly.

    No test covered the adapter's output flowing into the reconstructor, which is
    why real data found this and the 54 unit tests did not.
    """
    from decimal import Decimal

    _, recon = _import()
    trip = next(
        t for t in recon.round_trips if t.symbol == "CRUDEOILM" and t.strike == Decimal(5600)
    )
    assert trip.quantity == 30
    assert trip.risk_unit == Decimal("4595.50"), "the premium paid is known exactly"
    assert trip.gross_pnl == Decimal("204.50"), "4800.00 - 4595.50, exactly"
