"""Moved out of tests/unit/api/test_upload.py by TICKET-945, so that no test file imports another.

Fixtures are not kept here: each fixture that lived in that file is a plain function
below, and the fixture of the same name calls it.
"""

from __future__ import annotations

import re
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import update

from services.production.api.app import create_app
from services.production.db import models as m
from services.production.db.session import make_engine, make_session, run_migrations

CSRF = re.compile(r'name="csrf_token"\s+value="([^"]+)"')


DUPES = Path("data/fixtures/duplicates")


PNL = b"Symbol,Realised P&L\nWIDGETOIL,1500.00\n"


def sign_up(client, engine, code: str, login_id: str, consent: bool = True):
    client.cookies.clear()  # signing up signs in, and two traders can share a test client
    csrf = CSRF.search(client.get("/signup").text).group(1)
    client.post(
        "/signup",
        data={
            "login_id": login_id,
            "display_name": login_id,
            "password": "a-long-enough-password",
            "csrf_token": csrf,
        },
    )
    with make_session(engine) as sess:
        sess.execute(
            update(m.Trader).where(m.Trader.login_id == login_id).values(development_data=True)
        )
        sess.commit()
    csrf = CSRF.search(client.get("/login").text).group(1)
    client.post(
        "/login",
        data={"login_id": login_id, "password": "a-long-enough-password", "csrf_token": csrf},
    )
    if consent:
        csrf = CSRF.search(client.get("/consent").text).group(1)
        client.post(
            "/consent", data={"diagnosis": "yes", "engine_testing": "yes", "csrf_token": csrf}
        )
    return client


def upload_engine():
    """The same database the app uses.

    conftest sets SCOPE_DB per test; building a second engine at another path would
    write invites to a file create_app() never reads, and every page would 404.
    """
    import os

    e = make_engine(os.environ["SCOPE_DB"])
    run_migrations(e)
    return e


def upload_client(engine):
    return sign_up(TestClient(create_app()), engine, "U-1", "rikk")


def upload(
    client, path: Path | None = None, content: bytes | None = None, name: str = "tradebook.csv"
):
    csrf = CSRF.search(client.get("/upload").text).group(1)
    data = content if content is not None else path.read_bytes()
    return client.post(
        "/upload",
        files={"file": (name, data, "text/csv")},
        data={"csrf_token": csrf},
        follow_redirects=False,
    )


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
        (
            "2026-10-15,09:30:00,WIDGETOIL 19 NOV 5000 CALL,BUY,INTRADAY,MCX,"
            "Commodity,100,53.00,5300.00,Traded"
        ),
        (
            "2026-10-15,10:30:00,WIDGETOIL 19 NOV 5000 CALL,SELL,INTRADAY,MCX,"
            "Commodity,100,53.10,5310.00,Traded"
        ),
        (
            "2026-10-15,11:30:00,WIDGETOIL 19 NOV 5000 CALL,BUY,INTRADAY,MCX,"
            "Commodity,100,53.20,5320.00,Traded"
        ),
        (
            "2026-10-15,12:30:00,WIDGETOIL 19 NOV 5000 CALL,SELL,INTRADAY,MCX,"
            "Commodity,100,53.30,5330.00,Traded"
        ),
    ]
    return ("\n".join(base + later) + "\n").encode()
