"""The Mirror page: fixed order, a drawer on every line, and no claims.

The page formats what the metric functions return and computes nothing, so these
tests are about what a trader sees: the sections in the order the PRD fixes, a
drawer behind every line, a thin sample said rather than shown as a bare number,
and no sentence that asserts a cause or recommends an action.

The last of those is the one with teeth. v1 shows counted facts. The moment a
template says 'because' or 'you should', the product has made a claim it has not
earned and the research gate exists to prevent.
"""

from __future__ import annotations

import re
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from services.production.api.app import create_app
from services.production.db import models as m
from services.production.db.session import make_engine, make_session, run_migrations
from services.shared.schemas import scope_v1 as s_enums

CSRF = re.compile(r'name="csrf_token"\s+value="([^"]+)"')

SECTION_ORDER = [
    "worst trading days",
    "where the money came from",
    "trading on while already down",
    "how long you hold",
    "the clock",
]

# Words the product never uses, from PRD 7.5 and the Workbook's never-use list.
# These are claims by their nature: there is no sentence in which the product may
# call a trader's behaviour tilt or name his edge.
NEVER_USED = [
    "tilt", "revenge", "emotional", "psychology", "disease", "cure",
    "edge", "alpha", "expectancy", "discipline", "mistake", "should have",
]

# Patterns that ASSERT a cause, a grade or a recommendation. Banned as claims --
# which is why the test exempts section 6.7, whose whole job is to say the product
# does none of these. A rule against making claims is not a rule against denying
# them, and the first version of this guard did not know the difference: it banned
# "caused" and "we recommend" while 6.7 printed "cause" and "recommends", so both
# tests passed by luck. "The cause of this was" would have sailed through.
CLAIM_PATTERNS = [
    r"\bbecause\b", r"\bcaused by\b", r"\bthe cause of\b", r"\bdue to\b",
    r"\bled to\b", r"\bresulted from\b",
    r"\byou should\b", r"\bwe recommend\b", r"\btry to\b", r"\bconsider \w+ing\b",
    r"\byour score\b", r"\bwe estimate\b", r"\bcost you\b",
]

SECTION_6_7 = "what we have not told you"


@pytest.fixture()
def engine():
    import os
    e = make_engine(os.environ["SCOPE_DB"])
    run_migrations(e)
    return e


@pytest.fixture()
def client(engine):
    """A trader with the contract fixture loaded as his history."""
    import json
    from datetime import UTC, datetime
    from pathlib import Path

    from services.production.accounts import auth

    with make_session(engine) as sess:
        trader = m.Trader(display_name="Fixture", login_id="fx",
                          password_hash=auth.hash_password("a-long-enough-password"),
                          created_at=datetime.now(UTC), development_data=True)
        sess.add(trader)
        sess.flush()
        raw = m.RawFile(trader_id=trader.id, sha256="f" * 64, original_name="f.csv",
                        size=1, stored_path="/tmp/f", uploaded_at=datetime.now(UTC))
        sess.add(raw)
        sess.flush()
        imp = m.Import(trader_id=trader.id, raw_file_id=raw.id, source_account="A",
                       adapter_id="dhan_tradebook_v1", adapter_version="1",
                       filemap_version="1", code_version="fixturesha",
                       outcome=s_enums.ImportOutcome.ACCEPTED_PARTIAL_FIELDS,
                       rows_in=40, rows_parsed=40,
                       rows_excluded=0, fees_available=False, version_no=1,
                       trips_reconstructed=40,
                       density_default_unit="day", created_at=datetime.now(UTC))
        sess.add(imp)
        sess.flush()
        trips = json.loads(Path("tests/fixtures/mirror_contract/main.json").read_text())
        for t in trips:
            sess.add(m.Trip(
                import_id=imp.id, trip_id=t["trip_id"], trading_day=t["trading_day"],
                exchange=t["exchange"], symbol=t["symbol"], segment="OPT",
                direction="LONG",
                entry_ts=datetime.fromisoformat(t["entry_ts"]),
                exit_ts=datetime.fromisoformat(t["exit_ts"]),
                quantity=t["quantity"],
                entry_price=Decimal(100), exit_price=Decimal(100),
                gross=Decimal(t["gross"]), fees=Decimal(t["fees"]),
                net=Decimal(t["net"]),
                fees_available=False, risk_unit_source=s_enums.RiskUnitSourceV1(t["risk_unit_source"])))
        sess.add(m.ConsentEvent(trader_id=trader.id,
                                purpose=s_enums.ConsentPurpose.DIAGNOSIS, scope="v1",
                                terms_version="0-draft", granted=True,
                                at=datetime.now(UTC), method="web", wording_shown="x" * 100))
        sess.commit()

    client = TestClient(create_app())
    csrf = CSRF.search(client.get("/login").text).group(1)
    client.post("/login", data={"login_id": "fx",
                                "password": "a-long-enough-password",
                                "csrf_token": csrf}, follow_redirects=False)
    return client


def test_the_mirror_renders(client):
    assert client.get("/mirror").status_code == 200


def test_the_sections_appear_in_the_order_the_prd_fixes(client):
    body = client.get("/mirror").text.lower()
    positions = [body.find(heading) for heading in SECTION_ORDER]
    assert all(p >= 0 for p in positions), dict(zip(SECTION_ORDER, positions, strict=True))
    assert positions == sorted(positions), "sections are out of order"


def test_the_headline_figures_are_the_fixture_figures(client):
    body = client.get("/mirror").text
    assert "96%" in body, "share of total"
    assert "24,000" in body, "five worst days"
    assert "15.8%" in body, "strike rate"
    assert "3.0" in body, "holding ratio"
    assert "10" in body, "longest losing run"


def test_every_line_has_a_drawer(client):
    body = client.get("/mirror").text
    for line in ("worst-days", "best-worst-trades", "two-straight-losses",
                 "holding-time", "by-hour"):
        assert f"/mirror/{line}/drawer" in body, line


def test_a_drawer_lists_the_trades_behind_its_line(client):
    body = client.get("/mirror/two-straight-losses/drawer").text
    assert "t06" in body or "2026-09-02" in body
    assert "17" in body, "the condition count"


def test_a_drawer_belongs_to_its_owner_only(client, engine):
    from datetime import UTC, datetime

    from services.production.accounts import auth
    with make_session(engine) as sess:
        sess.add(m.Trader(display_name="Other", login_id="other",
                          password_hash=auth.hash_password("a-long-enough-password"),
                          created_at=datetime.now(UTC), development_data=True))
        sess.commit()
    other = TestClient(create_app())
    csrf = CSRF.search(other.get("/login").text).group(1)
    other.post("/login", data={"login_id": "other",
                               "password": "a-long-enough-password",
                               "csrf_token": csrf}, follow_redirects=False)
    body = other.get("/mirror").text
    assert "t06" not in body
    assert "96%" not in body


def test_figures_are_labelled_gross_when_fees_are_absent(client):
    body = client.get("/mirror").text.lower()
    assert "gross" in body
    assert "before brokerage" in body or "before charges" in body


def test_the_page_carries_its_lineage(client):
    body = client.get("/mirror").text
    assert "fixturesha" in body, "the code version that computed these figures"


def test_a_trader_with_no_history_is_told_so_not_shown_zeroes(engine):
    from datetime import UTC, datetime

    from services.production.accounts import auth
    with make_session(engine) as sess:
        sess.add(m.Trader(display_name="Empty", login_id="empty",
                          password_hash=auth.hash_password("a-long-enough-password"),
                          created_at=datetime.now(UTC), development_data=True))
        sess.commit()
    client = TestClient(create_app())
    csrf = CSRF.search(client.get("/login").text).group(1)
    client.post("/login", data={"login_id": "empty",
                                "password": "a-long-enough-password",
                                "csrf_token": csrf}, follow_redirects=False)
    body = client.get("/mirror").text
    assert "0%" not in body, "a zero is a figure; absence is not"
    assert "upload" in body.lower()


def test_no_template_uses_a_never_use_word(client):
    """PRD 7.5's never-use list, on what actually renders."""
    body = client.get("/mirror").text.lower()
    for word in NEVER_USED:
        assert word not in body, f"the Mirror says {word!r}"


def test_no_template_asserts_a_cause_a_grade_or_a_recommendation(client):
    """The claim patterns, everywhere except section 6.7's disclaimer.

    6.7 exists to say the product names no cause and recommends nothing, which it
    cannot say without using those words. Everything above it must not.
    """
    body = client.get("/mirror").text.lower()
    above_6_7 = body.split(SECTION_6_7)[0]
    assert len(body.split(SECTION_6_7)) == 2, "section 6.7 is missing or duplicated"
    for pattern in CLAIM_PATTERNS:
        found = re.search(pattern, above_6_7)
        assert found is None, f"the Mirror claims: {found.group(0)!r}"


def test_section_6_7_is_the_only_place_those_words_appear(client):
    """A disclaimer that drifts upward into the body would be a claim."""
    body = client.get("/mirror").text.lower()
    disclaimer = body.split(SECTION_6_7)[1]
    for word in ("cause", "score", "recommend"):
        assert word in disclaimer, f"6.7 must disclaim {word!r}"


def test_the_unqualified_symbol_R_never_appears(client):
    """Decision 15: figures divided by a budget are labelled in words."""
    body = client.get("/mirror").text
    assert not re.search(r"\b\d+(\.\d+)?\s*R\b", body), "an unqualified R multiple"


def test_times_are_shown_in_the_instrument_timezone_not_utc(client):
    """Found 19 Oct in the browser: every time read five and a half hours early.

    The database normalises to UTC, which is right -- a stored instant must be
    unambiguous. The Mirror then rendered the stored value raw, so a 09:20 trade
    appeared as 03:50 and the clock section reported hours 03 to 06 for a day that
    ran 09 to 12. The unit tests missed it because the fixture JSON carries +05:30
    offsets and never goes through the database.

    This is TD-026 on screen: the trading day and the hour must both come from the
    instrument profile's timezone (definitions_v1.md section 1).
    """
    body = client.get("/mirror").text
    assert "09:00" in body or "10:00" in body, "the clock is in IST"
    assert "03:00" not in body and "04:00" not in body, "the clock is in UTC"

    drawer = client.get("/mirror/worst-days/drawer").text
    assert "09:20" in drawer or "09:30" in drawer, "entry times are in IST"
    assert "03:50" not in drawer, "entry times are in UTC"


def test_the_worst_hour_is_the_hour_the_fixture_says(client, ):
    """Appendix A: hour 10 IST is the worst at -13,250, with 21 trades."""
    body = client.get("/mirror").text
    assert "13,250" in body
    assert "6,850" in body, "hour 09"


def test_section_6_6_says_what_could_not_be_read(client):
    """PRD 6.6: rows in, parsed, excluded with reasons; duplicates with the option to
    confirm; trips reconstructed and refused; risk figures by source; fees."""
    body = client.get("/mirror").text.lower()
    assert "what we could not read" in body
    assert "40" in body, "rows in"
    assert "risk figure" in body
    assert "no charges column" in body or "fees" in body


def test_section_6_6_counts_risk_figures_by_source(client):
    body = client.get("/mirror").text
    assert "your declared budget" in body.lower()
    assert "your stop" in body.lower()
    assert "18" in body, "declared_budget count"
    assert "10" in body, "defined_stop count"


def test_premium_paid_is_counted_but_never_a_denominator(client):
    """PRD 5.5: premium_paid and inferred_atr are recorded, never divided by."""
    body = client.get("/mirror").text.lower()
    assert "premium" in body, "it is counted"
    assert "× premium" not in body and "x premium" not in body


def test_section_6_7_says_what_we_have_not_told_you(client):
    """PRD 6.7: the plain statement, in the trader's sight, not a footnote."""
    body = client.get("/mirror").text.lower()
    assert "what we have not told you" in body
    for disclaimed in ("cause", "score", "cost", "recommend"):
        assert disclaimed in body, f"6.7 must disclaim {disclaimed}"


def test_the_clock_shows_the_worst_three_hours(client):
    """PRD 6.5: result by entry hour, worst three -- not every hour."""
    body = client.get("/mirror").text
    assert "13,250" in body, "the worst hour"
    assert "6,850" in body, "the second worst"
    assert "4,650" in body or "3,900" in body, "the third worst"


def test_section_6_3_compares_strike_rate_and_lots(client):
    """PRD 6.3: for those trades versus the rest -- strike rate, average lots."""
    body = client.get("/mirror").text.lower()
    assert "strike rate" in body
    assert "lots" in body
