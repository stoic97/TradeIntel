"""The eligibility page (PRD 5.6), from the outside.

It is the first thing a trader reads, and it is the product's account of its own
limits. Three things it must never do: present a draft framework as a fixed one,
put a never-use word in front of a trader, or let a check vanish silently because
nobody decided what to say about it.
"""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from services.production.api.app import create_app
from services.production.db import models as m
from services.production.db.session import make_engine, make_session, run_migrations
from services.shared.prereg import reader
from services.shared.schemas import scope_v1 as s

CSRF = re.compile(r'name="csrf_token"\s+value="([^"]+)"')
PASSWORD = "a-long-enough-password"

# PRD 7.5 and the Workbook. "edge" matters here specifically: the library calls
# two of its own checks overall_edge and edge_persistence, so rendering their
# names would walk this straight onto a trader's screen.
NEVER_USED = [
    "tilt", "revenge", "emotional", "psychology", "disease", "cure",
    "edge", "alpha", "expectancy", "discipline", "mistake", "signal", "tip",
]


@pytest.fixture()
def engine():
    import os
    e = make_engine(os.environ["SCOPE_DB"])
    run_migrations(e)
    return e


@pytest.fixture()
def client(engine):
    from services.production.accounts import auth
    with make_session(engine) as sess:
        trader = m.Trader(display_name="F", login_id="fx",
                          password_hash=auth.hash_password(PASSWORD),
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
                       outcome=s.ImportOutcome.ACCEPTED_PARTIAL_FIELDS,
                       rows_in=40, rows_parsed=40, rows_excluded=0,
                       fees_available=False, version_no=1, trips_reconstructed=40,
                       density_default_unit="day", created_at=datetime.now(UTC))
        sess.add(imp)
        sess.flush()
        rows = json.loads(Path("tests/fixtures/mirror_contract/main.json").read_text())
        for row in rows:
            sess.add(m.Trip(
                import_id=imp.id, trip_id=row["trip_id"],
                trading_day=row["trading_day"], exchange=row["exchange"],
                symbol=row["symbol"], segment="OPT", direction="LONG",
                entry_ts=datetime.fromisoformat(row["entry_ts"]),
                exit_ts=datetime.fromisoformat(row["exit_ts"]),
                quantity=row["quantity"], entry_price=Decimal(100),
                exit_price=Decimal(100), gross=Decimal(row["gross"]),
                fees=Decimal(row["fees"]), net=Decimal(row["net"]),
                fees_available=False,
                risk_unit_source=s.RiskUnitSourceV1(row["risk_unit_source"])))
        sess.add(m.ConsentEvent(trader_id=trader.id,
                                purpose=s.ConsentPurpose.DIAGNOSIS, scope="v1",
                                terms_version="0-draft", granted=True,
                                at=datetime.now(UTC), method="web",
                                wording_shown="x" * 100))
        sess.commit()
    client = TestClient(create_app())
    csrf = CSRF.search(client.get("/login").text).group(1)
    client.post("/login", data={"login_id": "fx", "password": PASSWORD,
                                "csrf_token": csrf}, follow_redirects=False)
    return client


def test_the_page_renders(client):
    assert client.get("/eligibility").status_code == 200


def test_every_check_in_the_library_appears(client):
    """A check nobody decided what to say about must not just be absent."""
    body = client.get("/eligibility").text
    for test in reader.load().tests:
        assert f">{test.id}<" in body, f"{test.id} is missing from the page"


def test_it_says_the_framework_is_still_a_draft(client):
    """Until the kickoff lock, a threshold here is written down, not fixed."""
    body = client.get("/eligibility").text.lower()
    assert "draft" in body
    assert "not yet fixed" in body


def test_no_never_use_word_reaches_the_rendered_page(client):
    """The template guard reads template source; this reads what was rendered.

    Two of the library's own checks are called overall_edge and edge_persistence,
    so printing the question names would put a banned word in front of a trader
    through a variable, where the source-level guard cannot see it.
    """
    body = client.get("/eligibility").text.lower()
    for word in NEVER_USED:
        assert re.search(rf"\b{re.escape(word)}\b", body) is None, word


def test_a_check_that_cannot_run_says_what_is_missing(client):
    body = client.get("/eligibility").text
    assert "TD-004" in body, "the tick-data checks name their deferral"
    assert "TD-003" in body, "the stop-order check names its deferral"


def test_nothing_on_the_page_reads_as_a_verdict(client):
    body = client.get("/eligibility").text.lower()
    for claim in ("you should", "we recommend", "your score", "you tend to",
                  "caused by", "due to"):
        assert claim not in body, claim


def test_a_trader_with_no_import_is_sent_to_upload(engine):
    from services.production.accounts import auth
    with make_session(engine) as sess:
        trader = m.Trader(display_name="N", login_id="nothing",
                          password_hash=auth.hash_password(PASSWORD),
                          created_at=datetime.now(UTC), development_data=True)
        sess.add(trader)
        sess.flush()
        sess.add(m.ConsentEvent(trader_id=trader.id,
                                purpose=s.ConsentPurpose.DIAGNOSIS, scope="v1",
                                terms_version="0-draft", granted=True,
                                at=datetime.now(UTC), method="web",
                                wording_shown="x" * 100))
        sess.commit()
    client = TestClient(create_app())
    csrf = CSRF.search(client.get("/login").text).group(1)
    client.post("/login", data={"login_id": "nothing", "password": PASSWORD,
                                "csrf_token": csrf}, follow_redirects=False)
    assert client.get("/eligibility", follow_redirects=False).status_code in (302, 303)


def test_it_needs_signing_in(engine):
    anonymous = TestClient(create_app())
    assert anonymous.get("/eligibility",
                         follow_redirects=False).status_code in (302, 303)
