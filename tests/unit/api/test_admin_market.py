"""TICKET-998: the admin page's Market data card, and connecting Fyers from it.

The card amends 848's read-only page by exactly this: two forms, each a POST with the page's
CSRF token, and the broker's GET back to the callback, checked by a signed state instead. Every
token, code and price here is made up; the broker's code exchange is faked, never the network.
"""

from __future__ import annotations

import base64
import json
import logging
import re
from datetime import UTC, date, datetime, timedelta
from urllib.parse import parse_qs, urlparse

import pytest
from sqlalchemy import select, text

from services.production.db import models as m
from services.production.db.session import make_session
from services.production.market import fyers
from services.production.market import token as T
from services.shared.market import day_store as ds
from services.shared.market import series as ms
from tests.helpers.admin_page import ADMIN, add_trader, admin_page_app, admin_page_engine, signed_in

CSRF = re.compile(r'name="csrf_token"\s+value="([^"]+)"')
APP_ID, SECRET = "MADEUP-100", "made-up-secret"


def made_up_token(expires: datetime) -> str:
    def part(d: dict) -> str:
        return base64.urlsafe_b64encode(json.dumps(d).encode()).decode().rstrip("=")
    return f"{part({'alg': 'none'})}.{part({'exp': int(expires.timestamp())})}.made-up-signature"


TOKEN = made_up_token(datetime.now(UTC) + timedelta(hours=5))


@pytest.fixture()
def app(monkeypatch, tmp_path):
    monkeypatch.setenv("FYERS_APP_ID", APP_ID)
    monkeypatch.setenv("FYERS_SECRET_KEY", SECRET)
    monkeypatch.setenv("FYERS_REDIRECT_URI", "https://scope.example/admin/fyers/callback")
    monkeypatch.setenv("SCOPE_MARKET_DIR", str(tmp_path / "market"))
    exchanged: list[str] = []

    def exchange(app_, code):
        exchanged.append(code)
        if code == "an-expired-code":
            raise fyers.ExchangeFailed("the code has expired or was used already")
        return TOKEN

    monkeypatch.setattr(fyers, "exchange", exchange)
    application = admin_page_app(monkeypatch)
    application.state.exchanged = exchanged
    return application


@pytest.fixture()
def engine(app):
    return admin_page_engine(app)


def admin(app, engine):
    client = signed_in(app, add_trader(engine, ADMIN))
    page = client.get("/admin")
    assert page.status_code == 200
    return client, CSRF.search(page.text)[1]


def stored(engine) -> list[m.MarketToken]:
    with make_session(engine) as sess:
        return sess.scalars(select(m.MarketToken)).all()


def actions(engine) -> list[tuple[str, str | None]]:
    with make_session(engine) as sess:
        return [(a.action, a.target) for a in sess.scalars(select(m.AdminAction).order_by(m.AdminAction.id))]


# ---------- admins only, and the same 404 for everyone else ----------

@pytest.mark.parametrize("who", ["signed out", "trader"])
@pytest.mark.parametrize(("method", "path"), [
    ("POST", "/admin/fyers/connect"), ("POST", "/admin/fyers/paste"), ("GET", "/admin/fyers/callback"),
    ("GET", "/admin/fyers/connect"), ("DELETE", "/admin/fyers/paste"),
])
def test_anyone_but_an_admin_gets_the_same_404_as_an_unknown_address(app, engine, who, method, path):
    client = signed_in(app, None if who == "signed out" else add_trader(engine, "someone"))
    unknown, got = client.request(method, "/no-such-page"), client.request(method, path)
    assert got.status_code == 404 and got.text == unknown.text


def test_a_form_without_the_pages_csrf_token_is_refused_and_nothing_is_stored(app, engine):
    client, _ = admin(app, engine)
    got = client.post("/admin/fyers/paste", data={"address": "https://www.google.com/?auth_code=x"})
    assert got.status_code == 403
    assert stored(engine) == [] and app.state.exchanged == []


# ---------- (A) one click, when the redirect comes back here ----------

def test_connect_sends_the_admin_to_fyers_login_with_a_signed_state(app, engine):
    client, csrf = admin(app, engine)
    got = client.post("/admin/fyers/connect", data={"csrf_token": csrf})
    assert got.status_code == 303
    where = urlparse(got.headers["location"])
    asked = parse_qs(where.query)
    assert where.netloc.endswith("fyers.in") and asked["client_id"] == [APP_ID]
    assert asked["redirect_uri"] == ["https://scope.example/admin/fyers/callback"]
    assert asked["state"][0] and SECRET not in got.headers["location"]
    assert ("fyers_login_started", None) in actions(engine)


def test_the_callback_with_the_signed_state_stores_the_token_encrypted(app, engine):
    client, csrf = admin(app, engine)
    state = parse_qs(urlparse(client.post("/admin/fyers/connect", data={"csrf_token": csrf})
                              .headers["location"]).query)["state"][0]
    got = client.get("/admin/fyers/callback", params={"auth_code": "a-good-code", "state": state, "s": "ok"})
    assert got.status_code == 303 and got.headers["location"] == "/admin?fyers=connected#market"
    rows = stored(engine)
    assert len(rows) == 1 and TOKEN not in rows[0].ciphertext
    assert ("fyers_connected", None) in actions(engine)


def test_a_callback_whose_state_isnt_ours_stores_nothing(app, engine):
    client, _ = admin(app, engine)
    got = client.get("/admin/fyers/callback", params={"auth_code": "a-good-code", "state": "made.up"})
    assert got.status_code == 303 and "fyers=refused" in got.headers["location"]
    assert stored(engine) == [] and app.state.exchanged == []


# ---------- (B) paste the whole address bar, always there ----------

def test_a_pasted_address_bar_is_read_for_its_code_and_stored(app, engine):
    client, csrf = admin(app, engine)
    pasted = "https://www.google.com/?s=ok&code=200&auth_code=a-pasted-code&state=None"
    got = client.post("/admin/fyers/paste", data={"csrf_token": csrf, "address": pasted})
    assert got.status_code == 303 and "fyers=connected" in got.headers["location"]
    assert app.state.exchanged == ["a-pasted-code"] and len(stored(engine)) == 1


def test_an_expired_code_is_refused_says_so_and_stores_nothing(app, engine):
    client, csrf = admin(app, engine)
    got = client.post("/admin/fyers/paste", data={"csrf_token": csrf,
                                                 "address": "https://www.google.com/?auth_code=an-expired-code"})
    assert "fyers=expired" in got.headers["location"]
    assert stored(engine) == []
    page = client.get("/admin?fyers=expired").text
    assert "expired" in page and "log in again" in page.lower()


def test_an_address_with_no_code_in_it_is_refused(app, engine):
    client, csrf = admin(app, engine)
    got = client.post("/admin/fyers/paste", data={"csrf_token": csrf, "address": "https://www.google.com/"})
    assert "fyers=no-code" in got.headers["location"] and app.state.exchanged == []


# ---------- the token is never seen ----------

def test_the_token_is_in_no_column_no_page_and_no_log(app, engine, caplog):
    caplog.set_level(logging.DEBUG)
    client, csrf = admin(app, engine)
    client.post("/admin/fyers/paste", data={"csrf_token": csrf, "address": "https://x/?auth_code=a-pasted-code"})
    page = client.get("/admin").text
    assert TOKEN not in page and "a-pasted-code" not in page
    assert TOKEN not in caplog.text and "a-pasted-code" not in caplog.text
    with make_session(engine) as sess:
        for table in m.Base.metadata.sorted_tables:
            for row in sess.execute(text(f'SELECT * FROM "{table.name}"')):
                assert TOKEN not in " ".join(str(v) for v in row), table.name
    with make_session(engine) as sess:
        assert T.read(sess, app.state.settings.file_key, now=datetime.now(UTC)) == TOKEN


# ---------- the card ----------

def test_the_card_says_never_connected_then_connected_until(app, engine):
    client, csrf = admin(app, engine)
    assert "never connected" in client.get("/admin").text
    client.post("/admin/fyers/paste", data={"csrf_token": csrf, "address": "https://x/?auth_code=a-pasted-code"})
    assert "connected until" in client.get("/admin").text


def test_the_card_shows_each_series_last_day_and_days_behind_and_never_a_price(app, engine, tmp_path):
    store = ds.DayStore(tmp_path / "market" / "CRUDEOIL", "CRUDEOIL")
    store.put(date(2026, 3, 2), b"timestamp,open,high,low,close,volume\n",
              [b"2026-03-02 09:00:00,5432,5439,5428,5436,10\n"])
    store.save(serves=("CRUDEOIL",), source="made up", roll="", clock=ms.CLOCK, interval="1 minute",
               built=date(2026, 3, 2))
    with make_session(engine) as sess:
        sess.add(m.MarketSyncRun(started_at=datetime.now(UTC), finished_at=datetime.now(UTC), result="ok",
                                 summary=json.dumps({"CRUDEOIL": {"added": 1, "refused": []}})))
        sess.add(m.MarketDayRequest(underlying="INFY", trading_day="2026-03-02", requested_at=datetime.now(UTC),
                                    status="waiting", tries=0))
        sess.commit()
    client, _ = admin(app, engine)
    page = client.get("/admin").text
    card = page[page.index('id="market"'):]
    assert "Crude oil" in card or "CRUDEOIL" in card
    assert "02 Mar 2026" in card
    assert "Stock days waiting: 1" in card
    for price in ("5432", "5439", "5428", "5436"):
        assert price not in card
    for underlying in ("NIFTY", "BANKNIFTY", "SENSEX", "GOLD", "SILVER"):
        assert underlying in card


def test_on_a_server_with_no_fyers_keys_the_card_has_no_forms(app, engine, monkeypatch):
    monkeypatch.delenv("FYERS_APP_ID")
    client = signed_in(app, add_trader(engine, ADMIN))
    page = client.get("/admin").text
    card = page[page.index('id="market"'):]
    assert "not set up on this server" in card and "<form" not in page and "csrf_token" not in page
    assert client.post("/admin/fyers/connect", data={"csrf_token": "any"}).status_code == 404
