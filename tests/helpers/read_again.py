"""Moved out of tests/unit/api/test_read_again.py by TICKET-945, so that no test file imports another."""

from __future__ import annotations

import html
import re
from pathlib import Path

from sqlalchemy import func, select

from services.production.ctr import reconstruct as rc
from services.production.db import models as m
from services.production.db.session import make_session
from services.production.mirror import loader
from tests.helpers.upload import CSRF

HEADER = (
    "Date,Time,Name,Buy/Sell,Order,Exchange,Segment,Quantity/Lot,Trade Price,Trade Value,Status"
)


OPTION = "NIFTY 25 JAN 20000 CALL"


TABLES = (
    m.RawFile,
    m.Import,
    m.ImportRow,
    m.Trip,
    m.SkippedTrip,
    m.OpenPosition,
    m.TradingDayVersion,
    m.Journal,
    m.ChargeStatement,
    m.ReportFeedback,
)


def _row(day: str, time: str, side: str, value: int) -> str:
    return (
        f"{day},{time},{OPTION},{side},INTRADAY,NSE,Derivative,50,{value / 50:.2f},"
        f"{value:.2f},Traded"
    )


FILE = (
    "\n".join(
        [
            HEADER,
            _row("2024-01-02", "09:30:00", "BUY", 5000),
            _row("2024-01-02", "09:40:00", "SELL", 4500),
            _row("2024-01-02", "10:00:00", "BUY", 5000),
            _row("2024-01-02", "10:10:00", "SELL", 4700),
            _row("2024-01-03", "09:30:00", "BUY", 5000),
            _row("2024-01-03", "09:40:00", "SELL", 5100),
            _row("2024-01-03", "10:00:00", "SELL", 6000),
            _row("2024-01-03", "10:10:00", "BUY", 5500),
            _row("2024-01-04", "09:30:00", "BUY", 5000),
            _row("2024-01-04", "09:40:00", "SELL", 5040),
            _row("2024-01-04", "10:00:00", "BUY", 5000),
            _row("2024-01-04", "10:10:00", "SELL", 5060),
        ]
    ).encode()
    + b"\n"
)


A_LATER_FILE = (
    FILE
    + _row("2024-01-04", "10:30:00", "BUY", 5000).encode()
    + b"\n"
    + _row("2024-01-04", "10:40:00", "SELL", 5010).encode()
    + b"\n"
)


NAME = "TRADE_HISTORY_one.csv"


def upload_older(client, monkeypatch, content=FILE, *, logic=True, name=NAME, export_date=None):
    """Upload under older code: no stamp, as an import from before this feature reads, and
    with ``logic`` reconstruction that refuses a sold option. Then the code moves on."""
    real = rc.reconstruct

    def refusing(fills, **kwargs):
        return real(fills, **{**kwargs, "short_options": False})

    with monkeypatch.context() as older:
        older.setattr(rc, "RECONSTRUCTION_VERSION", None, raising=False)
        if logic:
            older.setattr(rc, "reconstruct", refusing)
        return send(client, content, name, export_date)


def send(client, content=FILE, name=NAME, export_date=None):
    csrf = CSRF.search(client.get("/upload").text).group(1)
    data = {"csrf_token": csrf}
    if export_date:
        data["export_date"] = export_date
    return client.post(
        "/upload", files={"file": (name, content, "text/csv")}, data=data, follow_redirects=False
    )


def read_again(client, import_id: int, **kwargs):
    csrf = CSRF.search(client.get("/upload").text).group(1)
    return client.post(
        f"/imports/{import_id}/read-again",
        data={"csrf_token": csrf},
        follow_redirects=False,
        **kwargs,
    )


def imports(engine) -> list[m.Import]:
    with make_session(engine) as sess:
        return list(sess.scalars(select(m.Import).order_by(m.Import.id)).all())


def counts(engine) -> dict[str, int]:
    with make_session(engine) as sess:
        return {t.__tablename__: sess.scalar(select(func.count()).select_from(t)) for t in TABLES}


def current(engine):
    with make_session(engine) as sess:
        return loader.current_import(sess, sess.scalars(select(m.Trader)).first())


def words(page: str) -> str:
    page = re.sub(r"<(script|style|svg)\b.*?</\1>", " ", page, flags=re.DOTALL)
    return html.unescape(" ".join(re.sub(r"<[^>]+>", " ", page).split()))


def stored_path(engine) -> Path:
    with make_session(engine) as sess:
        return Path(sess.scalars(select(m.RawFile)).first().stored_path)


def confirm(client, import_id: int, group: str):
    page = client.get(f"/imports/{import_id}").text
    return client.post(
        f"/imports/{import_id}/confirm-duplicates",
        data={"dup_group": group, "csrf_token": CSRF.search(page).group(1)},
        follow_redirects=False,
    )


def answer(client, engine, journal: int, **data):
    csrf = CSRF.search(client.get(f"/journals/{journal}").text).group(1)
    response = client.post(
        f"/journals/{journal}/field", data={**data, "csrf_token": csrf}, follow_redirects=False
    )
    assert response.status_code in (200, 303)
