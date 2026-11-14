"""TICKET-926: one record from several files of the same broker.

Groww gives stocks and F&O as two downloads under one header. The second file is read
together with the first, not instead of it; a newer download replaces only the file it
overlaps. Every workbook here is made by the Groww fixture's script from made-up orders.
"""

from __future__ import annotations

import json
import os
import re

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from scripts import make_groww_fixture as groww
from services.production.api import routes_upload
from services.production.api.app import create_app
from services.production.db import models as m
from services.production.db.session import make_engine, make_session, run_migrations
from tests.unit.api.test_upload import DUPES, sign_up, upload

CSRF = re.compile(r'name="csrf_token"\s+value="([^"]+)"')

SHARES = [o for o in groww.ORDERS if o[2]]
FNO = [o for o in groww.ORDERS if not o[2] and o[1] != "NOT A CONTRACT"]
STOCKS_FILE = groww.build(SHARES)
FNO_FILE = groww.build(FNO)
NEWER_STOCKS = groww.build([o for o in SHARES if o[1] != "ITC"])
STOCKS_NAME = "Stocks Order History Nov 1 2026 to Nov 13 2026.xlsx"
FNO_NAME = "F&O Order History Nov 1 2026 to Nov 13 2026.xlsx"


@pytest.fixture()
def engine():
    e = make_engine(os.environ["SCOPE_DB"])
    run_migrations(e)
    return e


@pytest.fixture()
def client(engine):
    return sign_up(TestClient(create_app()), engine, "C-1", "both")


def latest(engine) -> m.Import:
    with make_session(engine) as sess:
        return sess.scalars(select(m.Import).order_by(m.Import.id.desc())).first()


def files_of(engine, imp: m.Import) -> list[str]:
    with make_session(engine) as sess:
        ids = json.loads(imp.reads_files) if imp.reads_files else [imp.raw_file_id]
        return [sess.get(m.RawFile, i).original_name for i in ids]


def trips(engine, imp: m.Import) -> list[tuple]:
    with make_session(engine) as sess:
        rows = sess.scalars(select(m.Trip).where(m.Trip.import_id == imp.id)).all()
        return sorted((t.symbol, t.segment, str(t.gross)) for t in rows)


def test_the_test_files_split_the_fixture_into_shares_and_fno():
    assert SHARES and FNO and len(SHARES) + len(FNO) == len(groww.ORDERS) - 1


def test_stocks_then_fno_is_one_record_holding_both(client, engine):
    assert upload(client, content=STOCKS_FILE, name=STOCKS_NAME).status_code == 303
    assert latest(engine).trips_reconstructed == 5
    assert upload(client, content=FNO_FILE, name=FNO_NAME).status_code == 303
    record = latest(engine)
    assert record.trips_reconstructed == 8
    assert files_of(engine, record) == [STOCKS_NAME, FNO_NAME]
    assert {segment for _, segment, _ in trips(engine, record)} == {"EQ", "OPT", "FUT"}


def test_the_order_of_the_two_uploads_does_not_change_the_record(client, engine):
    upload(client, content=STOCKS_FILE, name=STOCKS_NAME)
    upload(client, content=FNO_FILE, name=FNO_NAME)
    one = trips(engine, latest(engine))

    other = sign_up(TestClient(create_app()), engine, "C-2", "other")
    upload(other, content=FNO_FILE, name=FNO_NAME)
    upload(other, content=STOCKS_FILE, name=STOCKS_NAME)
    assert trips(engine, latest(engine)) == one


def test_a_newer_stocks_download_replaces_the_stocks_file_and_keeps_fno(client, engine):
    upload(client, content=STOCKS_FILE, name=STOCKS_NAME)
    upload(client, content=FNO_FILE, name=FNO_NAME)
    upload(client, content=NEWER_STOCKS, name="Stocks Order History newer.xlsx")
    record = latest(engine)
    assert files_of(engine, record) == [FNO_NAME, "Stocks Order History newer.xlsx"]
    assert record.trips_reconstructed == 7
    assert "ITC" not in {symbol for symbol, _, _ in trips(engine, record)}


def test_the_same_file_again_is_refused_naming_it_and_nothing_is_added(client, engine):
    upload(client, content=STOCKS_FILE, name=STOCKS_NAME)
    upload(client, content=FNO_FILE, name=FNO_NAME)
    before = latest(engine).id
    again = upload(client, content=STOCKS_FILE, name=STOCKS_NAME)
    assert again.status_code == 400
    assert "already uploaded this exact file" in again.text and STOCKS_NAME in again.text
    assert latest(engine).id == before


def test_a_file_that_overlaps_everything_replaces_the_record_as_before(client, engine):
    upload(client, DUPES / "clean.csv")
    upload(client, DUPES / "duplicated_block.csv", name="later.csv")
    record = latest(engine)
    assert record.reads_files is None
    assert files_of(engine, record) == ["later.csv"]


def test_the_full_groww_file_after_both_replaces_them(client, engine):
    upload(client, content=STOCKS_FILE, name=STOCKS_NAME)
    upload(client, content=FNO_FILE, name=FNO_NAME)
    upload(client, content=groww.build(), name="Order History all.xlsx")
    record = latest(engine)
    assert record.reads_files is None and record.trips_reconstructed == 8


def test_the_review_page_names_both_files(client, engine):
    upload(client, content=STOCKS_FILE, name=STOCKS_NAME)
    upload(client, content=FNO_FILE, name=FNO_NAME)
    page = client.get(f"/imports/{latest(engine).id}").text
    assert "Read together, from 2 files" in page
    assert STOCKS_NAME in page and "F&amp;O Order History" in page
    assert "Rows in the files" in page


def test_reading_again_reads_every_file(client, engine, monkeypatch):
    upload(client, content=STOCKS_FILE, name=STOCKS_NAME)
    upload(client, content=FNO_FILE, name=FNO_NAME)
    first = latest(engine)
    monkeypatch.setattr(routes_upload.pl, "out_of_date", lambda imp: True)
    csrf = CSRF.search(client.get("/upload").text).group(1)
    done = client.post(f"/imports/{first.id}/read-again", data={"csrf_token": csrf},
                       follow_redirects=False)
    assert done.status_code == 303, done.text[:300]
    again = latest(engine)
    assert again.id != first.id
    assert files_of(engine, again) == [STOCKS_NAME, FNO_NAME]
    assert trips(engine, again) == trips(engine, first)


def test_the_report_reads_the_combined_record(client, engine):
    upload(client, content=STOCKS_FILE, name=STOCKS_NAME)
    upload(client, content=FNO_FILE, name=FNO_NAME)
    for path in ("/mirror", "/journals", "/"):
        assert client.get(path).status_code == 200, path


def test_delete_everything_leaves_nothing(client, engine):
    upload(client, content=STOCKS_FILE, name=STOCKS_NAME)
    upload(client, content=FNO_FILE, name=FNO_NAME)
    token = CSRF.search(client.get("/account/delete").text).group(1)
    client.post("/account/delete", data={"understood": "yes", "csrf_token": token})
    with make_session(engine) as sess:
        assert sess.scalars(select(m.Import)).all() == []
        assert sess.scalars(select(m.RawFile)).all() == []
