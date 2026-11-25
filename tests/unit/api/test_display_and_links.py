"""TICKET-1027: small display and link fixes, one test per item of the checklist.

Every record here is the demo file or made up for the test; no trader's figures.
"""
from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from html import unescape
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from services.production.api.app import create_app
from services.production.db import models as m
from services.production.db.session import make_session
from services.production.mirror import loader
from services.production.mirror import metrics as mx
from services.shared.schemas import scope_v1 as s
from tests.unit.api import figure_pages as P

IST = ZoneInfo("Asia/Kolkata")
HREF = re.compile(r'href="([^"#]+)')


def text(html: str) -> str:
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", html)))


@pytest.fixture()
def app():
    return create_app()


@pytest.fixture()
def demo(app):
    client = TestClient(app)
    P._sign_up(client, app.state.engine, "visitor")
    P._consent(client)
    client.post("/upload/demo", data={"csrf_token": P._token(client, "/upload")}, follow_redirects=False)
    return client


def demo_trips(app):
    with make_session(app.state.engine) as sess:
        trader = sess.scalars(select(m.Trader).where(m.Trader.login_id == "visitor")).one()
        return loader.load_for(sess, trader)


# ---------- 1, 2. every link on every sample page opens; the sample has no Journal links ----------

def test_every_link_on_every_sample_page_opens(app):
    client = TestClient(app)
    seen, queue, bad, journal_links = set(), ["/sample"], [], []
    while queue:
        path = queue.pop(0)
        if path in seen:
            continue
        seen.add(path)
        r = client.get(path)
        if r.status_code != 200:
            bad.append((path, r.status_code))
            continue
        for href in HREF.findall(r.text):
            href = unescape(href)
            if re.match(r"/journals/\d", href):  # one of his Journals; the nav's tab is every page's
                journal_links.append((path, href))
            if href.startswith("/sample") and href.split("?")[0] not in seen:
                queue.append(href.split("#")[0])
    assert any(p.startswith("/sample/day/") for p in seen), "no sample day page was reached"
    assert bad == []
    assert journal_links == []  # a visitor has no Journal to open


# ---------- 3. one trade, not "1 trades" ----------

def test_the_report_card_says_one_trade(demo):
    home = text(demo.get("/").text)
    assert not re.search(r"\b1 trades", home)
    assert re.search(r"Stocks, ETFs and futures \+₹[\d,]+ · 1 trade\b", home)


# ---------- 4, 5, 6. Home's card ----------

def test_the_month_view_names_its_months(app, demo):
    from services.production.api import how_you_got_here as HY
    trips, imp = demo_trips(app)
    svg = str(HY.build(trips, imp, None, "m")["chart"])
    labels = re.findall(r'class="hy-axis hy-axis--x"[^>]*>([^<]+)<', svg)
    assert "Jul" in labels and "Aug" in labels, labels


def _ys(svg: str, cls: str) -> list[float]:
    return [float(y) for y in re.findall(rf'<text[^>]*y="([\d.]+)"[^>]*class="{cls}"', svg)]


@pytest.mark.parametrize("book,tf", [(None, "m"), (None, "w"), (None, "d"), ("crude-options", "m"),
                                     ("nifty-options", "m"), ("crude-options", "w")])
def test_the_last_value_tag_never_sits_on_an_axis_label(app, demo, book, tf):
    from services.production.api import how_you_got_here as HY
    trips, imp = demo_trips(app)
    svg = str(HY.build(trips, imp, book, tf)["chart"])
    last = _ys(svg, "hy-last-text")
    assert last, "no last-value tag"
    axis = [float(y) for y, label in re.findall(r'<text x="[\d.]+" y="([\d.]+)" class="hy-axis">([^<]+)</text>', svg)
            if "₹" in label]  # the rupee labels up the side; the trade count and 0 sit below the chart
    assert all(abs(a - last[0]) >= 16 for a in axis), (last, axis)  # the tag's box is about 16 px tall


def trip(tid: str, day: str, net: str = "100") -> mx.Trip:
    entry = datetime.fromisoformat(f"{day}T10:00").replace(tzinfo=IST)
    return mx.Trip(trip_id=tid, symbol="NIFTY", trading_day=day, entry_ts=entry,
                   exit_ts=entry + timedelta(minutes=10), holding_seconds=600, net=Decimal(net), lots=1,
                   risk_unit_source=s.RiskUnitSourceV1.PREMIUM_PAID, is_option=True,
                   lines=(mx.TradeLine("NIFTY", "OPT", "Buy", 1, None, None, Decimal(net)),))


def test_the_card_describes_the_latest_period_with_his_usual_trading():
    """Months with 10, 10 and 1 trades: his median month is 10, so the latest month with at least
    10 trades (February) is the one the card describes, and it says so."""
    from services.production.api import how_you_got_here as HY
    trips = ([trip(f"j{i}", f"2026-01-{5 + i:02d}") for i in range(10)]
             + [trip(f"f{i}", f"2026-02-{2 + i:02d}") for i in range(10)] + [trip("m0", "2026-03-02")])
    view = HY.build(trips, None, None, "m")
    assert view["last_label"] == "Feb 2026"
    assert view["last_words"] == "the latest month with your usual number of trades"
    assert view["last"].trades == 10


def test_a_full_latest_period_keeps_its_own_words():
    from services.production.api import how_you_got_here as HY
    trips = [trip(f"j{i}", f"2026-01-{5 + i:02d}") for i in range(5)] + [trip(f"f{i}", f"2026-02-{2 + i:02d}") for i in range(5)]
    view = HY.build(trips, None, None, "m")
    assert view["last_label"] == "Feb 2026" and view["last_words"] == "the last month"


def test_the_trade_count_label_ends_inside_the_chart(app, demo):
    from services.production.api import how_you_got_here as HY
    trips, imp = demo_trips(app)
    svg = str(HY.build(trips, imp, None, "w")["chart"])
    label = re.search(r'<text x="([\d.]+)" y="[\d.]+" class="hy-axis"( text-anchor="end")?>[\d,]+ trades?</text>', svg)
    assert label and label.group(2), "the count label must end at the chart's edge"
    assert float(label.group(1)) <= HY.W


# ---------- 7. dial wedges clear on the demo's own figures ----------

FIT = -13


@pytest.mark.parametrize("size", ["phone", "desktop"])
def test_every_chapter_dial_clears_on_the_demo_figures(app, demo, size):
    from services.production.api import scope_facts as SF
    from services.production.api import scope_geometry as G
    trips, imp = demo_trips(app)
    figs = SF.facts(SF.record_context(trips), imp)
    z = G.SIZES[size]
    rr = G.radii(z["R"])
    for n in (1, 2, 3, 4):
        view = SF.chapter_view(n, figs)
        items = (view.get("desktop_items") or view["items"]) if size == "desktop" else [
            {**i, "figure": i.get("phone_figure", i["figure"]), "label": i.get("phone_label", i.get("label", ""))}
            for i in view["items"]]
        from services.production.api import dial as D  # a mini as wide as its wedge clears, either size
        items = D.fitted(items, z["figSizesChapter"], size)
        sec = G.sectors(len(items), False)
        lay = G.layout_contents(items, sec, rr, z["figSizesChapter"])
        for i, block in enumerate(lay["blocks"]):
            if items[i]["figure"] == "—":  # a state's dash has no words to run into the ring
                continue
            clear = G.block_clearance(sec["slices"][i], sec["span"], lay["radius"][i], block, rr)
            assert clear >= FIT, (n, size, items[i]["figure"], clear)


# ---------- 8. chapter 1's money card ----------

def test_a_signed_figure_never_wraps_from_its_sign(demo):
    html = demo.get("/mirror/chapter/1").text
    found = re.search(r"Your best five trades came to (.*?)\. Your worst", html, re.DOTALL)
    assert found and 'class="nowrap"' in found.group(1)


def test_the_best_and_worst_five_dates_are_grouped_by_their_bars(demo):
    html = demo.get("/mirror/chapter/1").text
    days = re.search(r'<span class="money-days">(.*?)</span></span>', html, re.DOTALL)
    assert days, "no dates on the card"
    words = text(days.group(1))
    assert "Best five:" in words and "Worst five:" in words


# ---------- 9. the Journal list ----------

def test_the_journal_list_never_shows_a_version_number():
    from types import SimpleNamespace

    from services.production.api.app import TEMPLATES
    journal = SimpleNamespace(id=7, period_start="2026-07-30", period_end="2026-07-30", version_no=3, opened_at=None)
    html = TEMPLATES.env.get_template("_journal_index.html").render(latest=[journal], changed_ids={7}, reasons={})
    assert not re.search(r"version\s*\d", text(html)), text(html)
    assert "updated" in text(html)


# ---------- 10. the day page header ----------

def test_a_day_page_names_its_day_once(demo):
    html = demo.get("/mirror/day/2026-07-30").text
    assert "every one of them" not in html
    assert "Day 1 ·" not in text(html)


# ---------- 11. the consent ledger ----------

def test_the_ledger_says_current_or_earlier_wording_not_a_version(app, demo):
    from services.production.accounts import consent as cs
    with make_session(app.state.engine) as sess:
        trader = sess.scalars(select(m.Trader).where(m.Trader.login_id == "visitor")).one()
        sess.add(m.ConsentEvent(trader_id=trader.id, purpose=s.ConsentPurpose.DIAGNOSIS, scope="all",
                                granted=True, terms_version="0-draft", at=datetime(2026, 1, 2, tzinfo=UTC),
                                method="checkbox", wording_shown="an earlier wording"))
        sess.commit()
    page = text(demo.get("/settings/consent").text)
    assert "0-draft" not in page and not re.search(r"version \S+", page)
    assert "earlier wording" in page and "current wording" in page
    assert cs.CURRENT.version != "0-draft"


# ---------- 12. what moved, by book ----------

def test_what_moved_has_no_other_trades_row():
    import inspect

    from services.production.api import routes_upload
    assert '"Other trades"' not in inspect.getsource(routes_upload._what_moved)


# ---------- 13. the factor map answers once ----------

def test_a_factor_in_his_file_is_never_not_in_his_file():
    from services.production.api import factor_map as FM
    factor = next(f for f in FM.FACTORS if f.name == "Where your results come from, cell by cell")
    got = FM.in_file(factor, enough=frozenset(), short=frozenset(), fact_states={},
                     filters_seen=frozenset(), has_charges=False)
    assert got is FM.InFile.YES


# ---------- 14. no placeholder guess ----------

def test_the_guess_is_never_asked_with_placeholder_labels(demo):
    from services.production.mirror import guess as GU
    assert getattr(GU, "PLACEHOLDER", None) is True, "guess has no PLACEHOLDER flag"
    assert not GU.ready(production=False)
    r = demo.get("/guess", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/mirror/reveal"
    assert "[guess" not in demo.get("/mirror/reveal").text


# ---------- review (24 Nov): line 5's rule, line 12's rows, line 14's stored guess ----------

def test_a_latest_month_a_little_under_his_usual_is_still_the_one_described():
    """Months of 10, 10 and 8 trades: 8 is under his median month (10) but not "almost nothing",
    so the card keeps the latest month and its own words. The old rule moved off it."""
    from services.production.api import how_you_got_here as HY
    trips = ([trip(f"j{i}", f"2026-01-{5 + i:02d}") for i in range(10)]
             + [trip(f"f{i}", f"2026-02-{2 + i:02d}") for i in range(10)]
             + [trip(f"m{i}", f"2026-03-{2 + i:02d}") for i in range(8)])
    view = HY.build(trips, None, None, "m")
    assert view["last_label"] == "Mar 2026"
    assert view["last"].trades == 8


def test_a_latest_month_with_almost_nothing_moves_to_the_last_month_of_trading():
    """Almost nothing, ruled 24 Nov: under a quarter of his median month. 10, 10, 2: 2 < 2.5."""
    from services.production.api import how_you_got_here as HY
    trips = ([trip(f"j{i}", f"2026-01-{5 + i:02d}") for i in range(10)]
             + [trip(f"f{i}", f"2026-02-{2 + i:02d}") for i in range(10)]
             + [trip(f"m{i}", f"2026-03-{2 + i:02d}") for i in range(2)])
    assert HY.build(trips, None, None, "m")["last_label"] == "Feb 2026"


def test_what_moved_labels_each_row_by_its_own_book_and_never_a_total_beside_it():
    from services.production.api import routes_upload
    headline = getattr(routes_upload, "_headline_figures", None)
    assert headline is not None, "no _headline_figures(trips) to read the rows from"
    rows = headline([trip("a", "2026-01-05", "300"), trip("b", "2026-01-06", "-500")])
    assert "Option trades" not in rows
    books = mx.verdict([trip("a", "2026-01-05", "300"), trip("b", "2026-01-06", "-500")]).books
    assert [label for label in rows if label != "Your five worst days"] == [b.label for b in books]


def test_a_stored_placeholder_guess_is_never_printed_on_the_reveal(app, demo):
    from services.production.mirror import guess as GU
    with make_session(app.state.engine) as sess:
        trader = sess.scalars(select(m.Trader).where(m.Trader.login_id == "visitor")).one()
        imp = sess.scalars(select(m.Import).where(m.Import.trader_id == trader.id)).first()
        GU.record(sess, trader=trader, answer="option-3", import_id=imp.id)
        sess.commit()
    html = demo.get("/mirror/reveal").text
    assert "[guess" not in html and "TR-009" not in html
