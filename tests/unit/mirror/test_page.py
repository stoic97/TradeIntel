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

NEVER_USED = [
    "because", "caused", "due to", "you should", "we recommend", "try to",
    "edge", "alpha", "expectancy", "your R", "tilt", "revenge",
]


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
                quantity=t["lots"],
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


def test_no_template_makes_a_claim_it_has_not_earned(client):
    """PRD 7.3's never-use list, enforced on what actually renders."""
    body = client.get("/mirror").text.lower()
    for word in NEVER_USED:
        assert word not in body, f"the Mirror says {word!r}"


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
