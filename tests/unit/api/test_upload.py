"""Upload and import review, through the browser (PRD 5.2-5.4).

The pipeline was proven in phase 1; this is about the route around it. What these
tests fix is mostly what must NOT happen: no upload without consent, no silent
duplicate, no file read before its size is checked, and no trader seeing another
trader's import.

That last one is the test easiest to forget and worst to fail. An ownership check
missing from one route is a tradebook shown to the wrong person.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update

from services.production.api.app import create_app
from services.production.db import models as m
from services.production.db.session import make_engine, make_session, run_migrations
from services.shared.schemas import scope_v1 as s

CSRF = re.compile(r'name="csrf_token"\s+value="([^"]+)"')
DUPES = Path("data/fixtures/duplicates")
PNL = b"Symbol,Realised P&L\nWIDGETOIL,1500.00\n"


def sign_up(client, engine, code: str, login_id: str, consent: bool = True):
    from datetime import UTC, datetime
    with make_session(engine) as sess:
        sess.add(m.InviteCode(code=code, created_at=datetime.now(UTC)))
        sess.commit()
    csrf = CSRF.search(client.get(f"/invite/{code}").text).group(1)
    client.post(f"/invite/{code}", data={"login_id": login_id, "display_name": login_id,
                                         "password": "a-long-enough-password",
                                         "csrf_token": csrf})
    with make_session(engine) as sess:
        sess.execute(update(m.Trader).where(m.Trader.login_id == login_id)
                     .values(development_data=True))
        sess.commit()
    csrf = CSRF.search(client.get("/login").text).group(1)
    client.post("/login", data={"login_id": login_id,
                                "password": "a-long-enough-password",
                                "csrf_token": csrf})
    if consent:
        csrf = CSRF.search(client.get("/consent").text).group(1)
        client.post("/consent", data={"diagnosis": "yes", "engine_testing": "yes",
                                      "csrf_token": csrf})
    return client


@pytest.fixture()
def engine():
    """The same database the app uses.

    conftest sets SCOPE_DB per test; building a second engine at another path would
    write invites to a file create_app() never reads, and every page would 404.
    """
    import os
    e = make_engine(os.environ["SCOPE_DB"])
    run_migrations(e)
    return e


@pytest.fixture()
def client(engine):
    return sign_up(TestClient(create_app()), engine, "U-1", "rikk")


def upload(client, path: Path | None = None, content: bytes | None = None,
           name: str = "tradebook.csv"):
    csrf = CSRF.search(client.get("/upload").text).group(1)
    data = content if content is not None else path.read_bytes()
    return client.post("/upload", files={"file": (name, data, "text/csv")},
                       data={"csrf_token": csrf}, follow_redirects=False)


def test_upload_needs_consent(engine):
    client = sign_up(TestClient(create_app()), engine, "U-2", "noconsent", consent=False)
    assert client.get("/upload", follow_redirects=False).status_code in (302, 303)


def test_a_good_file_creates_an_import_and_redirects_to_its_review(client, engine):
    response = upload(client, DUPES / "clean.csv")
    assert response.status_code in (302, 303)
    assert "/imports/" in response.headers["location"]
    with make_session(engine) as sess:
        imp = sess.scalars(select(m.Import)).one()
        assert imp.outcome is s.ImportOutcome.ACCEPTED_PARTIAL_FIELDS
        assert imp.rows_in == 4


def test_the_stored_file_is_encrypted_and_matches_the_record(client, engine, tmp_path):
    upload(client, DUPES / "clean.csv")
    with make_session(engine) as sess:
        raw = sess.scalars(select(m.RawFile)).one()
    on_disk = Path(raw.stored_path).read_bytes()
    assert b"WIDGETOIL" not in on_disk
    import hashlib
    assert raw.sha256 == hashlib.sha256((DUPES / "clean.csv").read_bytes()).hexdigest()


def test_the_same_file_twice_is_refused_with_a_message(client):
    upload(client, DUPES / "clean.csv")
    second = upload(client, DUPES / "clean.csv")
    assert second.status_code == 400
    assert "already" in second.text.lower()


def test_a_file_over_the_cap_is_refused(client):
    from services.production.journal import constants as k
    oversized = b"x" * (k.MAX_UPLOAD_BYTES + 1)
    response = upload(client, content=oversized)
    assert response.status_code == 400
    assert "10" in response.text


def test_a_wrong_file_shows_the_rejection_and_nothing_else(client, engine):
    response = upload(client, content=PNL, name="pnl.csv")
    assert response.status_code in (302, 303)
    review = client.get(response.headers["location"]).text
    assert "trade-level" in review.lower()
    for absent in ("rows in", "trips", "journal unit"):
        assert absent not in review.lower()


def test_the_review_shows_duplicates_and_the_day_diff(client):
    response = upload(client, DUPES / "duplicated_block.csv")
    review = client.get(response.headers["location"]).text
    assert "6" in review
    assert "duplicate" in review.lower()
    assert "2026-10-15" in review


def test_confirming_duplicates_creates_a_new_version(client, engine):
    response = upload(client, DUPES / "duplicated_block.csv")
    location = response.headers["location"]
    page = client.get(location).text
    csrf = CSRF.search(page).group(1)
    group = re.search(r'name="dup_group" value="([^"]+)"', page).group(1)
    client.post(f"{location}/confirm-duplicates",
                data={"dup_group": group, "csrf_token": csrf})
    with make_session(engine) as sess:
        imports = sess.scalars(select(m.Import).order_by(m.Import.id)).all()
        assert len(imports) == 2
        assert imports[1].version_no == 2
        assert imports[1].rows_excluded > 0


def test_a_trader_cannot_see_another_traders_import(client, engine):
    upload(client, DUPES / "clean.csv")
    with make_session(engine) as sess:
        import_id = sess.scalars(select(m.Import)).one().id

    other = sign_up(TestClient(create_app()), engine, "U-3", "someone-else")
    assert other.get(f"/imports/{import_id}").status_code == 404


def test_the_account_page_offers_what_he_can_do(client):
    """Found 17 Oct: the account page named no action, so the only way to the
    upload was typing the URL."""
    body = client.get("/account").text
    assert "/upload" in body
    assert "/settings/consent" in body


def test_a_trader_with_uploads_sees_them_listed(client, engine):
    upload(client, DUPES / "clean.csv")
    body = client.get("/account").text
    assert "/imports/" in body
    assert "Nothing has been uploaded" not in body


def test_signing_in_lands_on_the_upload_when_there_is_nothing_yet(engine):
    """A page saying 'nothing has been uploaded' is not a destination."""
    client = sign_up(TestClient(create_app()), engine, "U-4", "fresh")
    csrf = CSRF.search(client.get("/login").text).group(1)
    response = client.post("/login", data={"login_id": "fresh",
                                           "password": "a-long-enough-password",
                                           "csrf_token": csrf},
                           follow_redirects=False)
    assert "/upload" in response.headers["location"]


def test_signing_in_lands_on_the_latest_import_when_there_is_one(client, engine):
    upload(client, DUPES / "clean.csv")
    with make_session(engine) as sess:
        import_id = sess.scalars(select(m.Import)).one().id
    csrf = CSRF.search(client.get("/login").text).group(1)
    response = client.post("/login", data={"login_id": "rikk",
                                           "password": "a-long-enough-password",
                                           "csrf_token": csrf},
                           follow_redirects=False)
    assert f"/imports/{import_id}" in response.headers["location"]

def _two_days() -> bytes:
    """The clean fixture, plus a second trading day of two round trips.

    Two things have to be true before an upload writes a day Journal, and the first
    draft of this fixture had only one of them.

    A day is complete only when the file contains a later one -- nothing in a
    single-day export says the trading is over -- so one day can never produce a
    Journal. That much was the reason for a second day.

    The second is the density rule (PRD 2): the unit is the trading day only when
    the median eligible day has at least two trips, and otherwise it is per 10
    trips. A second day carrying one round trip made the median 1.5, so the unit
    fell back to per-10 and three trips produced nothing -- the rule working
    correctly on a fixture too thin to show it. Hence two round trips a day.
    """
    base = (DUPES / "clean.csv").read_text().rstrip("\n").splitlines()
    later = [
        ("2026-10-15,09:30:00,WIDGETOIL 19 NOV 5000 CALL,BUY,INTRADAY,MCX,"
         "Commodity,100,53.00,5300.00,Traded"),
        ("2026-10-15,10:30:00,WIDGETOIL 19 NOV 5000 CALL,SELL,INTRADAY,MCX,"
         "Commodity,100,53.10,5310.00,Traded"),
        ("2026-10-15,11:30:00,WIDGETOIL 19 NOV 5000 CALL,BUY,INTRADAY,MCX,"
         "Commodity,100,53.20,5320.00,Traded"),
        ("2026-10-15,12:30:00,WIDGETOIL 19 NOV 5000 CALL,SELL,INTRADAY,MCX,"
         "Commodity,100,53.30,5330.00,Traded"),
    ]
    return ("\n".join(base + later) + "\n").encode()


def test_an_upload_writes_a_journal_for_every_complete_day(client, engine):
    """PRD 7.2: cadence is upload cadence.

    The modules that generate Journals were built and tested on their own, and
    nothing called them from the upload: a trader would have reached an empty
    Journal list after a successful import, with every unit test passing.
    """
    upload(client, content=_two_days())
    with make_session(engine) as sess:
        written = list(sess.scalars(select(m.Journal)).all())
    assert [j.period_start for j in written] == ["2026-10-14"], (
        "the complete day gets a Journal; the day with nothing after it does not"
    )


def test_the_journal_list_shows_what_the_upload_generated(client):
    upload(client, content=_two_days())
    assert "2026-10-14" in client.get("/journals").text
