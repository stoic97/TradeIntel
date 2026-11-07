"""TICKET-842: "Try it with a demo file", through the browser.

A visitor without his broker export loads the synthetic demo tradebook into his own
account and sees the report. The gate's five points, each pinned here:

1. The upload page offers it, and one click runs the ordinary pipeline.
2. (The file itself: tests/unit/demo/test_demo_tradebook.py.)
3. Every page drawn from the demo says so, and no page drawn from a real upload does.
4. It is an ordinary upload: listed as "Demo", taken by "Delete everything", and a
   real upload afterwards is exactly as if it had never been there.
5. Journals open on demo days; nothing written on them reaches a real upload.
"""

from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update

from services.production import demo
from services.production.api import admin_view
from services.production.api.app import create_app
from services.production.db import models as m
from services.production.db.session import make_session
from tests.unit.api.test_upload import DUPES, PNL, sign_up, upload

CSRF = re.compile(r'name="csrf_token"\s+value="([^"]+)"')
LINE = "This is a demo file, not your trading."
OFFER = "Try it with a demo file."
REAL = DUPES / "clean.csv"


@pytest.fixture()
def engine():
    import os

    from services.production.db.session import make_engine, run_migrations

    e = make_engine(os.environ["SCOPE_DB"])
    run_migrations(e)
    return e


@pytest.fixture()
def client(engine):
    return sign_up(TestClient(create_app()), engine, "D-1", "visitor")


def try_the_demo(client, follow=False):
    token = CSRF.search(client.get("/upload").text).group(1)
    return client.post("/upload/demo", data={"csrf_token": token}, follow_redirects=follow)


def imports(engine, login_id="visitor"):
    with make_session(engine) as sess:
        trader = sess.scalars(select(m.Trader).where(m.Trader.login_id == login_id)).one()
        return list(sess.scalars(
            select(m.Import).where(m.Import.trader_id == trader.id).order_by(m.Import.id)
        ).all())


def journal_ids(engine, import_id: int) -> list[int]:
    with make_session(engine) as sess:
        return list(sess.scalars(
            select(m.Journal.id).where(m.Journal.import_id == import_id)
        ).all())


def record_pages(engine, imp: m.Import) -> list[str]:
    """The pages a record is read on, and its first Journal if it has one: the demo has
    many; the two-trade real file may have none, and then there is no Journal page."""
    journals = [f"/journals/{journal_ids(engine, imp.id)[0]}"] if journal_ids(engine, imp.id) else []
    return ["/", "/mirror", "/mirror/chapter/1", "/mirror/chapter/3",
            "/mirror/fact/worst-days", "/journals", *journals,
            f"/imports/{imp.id}", "/eligibility", "/account"]


# ---------- 1. Offered beside the file picker; one click, the ordinary pipeline ----------

def test_the_upload_page_offers_the_demo_beside_the_file_picker(client):
    page = client.get("/upload").text
    assert OFFER in page and "export yet?" in page
    assert '<form method="post" action="/upload/demo"' in page


def test_one_click_loads_the_demo_through_the_ordinary_pipeline(client, engine):
    r = try_the_demo(client)
    (imp,) = imports(engine)
    assert (r.status_code, r.headers["location"]) == (303, f"/imports/{imp.id}")
    assert imp.source_account == demo.ACCOUNT
    assert imp.adapter_id == "dhan_tradebook_v1" and imp.trips_reconstructed > 0
    with make_session(engine) as sess:
        raw = sess.get(m.RawFile, imp.raw_file_id)
        assert raw.original_name == demo.FILE_NAME
        assert sess.scalars(select(m.Trip).where(m.Trip.import_id == imp.id)).first()
    assert journal_ids(engine, imp.id), "the pipeline wrote its Journals too"


def test_a_second_click_opens_the_same_demo(client, engine):
    try_the_demo(client)
    r = try_the_demo(client)
    (imp,) = imports(engine)
    assert (r.status_code, r.headers["location"]) == (303, f"/imports/{imp.id}")


def test_the_demo_needs_its_token_and_consent(client, engine):
    assert client.post("/upload/demo", data={}, follow_redirects=False).status_code == 403
    other = sign_up(TestClient(create_app()), engine, "D-2", "noconsent", consent=False)
    r = other.post("/upload/demo", data={"csrf_token": "x"}, follow_redirects=False)
    assert r.status_code in (302, 303, 403)
    assert imports(engine, "noconsent") == []


# ---------- 3. Every demo page says so; no real page does ----------

def test_every_page_drawn_from_the_demo_says_so(client, engine):
    try_the_demo(client)
    (imp,) = imports(engine)
    assert journal_ids(engine, imp.id), "the demo's pages include a Journal"
    for path in record_pages(engine, imp):
        r = client.get(path)
        assert r.status_code == 200, path
        assert r.text.count(LINE) == 1, path


def test_no_page_drawn_from_a_real_upload_says_so(client, engine):
    upload(client, REAL)
    (imp,) = imports(engine)
    for path in record_pages(engine, imp):
        assert LINE not in client.get(path).text, path


# ---------- 4. An ordinary upload ----------

def test_the_uploads_list_labels_it_demo(client):
    try_the_demo(client)
    account = client.get("/account").text
    assert "Demo" in account.split("Your uploads", 1)[1]


def test_delete_everything_takes_the_demo_with_it(client, engine):
    try_the_demo(client)
    token = CSRF.search(client.get("/account/delete").text).group(1)
    client.post("/account/delete", data={"understood": "yes", "csrf_token": token})
    with make_session(engine) as sess:
        assert sess.scalars(select(m.Import)).all() == []
        assert sess.scalars(select(m.RawFile)).all() == []


def test_a_real_upload_after_the_demo_is_as_if_it_had_never_been_there(client, engine):
    try_the_demo(client)
    upload(client, REAL)
    (real,) = imports(engine)
    assert real.source_account != demo.ACCOUNT
    assert (real.version_no, real.supersedes_import_id) == (1, None)

    fresh = sign_up(TestClient(create_app()), engine, "D-3", "fresh")
    upload(fresh, REAL)
    (alone,) = imports(engine, "fresh")
    assert real.trips_reconstructed == alone.trips_reconstructed
    assert len(journal_ids(engine, real.id)) == len(journal_ids(engine, alone.id))
    with make_session(engine) as sess:
        assert sess.scalars(select(m.TradingDayVersion).where(
            m.TradingDayVersion.source_account == demo.ACCOUNT)).all() == []
    for path in ("/", "/mirror", "/journals", "/account"):
        assert LINE not in client.get(path).text, path


def test_a_refused_real_file_leaves_the_demo_where_it_was(client, engine):
    try_the_demo(client)
    upload(client, content=PNL, name="pnl.csv")
    demo_import, refused = imports(engine)
    assert demo_import.source_account == demo.ACCOUNT
    assert LINE in client.get("/mirror").text, "the record shown is still the demo"
    assert LINE not in client.get(f"/imports/{refused.id}").text, "his refused file is his"


def test_once_he_has_a_real_record_the_demo_is_not_offered_or_taken(client, engine):
    upload(client, REAL)
    assert OFFER not in client.get("/upload").text
    r = try_the_demo(client)
    assert r.status_code == 303 and r.headers["location"] == "/mirror"
    assert [i.source_account for i in imports(engine)] == ["A"]


# ---------- What /admin makes of it, through the real upload paths (TICKET-865) ----------

def admin_row_and_cards(engine) -> tuple[dict, dict]:
    with make_session(engine) as sess:
        sess.execute(update(m.Trader).values(development_data=False))
        sess.commit()
    with make_session(engine) as sess:
        built = admin_view.build(sess, running_version="x", production=False)
    return next(r for r in built["rows"] if r["login_id"] == "visitor"), built["cards"]


def test_admin_reads_a_loaded_demo_as_the_demo(client, engine):
    try_the_demo(client)
    row, cards = admin_row_and_cards(engine)
    assert row["file"] == "demo"
    assert (cards["tried_demo"], cards["uploaded_real"]) == (1, 0)


def test_admin_reads_a_real_upload_after_the_demo_as_real(client, engine):
    try_the_demo(client)
    upload(client, REAL)
    row, cards = admin_row_and_cards(engine)
    assert row["file"] == "real"
    assert (cards["tried_demo"], cards["uploaded_real"]) == (0, 1)


# ---------- 5. Journals on demo days; nothing carried ----------

def test_a_demo_journal_opens_and_nothing_written_on_it_reaches_a_real_upload(client, engine):
    try_the_demo(client)
    (imp,) = imports(engine)
    first = journal_ids(engine, imp.id)[0]
    page = client.get(f"/journals/{first}")
    assert page.status_code == 200
    token = CSRF.search(page.text).group(1)
    client.post(f"/journals/{first}/field",
                data={"field": "note", "value": "written on a demo day", "trip_id": "",
                      "csrf_token": token})
    with make_session(engine) as sess:
        assert sess.scalars(select(m.JournalFieldEntry)).all(), "the note was kept"

    upload(client, REAL)
    with make_session(engine) as sess:
        assert sess.scalars(select(m.JournalFieldEntry)).all() == []
        assert sess.get(m.Journal, first) is None
