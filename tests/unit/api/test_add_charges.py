"""The optional second file after an upload: the broker's charges, as a record (TICKET-828).

A synthetic two-day tradebook, hand-worked:
    day one  buy 1,000.00  sell 1,200.00   result +200
    day two  buy 2,000.00  sell 1,500.00   result -500
    before charges -300

A synthetic charges file: 50.50 on day one and 60.25 on day two, 110.75 in all, so net
is -300 - 110.75 = -410.75. Shown through the rupees filter, which cuts to whole rupees:
charges 110, net -410. Scope works none of those charges out.
"""

from __future__ import annotations

import re
from dataclasses import replace
from decimal import Decimal as D
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from services.production.api.app import create_app
from services.production.charges import record
from services.production.db import models as m
from services.production.db.session import make_session
from tests.unit.api.test_upload import CSRF, engine, sign_up, upload  # noqa: F401

NAME = "WIDGETOIL 19 MAR 5000 CALL"
FILE = "\n".join([
    "Date,Time,Name,Buy/Sell,Order,Exchange,Segment,Quantity/Lot,Trade Price,Trade Value,Status",
    f"2020-03-02,09:30:00,{NAME},BUY,INTRADAY,MCX,Commodity,100,10.00,1000.00,Traded",
    f"2020-03-02,10:00:00,{NAME},SELL,INTRADAY,MCX,Commodity,100,12.00,1200.00,Traded",
    f"2020-03-03,09:30:00,{NAME},BUY,INTRADAY,MCX,Commodity,100,20.00,2000.00,Traded",
    f"2020-03-03,10:00:00,{NAME},SELL,INTRADAY,MCX,Commodity,100,15.00,1500.00,Traded",
]).encode() + b"\n"
FULL = b"Date,Total Charges\n2020-03-02,50.50\n2020-03-03,60.25\n"
PART = b"Date,Total Charges\n2020-03-02,50.50\n"
GROSS_LINE = "every rupee figure below is gross"
NEW_COPY = ("Before charges", "broker's file", "Add charges", "Net:", "Net of those")
REPORT = ("/mirror", "/mirror/chapter/1", "/mirror/chapter/4", "/mirror/fact/strike",
          "/mirror/fact/money", "/mirror/fact/risk")


def words(html: str) -> str:
    html = re.sub(r"<(script|style|svg)\b.*?</\1>", " ", html, flags=re.DOTALL)
    html = re.sub(r"</?(span|a)\b[^>]*>", "", html)  # inline: no gap in the sentence
    return " ".join(re.sub(r"<[^>]+>", " ", html).split())


@pytest.fixture()
def client(engine):  # noqa: F811
    c = sign_up(TestClient(create_app()), engine, "C-1", "charges")
    assert upload(c, content=FILE).status_code in (302, 303)
    return c


def import_id(engine) -> int:  # noqa: F811
    with make_session(engine) as sess:
        return sess.scalars(select(m.Import)).one().id


def step(engine) -> str:  # noqa: F811
    return f"/imports/{import_id(engine)}/charges"


def post_file(client, engine, content: bytes, name="charges.csv"):  # noqa: F811
    url = step(engine)
    csrf = CSRF.search(client.get("/upload").text).group(1)  # the closed step has no form
    return client.post(url, files={"file": (name, content, "text/csv")},
                       data={"csrf_token": csrf}, follow_redirects=False)


def production(client):
    client.app.state.settings = replace(client.app.state.settings, production=True)


# ---- after upload there is an optional step


def test_what_we_read_offers_the_step(client, engine):  # noqa: F811
    page = client.get(f"/imports/{import_id(engine)}").text
    assert f'href="{step(engine)}"' in page
    assert "Add charges" in page


def test_the_step_shows_the_result_it_would_take_charges_off(client, engine):  # noqa: F811
    page = words(client.get(step(engine)).text)
    assert "−₹300" in page
    assert "Before charges" in page


def test_the_step_takes_a_file_and_can_be_skipped(client, engine):  # noqa: F811
    page = client.get(step(engine)).text
    assert 'type="file"' in page
    assert 'href="/guess"' in page
    assert "Skip" in page


def test_the_step_asks_for_no_brokerage_plan_and_works_nothing_out(client, engine):  # noqa: F811
    """The ruling: a record, not a calculation. No turnover sum, no rate, no plan."""
    page = words(client.get(step(engine)).text)
    for word in ("turnover", "Statutory", "brokerage plan", "estimate"):
        assert word not in page


def test_the_step_is_his_own(client, engine):  # noqa: F811
    url = step(engine)
    other = sign_up(TestClient(create_app()), engine, "C-2", "someone-else")
    assert other.get(url).status_code == 404
    csrf = CSRF.search(other.get("/upload").text).group(1)
    posted = other.post(url, files={"file": ("c.csv", FULL, "text/csv")},
                        data={"csrf_token": csrf}, follow_redirects=False)
    assert posted.status_code == 404
    with make_session(engine) as sess:
        assert sess.scalars(select(m.ChargeStatement)).first() is None


def test_the_step_needs_a_sign_in(engine, client):  # noqa: F811
    url = step(engine)
    assert TestClient(create_app()).get(url, follow_redirects=False).status_code in (302, 303)


def test_a_file_needs_the_form_token(client, engine):  # noqa: F811
    posted = client.post(step(engine), files={"file": ("c.csv", FULL, "text/csv")},
                         follow_redirects=False)
    assert posted.status_code == 403


# ---- a trader who skips sees what he sees today


def test_a_trader_who_skips_sees_the_report_as_it_was(client, engine):  # noqa: F811
    client.get(step(engine))  # looked at the step, added nothing
    for url in REPORT:
        page = client.get(url).text
        for copy in NEW_COPY:
            assert copy not in words(page), (url, copy)
        assert GROSS_LINE in page, url


# ---- net = gross - the broker's charges, labelled, beside the result


def test_net_is_gross_less_the_charges_in_the_file(client, engine):  # noqa: F811
    assert post_file(client, engine, FULL).status_code == 303
    page = words(client.get("/mirror").text)
    assert "Before charges: −₹300." in page
    assert "Less charges from your broker's file: ₹110." in page
    assert "Net: −₹410." in page


def test_the_sum_keeps_its_paise_until_it_is_shown(client, engine):  # noqa: F811
    post_file(client, engine, FULL)
    with make_session(engine) as sess:
        trader = sess.scalars(select(m.Trader)).one()
        view = record.build(sess, trader, sess.scalars(select(m.Import)).one())
    assert view.charges == D("110.75")
    assert view.net == D("-410.75")


def test_the_line_sits_above_the_rest_of_home(client, engine):  # noqa: F811
    post_file(client, engine, FULL)
    page = words(client.get("/mirror").text)
    assert page.index("Before charges") < page.index("Counted from your file")


def test_a_file_for_some_days_says_how_many_it_covers(client, engine):  # noqa: F811
    """-300 - 50.50 = -350.50, and it does not read as his whole net."""
    post_file(client, engine, PART)
    page = words(client.get("/mirror").text)
    # Not "trading days": home counts days a trade opened, and one screen has one count.
    assert "Less charges from your broker's file: ₹50, for 1 of the 2 days in your upload." in page
    assert "Net of those: −₹350." in page
    assert "Net:" not in page


def test_a_day_with_no_trade_in_this_upload_is_not_counted(client, engine):  # noqa: F811
    post_file(client, engine, FULL + b"2019-01-01,70.00\n")
    page = words(client.get("/mirror").text)
    assert "₹110." in page
    assert "1 day in your broker's file has no trade in this upload and is not counted." in page


def test_a_file_that_shares_no_day_with_the_upload_is_refused(client, engine):  # noqa: F811
    assert post_file(client, engine, b"Date,Total Charges\n2019-01-01,70.00\n").status_code == 400
    with make_session(engine) as sess:
        assert sess.scalars(select(m.ChargeStatement)).first() is None


def test_a_later_file_replaces_a_day_and_the_first_stays_on_record(client, engine):  # noqa: F811
    post_file(client, engine, PART)
    post_file(client, engine, b"Date,Total Charges\n2020-03-02,20.00\n")
    assert "₹20, for 1 of the 2" in words(client.get("/mirror").text)
    with make_session(engine) as sess:
        assert len(sess.scalars(select(m.ChargeStatement)).all()) == 2


# ---- what the file said stays what the file said


def test_the_trips_and_the_import_are_not_rewritten(client, engine):  # noqa: F811
    with make_session(engine) as sess:
        before = [(t.gross, t.fees, t.net, t.fees_available) for t in sess.scalars(select(m.Trip))]
    post_file(client, engine, FULL)
    client.get("/mirror")
    with make_session(engine) as sess:
        after = [(t.gross, t.fees, t.net, t.fees_available) for t in sess.scalars(select(m.Trip))]
        assert sess.scalars(select(m.Import)).one().fees_available is False
    assert after == before
    assert all(fees == 0 and not available for _g, fees, _n, available in after)


@pytest.mark.parametrize("url", ["/mirror/chapter/1", "/mirror/chapter/4", "/mirror/fact/strike",
                                 "/mirror/fact/money", "/mirror/fact/run", "/mirror/fact/unread",
                                 "/mirror/fact/worst-days", "/mirror/fact/risk"])
def test_every_other_page_is_unchanged_and_still_truly_gross(client, engine, url):  # noqa: F811
    """One line, not fed through: strike rate and break-even read the tradebook's result."""
    def page():
        return re.sub(r'value="[^"]{20,}"', "", client.get(url).text)

    before = page()
    post_file(client, engine, FULL)
    assert page() == before


def test_the_gross_line_stays_on_home_below_the_net_line(client, engine):  # noqa: F811
    """Everything under it is still gross, and the frozen sentence says only that."""
    post_file(client, engine, FULL)
    page = client.get("/mirror").text
    assert page.index("broker's file") < page.index(GROSS_LINE)


# ---- the file itself


def test_the_file_is_kept_encrypted_as_his(client, engine):  # noqa: F811
    post_file(client, engine, PART)
    with make_session(engine) as sess:
        stored = sess.scalars(select(m.ChargeStatement)).one()
        raw = sess.get(m.RawFile, stored.raw_file_id)
        assert b"Total Charges" not in Path(raw.stored_path).read_bytes()


@pytest.mark.parametrize("content", [
    b"Something,Else\n1,2\n",
    b"Date,Total Charges\n",
    b"Date,Total Charges\nnot-a-date,5\n",
    b"Date,Total Charges\n2020-03-02,lots\n",
    b"Date,Total Charges\n2020-03-02,-5\n",
    b"Date,Total Charges\n2020-03-02,NaN\n",
    b"Date,Total Charges\n2020-03-02,5\n2020-03-02,6\n",
    b"Date,Total Charges\n2020-03-02\n",
    b"%PDF-1.7 \xff\xfe binary",
])
def test_a_file_we_cannot_read_is_refused_and_not_kept(client, engine, content):  # noqa: F811
    assert post_file(client, engine, content).status_code == 400
    with make_session(engine) as sess:
        assert sess.scalars(select(m.ChargeStatement)).first() is None
        assert len(sess.scalars(select(m.RawFile)).all()) == 1  # the tradebook alone


def test_the_same_file_twice_is_refused(client, engine):  # noqa: F811
    post_file(client, engine, PART)
    assert post_file(client, engine, PART).status_code == 400


# ---- nobody has checked the shape against a real file, so production does not take it


def test_in_production_the_upload_is_closed_and_stores_nothing(client, engine):  # noqa: F811
    production(client)
    page = client.get(step(engine)).text
    assert 'type="file"' not in page
    assert post_file(client, engine, PART).status_code == 503
    with make_session(engine) as sess:
        assert sess.scalars(select(m.ChargeStatement)).first() is None


def test_in_production_what_we_read_does_not_offer_a_closed_step(client, engine):  # noqa: F811
    production(client)
    assert "Add charges" not in client.get(f"/imports/{import_id(engine)}").text
