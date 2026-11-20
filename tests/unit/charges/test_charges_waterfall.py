"""TICKET-995: where the money went, from what his trades made, through each charge, to what he kept.

Every trade here is made up. The pipeline is given a ``ChargesInput`` directly, as no upload
passes one in yet. Each expected figure is worked by hand from the rate rows and the broker's
plan, as 912's own tests work them (tests/unit/charges/test_charges_at_import.py):

One WIDGETOIL option trade, 100 bought at 52.00 and sold at 57.00 on any day from 1 Oct 2024
(MCX_OPT rows 36/40 exchange 0.000418, 53 CTT sell 0.0005, 61 stamp buy 0.00003, 76/77 SEBI
0.000001, 92/93 GST 0.18; Dhan Rs 20 an order):
    Brokerage 2 x 20                                   40
    CTT       0.0005 x 5,700                            2.85
    Exchange  0.000418 x (5,200 + 5,700)                4.5562
    SEBI fee  0.000001 x (5,200 + 5,700)                0.0109
    Stamp     0.00003 x 5,200                           0.156
    GST       0.18 x (40 + 4.5562 + 0.0109)             8.022078
    Total                                              55.595178   (912's figure)
Gross 500 a trade. The same trade on 30 Sep 2024 is before the rate table: not priced.
"""
from __future__ import annotations

import importlib
import importlib.resources
import importlib.util
import re
from decimal import Decimal as D

import pytest
from sqlalchemy import select

from services.production.ctr.intake import persist
from services.production.ctr.intake import pipeline as pl
from services.production.db import models as m
from services.production.db.session import make_session
from tests.helpers.upload import upload_client, upload_engine

DHAN = "Date,Time,Name,Buy/Sell,Order,Exchange,Segment,Quantity/Lot,Trade Price,Trade Value,Status"
CONTRACT = "WIDGETOIL 17 OCT 6950 CALL"
ONE = {"BROKERAGE": D(40), "CTT": D("2.85"), "EXCHANGE": D("4.5562"), "SEBI": D("0.0109"),
       "STAMP": D("0.156"), "GST": D("8.022078")}
CHARGED = D("55.595178")


def waterfall():
    assert importlib.util.find_spec("services.production.charges.waterfall"), \
        "no services/production/charges/waterfall.py"
    return importlib.import_module("services.production.charges.waterfall")


def table():
    assert hasattr(m, "TripCharge"), "no trip_charge table in models"
    return table()


def trade(day: str, sold: str = "57.00", at: str = "10") -> list[str]:
    value = D(sold) * 100
    return [f"{day},{at}:00:00,{CONTRACT},BUY,INTRADAY,MCX,Commodity,100,52.00,5200.00,Traded",
            f"{day},{at}:30:00,{CONTRACT},SELL,INTRADAY,MCX,Commodity,100,{sold},{value:.2f},Traded"]


def dhan(*days: str, sold: str = "57.00") -> str:
    rows = [r for d in days for r in trade(d, sold)]
    return "\n".join([DHAN, *rows]) + "\n"


def plan(text: str, charges: pl.ChargesInput | None) -> pl.ImportPlan:
    return pl.plan_import(text, context=pl.ImportContext(
        trader_id="t", source_account="A", code_version="test", charges=charges))


@pytest.fixture()
def engine():
    return upload_engine()


@pytest.fixture()
def client(engine):
    return upload_client(engine)


def store(engine, text: str, charges: pl.ChargesInput | None, sha: str = "a") -> int:
    with make_session(engine) as sess:
        trader = sess.scalars(select(m.Trader)).first()
        imp = persist.write_plan(sess, trader=trader, plan=plan(text, charges), raw_sha256=sha * 64,
                                 original_name="made-up.csv", stored_path="x", size=len(text))
        sess.commit()
        return imp.id


def page(client) -> str:
    return client.get("/mirror/fact/charges").text


# ---------- 1. what was computed is stored ----------

def test_each_trade_s_source_and_components_are_stored_as_decimal_text(client, engine):
    imp_id = store(engine, dhan("2024-09-30", "2024-10-01"), pl.ChargesInput())
    with make_session(engine) as sess:
        rows = sess.scalars(select(table()).where(table().import_id == imp_id)).all()
        by_source = {}
        for r in rows:
            by_source.setdefault(r.source, []).append(r)
    assert {r.component: r.amount for r in by_source["calculated"]} == ONE
    assert all(isinstance(r.amount, D) for r in by_source["calculated"])
    assert [(r.component, r.amount) for r in by_source["not_priced"]] == [(None, None)]


def test_the_table_is_insert_only():
    assert issubclass(table(), m._InsertOnly)


# ---------- 2. where it sits ----------

def test_it_is_chapter_one_after_where_the_money_came_from():
    from services.production.api import scope_map as S
    keys = [f.key for f in S.chapter(1).facts]
    assert "charges" in keys, keys
    assert keys.index("charges") == keys.index("money") + 1
    assert S.FACTS["charges"].title == "Where the money went"


# ---------- 3, 4. each source lands where the ticket says; the steps add up exactly ----------

def test_calculated_trades_step_down_by_each_component_largest_first(client, engine):
    store(engine, dhan("2024-09-30", "2024-10-01", "2024-10-02"), pl.ChargesInput())
    html = page(client)
    names = re.findall(r'class="wf-step__name">([^<]+)<', html)
    assert names == ["Brokerage", "GST", "Exchange transaction charges", "CTT", "Stamp duty",
                     "SEBI fee"]
    assert "Before charges" in html and "After charges" in html


def test_the_steps_add_up_exactly_in_decimals(client, engine):
    imp_id = store(engine, dhan("2024-09-30", "2024-10-01", "2024-10-02"), pl.ChargesInput())
    wf = waterfall()
    with make_session(engine) as sess:
        trader = sess.scalars(select(m.Trader)).first()
        imp = sess.get(m.Import, imp_id)
        from services.production.mirror import loader
        trips, _ = loader.load_for(sess, trader, imp)
        got = wf.build(wf.load(sess, trader, imp), trips)
    assert got.before == D(1000)                       # two priced trades, 500 each
    assert {s.key: s.amount for s in got.steps} == {k: 2 * v for k, v in ONE.items()}
    # Exact in Decimals: a page rounds each figure to the rupee, so a shown sum can be 1 off.
    assert got.before - sum((s.amount for s in got.steps), D(0)) == got.after
    assert got.after == D(1000) - 2 * CHARGED
    assert got.left_out == 1 and len(got.included) == 2


def test_a_trade_before_the_rate_table_is_left_out_and_counted(client, engine):
    store(engine, dhan("2024-09-30", "2024-10-01"), pl.ChargesInput())
    html = page(client)
    assert "1 trade is not in this: its result is before charges." in re.sub(r"<[^>]+>", "", html)


def test_an_old_import_with_the_tradebook_s_charges_is_one_tradebook_step(client, engine):
    imp_id = store(engine, dhan("2025-10-01", "2025-10-02"), None)
    with make_session(engine) as sess:  # an import stored before this ticket: no source rows,
        for r in sess.scalars(select(table()).where(table().import_id == imp_id)):
            sess.delete(r)                # and its file carried its own charges
        sess.flush()
        sess.execute(m.Import.__table__.update().where(m.Import.id == imp_id)
                     .values(fees_available=True))
        sess.execute(m.Trip.__table__.update().where(m.Trip.import_id == imp_id)
                     .values(fees=D(30), net=D(470)))
        sess.commit()
    html = page(client)
    assert re.findall(r'class="wf-step__name">([^<]+)<', html) == ["Charges in your tradebook"]


def test_a_charges_file_day_is_one_step_and_after_charges_is_home_s_net(client, engine):
    from services.production.charges import record
    imp_id = store(engine, dhan("2025-10-01", "2025-10-02"), None)
    with make_session(engine) as sess:
        trader = sess.scalars(select(m.Trader)).first()
        imp = sess.get(m.Import, imp_id)
        raw = sess.get(m.RawFile, imp.raw_file_id)
        record.record_statement(sess, trader, raw, "made-up", {"2025-10-01": D("61.25"),
                                                               "2025-10-02": D("58.75")})
        sess.commit()
        home = record.build(sess, trader, imp)
        wf = waterfall()
        from services.production.mirror import loader
        trips, _ = loader.load_for(sess, trader, imp)
        got = wf.build(wf.load(sess, trader, imp), trips)
    assert [s.name for s in got.steps] == ["Charges from your charges file"]
    assert got.steps[0].amount == D(120)
    assert got.after == home.net == D(880)
    assert "Charges from your charges file" in page(client)


# ---------- 5. the jolt line, at 30 included trades ----------

def _days(n: int) -> list[str]:
    from datetime import date, timedelta
    return [(date(2025, 1, 1) + timedelta(days=i)).isoformat() for i in range(n)]


def _mixed(n: int) -> str:
    """n trades a day apart, every third a loser (sold at 47.00), so there is an average winner."""
    rows = []
    for i, d in enumerate(_days(n)):
        rows += trade(d, "47.00" if i % 3 == 0 else "57.00")
    return "\n".join([DHAN, *rows]) + "\n"


def test_the_jolt_line_shows_at_thirty_trades(client, engine):
    store(engine, _mixed(30), pl.ChargesInput())
    text = re.sub(r"<[^>]+>", "", page(client))
    assert "Your average winner is" in text and "Each trade pays" in text and "in charges." in text


def test_the_jolt_line_does_not_show_at_twenty_nine(client, engine):
    store(engine, _mixed(29), pl.ChargesInput())
    text = re.sub(r"<[^>]+>", "", page(client))
    assert "Each trade pays" not in text
    assert "Before charges" in text  # the chart still shows


# ---------- 6. a step opens its trades; 7. no would-have figure ----------

def test_each_step_opens_the_trades_it_was_charged_on(client, engine):
    store(engine, dhan("2024-09-30", "2024-10-01", "2024-10-02"), pl.ChargesInput())
    html = page(client)
    links = re.findall(r'href="(/mirror/fact/charges/trades\?charge=[A-Z_a-z]+)"', html)
    assert "/mirror/fact/charges/trades?charge=BROKERAGE" in links
    listed = client.get("/mirror/fact/charges/trades?charge=CTT").text
    assert listed.count('<article class="trade">') == 2
    from services.production.api import trade_list as TL
    assert "charges" in TL.FACTS_WITH_TRADES


def test_nothing_says_what_he_would_have_made():
    tpl = importlib.resources.files("services.production.api") / "templates/scope/facts/charges.html"
    assert tpl.is_file(), "no charges.html"
    words = tpl.read_text(encoding="utf-8").lower()
    for claim in ("would have", "without charges", "saved", "could have"):
        assert claim not in words, claim


def test_no_script_on_the_page(client, engine):
    store(engine, dhan("2024-10-01"), pl.ChargesInput())
    body = page(client).split("<main", 1)[1].split("</main>", 1)[0]
    assert "<script" not in body


# ---------- 9. deletion reaches the new rows ----------

def test_deleting_the_trader_removes_the_new_rows(client, engine, tmp_path):
    from services.production.accounts import deletion
    from services.production.accounts.file_store import FileStore, generate_key
    store(engine, dhan("2024-10-01"), pl.ChargesInput())
    with make_session(engine) as sess:
        trader = sess.scalars(select(m.Trader)).first()
        assert sess.scalars(select(table())).first() is not None
        deletion.delete_trader(sess, FileStore(tmp_path / "f", generate_key()), trader=trader)
        sess.commit()
        assert sess.scalars(select(table())).first() is None
