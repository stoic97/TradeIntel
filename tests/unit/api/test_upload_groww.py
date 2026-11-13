"""TICKET-895 gate 6: a Groww workbook uploaded through the page reaches a rendered report.

The ordinary route, the ordinary pipeline: the upload is read from its header down, its
import records the Groww adapter and the profile versions, and the trader's pages draw
from it. Nothing from the workbook's preamble is shown back.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from services.production.api.app import create_app
from services.production.ctr.adapters import groww_orders
from services.production.db import models as m
from services.production.db.session import make_engine, make_session, run_migrations
from tests.unit.api.test_upload import sign_up, upload

FIXTURE = Path("data/fixtures/groww_orders_sample.xlsx")
NAME = "Stocks Order History Nov 1 2026 to Nov 13 2026.xlsx"


@pytest.fixture()
def engine():
    e = make_engine(os.environ["SCOPE_DB"])
    run_migrations(e)
    return e


@pytest.fixture()
def client(engine):
    return sign_up(TestClient(create_app()), engine, "G-1", "growwer")


def the_import(engine) -> m.Import:
    with make_session(engine) as sess:
        return sess.scalars(select(m.Import).order_by(m.Import.id.desc())).first()


def test_a_groww_workbook_uploads_and_its_import_records_what_read_it(client, engine):
    response = upload(client, content=FIXTURE.read_bytes(), name=NAME)
    assert response.status_code == 303, response.text[:400]
    imp = the_import(engine)
    assert imp.adapter_id == groww_orders.FORMAT_ID
    assert imp.adapter_version == "1"
    assert {"NSE:*", "BSE:*", "NSE:NIFTY"} <= set(json.loads(imp.profile_versions))
    assert (imp.rows_in, imp.rows_parsed) == (20, 17)
    assert imp.trips_reconstructed == 8


def test_the_report_renders_from_it_and_never_shows_the_preamble(client, engine):
    upload(client, content=FIXTURE.read_bytes(), name=NAME)
    imp = the_import(engine)
    for path in ("/mirror", f"/imports/{imp.id}", "/journals", "/"):
        page = client.get(path)
        assert page.status_code == 200, path
        assert "Sample Trader" not in page.text and "Unique Client Code" not in page.text, path
    review = client.get(f"/imports/{imp.id}").text
    assert "could not read" in review and "no charges column" in review


def test_the_stored_rows_are_the_orders_not_the_preamble(client, engine):
    upload(client, content=FIXTURE.read_bytes(), name=NAME)
    with make_session(engine) as sess:
        rows = sess.scalars(select(m.ImportRow.raw_text)).all()
    assert len(rows) == 20
    assert not [r for r in rows if "Sample Trader" in r or "Unique Client Code" in r]


def test_the_upload_page_says_groww_works_and_takes_an_excel_file(client):
    page = client.get("/upload").text
    assert "Works with: Dhan and Groww" in page
    assert "To download it from Groww" in page
    assert ".xlsx" in page
