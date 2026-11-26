"""TICKET-919: the hiding page prints both figures, and the chance line when it applies.

Pins the gate and the founder's ruling of 16 Nov 2026 (919 Q1: a; in Jira, not repeated here):

* One factor, previous result: the most recent same-day trade exited before this entry, the
  way b2_condition resolves its priors. Won or lost on its result before charges (founder, 24 Nov
  2026, TICKET-919); a level one is neither. Every summed figure stays net.
* Per book, on same-day trades. Until TICKET-918 the prior is read across books, as one argument.
* On the record: the net of every trade after a win, and of every trade after a loss.
* With only what was known then: in entry order, a trade counts when its state's earlier trades
  in its book, exited before its entry, number THEN_MINIMUM or more and are down overall.
  THEN_MINIMUM is the framework's minimum of 30; using it here is new, so it is arbitrary.
* Both figures are set against random sets of the same number of the book's trades that have a
  previous result (spec 5.4, N-C), b2_shuffle's draws and seed, the middle 95%, ends included.
* A figure inside its band ships with the chance line; the line cannot be written without the
  band that justifies it (gate 2). Both figures carry 917's labels and open their trades.
  Nothing here is called a finding, saved, avoided, a cost or kept.

Every expected value is worked by hand from the invented book below or from the 40-trip
fixture's trips. No trader data is in this file.
"""

from __future__ import annotations

import importlib
import re
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from html.parser import HTMLParser
from pathlib import Path

import pytest
from markupsafe import escape
from sqlalchemy import select

from services.production.api import findings as F
from services.production.api import formatting
from services.production.api import scope_facts as SF
from services.production.api import scope_map as S
from services.production.api import trade_list as TL
from services.production.db import models as m
from services.production.db.session import make_session
from services.production.mirror import loader
from services.production.mirror import metrics as mx
from services.shared.conditions import b2_shuffle
from services.shared.conditions.b2_condition import Obs
from services.shared.schemas import scope_v1 as s

IST = timezone(timedelta(hours=5, minutes=30))
OIL = "WIDGETOIL options"
CHANCE = "Can't be told apart from chance."
RECORD, THEN = "On your record:", "Choosing with only what you knew then:"
HIDDEN = Path("services/production/api/templates/scope/facts/hidden.html")


def _module(name: str):
    try:
        return importlib.import_module(name)
    except ModuleNotFoundError:
        pytest.fail(f"{name} is not built yet (TICKET-919)")


def _built(obj, name: str):
    if not hasattr(obj, name):
        pytest.fail(f"{getattr(obj, '__name__', obj)}.{name} is not built yet (TICKET-919)")
    return getattr(obj, name)


def trip(i: int, day: str, net: int, symbol: str = "WIDGETOIL", minute: int = 0,
         length: int = 5) -> mx.Trip:
    entry = datetime.fromisoformat(day).replace(hour=10, minute=minute, tzinfo=IST)
    leave = entry + timedelta(minutes=length)
    return mx.Trip(f"T{i}", symbol, day, entry, leave, int((leave - entry).total_seconds()),
                   Decimal(net), 1, s.RiskUnitSourceV1.PREMIUM_PAID)


# Every trade closes the day it opens. Previous result: the last trade that day exited before
# this entry, in any book until TICKET-918.
#   day         10:00 (5 min)        10:10 (5 min)   its previous result
#   2026-01-05  T1  +100             T2  -40         T2 after a win
#   2026-01-06  T3  +100             T4  -60         T4 after a win
#   2026-01-07  T5  +100             T6 +200         T6 after a win
#   2026-01-08  T7  +100             T8  -10         T8 after a win
#   2026-01-09  T9  +100             T10  -5         T10 after a win
#   2026-01-12  T11 -100 (30 min)    T12 -30         none: T11 is still open at 10:10
#   2026-01-13  T13 +50 WIDGETIDX    T14 -20         T14 after a win, read across books
#   2026-01-14  T15 -100             T16 +40         T16 after a loss
# On the record, after a win: T2 T4 T6 T8 T10 T14 = -40 -60 +200 -10 -5 -20 = +65 on 6 trades.
#   After a loss: T16 = +40 on 1 trade. Without reading across books, T14 has none: +85 on 5.
# With only what was known then, at a minimum of 2 (earlier trades after a win, all exited):
#   T2: 0 earlier, no. T4: 1, no. T6: 2 at -100, yes. T8: 3 at +100, no. T10: 4 at +90, no.
#   T14: 5 at +85, no. So T6 alone: +200 on 1 trade. T16 has none before it: never reached.
# The pool both bands draw from: WIDGETOIL's trades with a previous result, T2 T4 T6 T8 T10
#   T14 T16: -40 -60 +200 -10 -5 -20 +40, total +105.
#   6 of the 7: 105 less the one left out: 145 165 -95 115 110 125 65, each 1 time in 7, so the
#   middle 95% runs lowest to highest: (-95, +165), and +65 is inside.
#   1 of the 7: each net 1 time in 7: (-60, +200), and +200 (the end) and +40 are inside.
BOOK = [
    trip(1, "2026-01-05", 100), trip(2, "2026-01-05", -40, minute=10),
    trip(3, "2026-01-06", 100), trip(4, "2026-01-06", -60, minute=10),
    trip(5, "2026-01-07", 100), trip(6, "2026-01-07", 200, minute=10),
    trip(7, "2026-01-08", 100), trip(8, "2026-01-08", -10, minute=10),
    trip(9, "2026-01-09", 100), trip(10, "2026-01-09", -5, minute=10),
    trip(11, "2026-01-12", -100, length=30), trip(12, "2026-01-12", -30, minute=10),
    trip(13, "2026-01-13", 50, symbol="WIDGETIDX"), trip(14, "2026-01-13", -20, minute=10),
    trip(15, "2026-01-14", -100), trip(16, "2026-01-14", 40, minute=10),
]

# The 40-trip fixture: one book, WIDGETOIL options, every trade closed the day it opened.
#   no previous result (first of the day, or nothing exited yet):
#     t01 t02 t04 t10 t14 t19 t27 t31 t37
#   after a win: t28 (t27 +1500), t32 (t31 +1000), t36 (t35 +500)
#   level: t12 (t11 0)          after a loss: the other 27
# On the record, after a win: -1000 -500 -1000 = -2,500 on 3 trades. After a loss: t03 -400,
#   2 Sep -7,000, t11 t13 0, 4 Sep -1,500, 7 Sep -11,000, 8 Sep -1,000, 9 Sep -500, 10 Sep -750
#   = -22,150 on 27 trades. At 30, no trade after a loss has more than 26 such trades before
#   it and none after a win more than 2, so neither real-time figure is reached.
POOL = [-400, -1500, -2000, 500, -2000, -2000, 0, -100, 0, -500, 1000, -1000, -1000,
        -1000, -2000, -2000, -2000, -2000, -1000, -1000, -1000, -500, -500, -500, -500, -500,
        500, -1000, -250, -250, -250]
"""The fixture's 31 trades with a previous result, in entry order: what both bands draw from."""


def _rows(trips: list[mx.Trip], **kw) -> dict:
    figures = _built(mx, "previous_result_figures")
    return {(r.book, r.state): r for r in figures(trips, **kw)}


def _view(minimum: int = 2) -> tuple[dict, dict]:
    ctx = SF.record_context(BOOK)
    ctx["previous_result"] = _built(mx, "previous_result_figures")(BOOK, minimum=minimum)
    books = {b["book"]: b for b in SF._hidden_view(ctx)["books"]}
    rows = books[OIL].get("previous")
    if rows is None:
        pytest.fail("the hiding page's book view has no 'previous' rows yet (TICKET-919)")
    return ctx, {p["state"]: p for p in rows}


def _listed(ctx: dict, query: dict) -> set[str]:
    """The trades the list shows: the ones listing hands scope_map.groups to draw."""
    shown: list[mx.Trip] = []
    real = S.groups

    def spy(key, ctx_, only=None):
        shown.extend(only or [])
        return real(key, ctx_, only=only)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(S, "groups", spy)
        listed = TL.listing("hidden", ctx, query, {})
    assert listed["shown"] == len(shown)
    return {t.trip_id for t in shown}


class _Text(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def _text(html: str) -> str:
    parser = _Text()
    parser.feed(html)
    return " ".join("".join(parser.parts).split())


PARA = re.compile(r'<p\b([^>]*\bdata-figure="[^"]+"[^>]*)>(.*?)</p>', re.DOTALL)


def _paras(html: str) -> list[tuple[dict, str]]:
    return [(dict(re.findall(r'(data-[\w-]+)="([^"]*)"', attrs)), _text(body))
            for attrs, body in PARA.findall(html)]


def test_the_previous_result_is_the_last_trade_exited_before_entry_that_day():
    previous_of = _built(_module("services.shared.conditions.previous_result"), "previous_of")
    obs = [Obs(0, 0.0, 10.0, 1.0), Obs(0, 5.0, 8.0, -1.0), Obs(0, 12.0, 20.0, -1.0),
           Obs(0, 10.0, 11.0, 1.0), Obs(1, 1.0, 2.0, 1.0)]
    # 0: nothing before. 1: nothing exited by 5. 2: 0, 1 and 3 exited by 12, 3 last (11).
    # 3: only 1 exited before 10 (0 exits at 10, not before). 4: a new day.
    assert previous_of(obs) == [None, None, 3, 1, None]


def test_the_minimum_is_the_frameworks_and_marked_arbitrary():
    assert _built(mx, "THEN_MINIMUM") == 30 == mx.BOOK_ROW_MINIMUM
    source = Path("services/production/mirror/metrics.py").read_text(encoding="utf-8")
    said = re.search(r'THEN_MINIMUM\s*=.*?\n"""(.*?)"""', source, re.DOTALL)
    assert said and "arbitrary" in said.group(1) and "framework_v1.yaml" in said.group(1)


def test_both_figures_by_hand():
    rows = _rows(BOOK, minimum=2)
    assert set(rows) == {(OIL, "win"), (OIL, "loss")}
    win, loss = rows[(OIL, "win")], rows[(OIL, "loss")]
    assert win.record_ids == ("T2", "T4", "T6", "T8", "T10", "T14")
    assert win.record_net == Decimal(65)
    assert win.reached and win.then_ids == ("T6",) and win.then_net == Decimal(200)
    assert loss.record_ids == ("T16",) and loss.record_net == Decimal(40)
    assert not loss.reached and loss.then_ids == () and loss.then_band is None


def test_until_918_the_prior_is_read_across_books_as_one_argument():
    win = _rows(BOOK, minimum=2, across_books=False)[(OIL, "win")]
    assert win.record_ids == ("T2", "T4", "T6", "T8", "T10") and win.record_net == Decimal(85)


def test_each_figure_has_its_band_by_hand():
    rows = _rows(BOOK, minimum=2)
    win, loss = rows[(OIL, "win")], rows[(OIL, "loss")]
    assert win.record_band.band == (-95.0, 165.0) and win.record_band.inside
    assert win.then_band.band == (-60.0, 200.0) and win.then_band.inside  # the end is inside
    assert loss.record_band.band == (-60.0, 200.0) and loss.record_band.inside
    assert (win.record_band.draws, win.record_band.seed) == (b2_shuffle.DRAWS, b2_shuffle.SEED)


def test_the_band_is_random_sets_of_the_same_size():
    LO = _module("services.shared.conditions.leave_out")
    band_of = _built(LO, "band_of")
    same = band_of([-100.0] * 10, -300.0, 3)
    assert same.band == (-300.0, -300.0) and same.inside
    rare = band_of([-1000.0] + [10.0] * 99, -1000.0, 1)  # 1 draw in 100 is the -1000
    assert rare.band == (10.0, 10.0) and not rare.inside
    assert band_of([1.0, 2.0], 0.0, 0).band == (0.0, 0.0)
    assert band_of([-40.0, 7.0, 3.0], 7.0, 2) == band_of([-40.0, 7.0, 3.0], 7.0, 2)
    assert "inside" not in LO.ChanceBand.__dataclass_fields__  # decided from the band, not passed


def test_the_figures_are_decided_once_per_request():
    ctx = SF.record_context(BOOK)
    assert "previous_result" in ctx
    assert {(r.book, r.state) for r in ctx["previous_result"]} == {(OIL, "win"), (OIL, "loss")}
    assert not any(r.reached for r in ctx["previous_result"])  # at 30 nothing here is reached


def test_each_figure_reads_as_a_fact_with_its_label_covered():  # gate 1
    _, p = _view()
    # the counts inside the words are figures too, so the words are read as the page reads them
    assert _text(str(p["win"]["record_words"])) == (
        "net on 6 trades opened right after a win that day")
    assert _text(str(p["win"]["then_words"])) == (
        "net on 1 trade opened right after a win that day while your earlier ones after a win,"
        " 2 or more, were down overall")
    assert formatting.rupees(Decimal(65)) in str(p["win"]["record"])
    assert formatting.rupees(Decimal(200)) in str(p["win"]["then"])
    assert _text(str(p["loss"]["record_words"])) == (
        "net on 1 trade opened right after a loss that day")
    assert p["loss"]["then"] == "not enough trades yet" and not p["loss"]["then_words"]


def test_both_figures_carry_both_labels():
    _, p = _view()
    for row in p.values():
        assert isinstance(row["record_finding"], F.Finding)
        assert (row["record_finding"].known, row["record_finding"].rung) == (
            F.Known.ONLY_AFTER, F.Rung.SEEN)
        assert isinstance(row["then_finding"], F.Finding)
        assert (row["then_finding"].known, row["then_finding"].rung) == (
            F.Known.AT_CLICK, F.Rung.SEEN)


def test_both_figures_open_their_trades():  # gate 3
    ctx, p = _view()
    record = S.see_all_href("hidden", book=OIL, after="win")
    then = S.see_all_href("hidden", book=OIL, after="win", then="yes")
    assert f'href="{escape(record)}"' in str(p["win"]["record"])
    assert f'href="{escape(then)}"' in str(p["win"]["then"])
    assert _listed(ctx, {"book": OIL, "after": "win"}) == {"T2", "T4", "T6", "T8", "T10", "T14"}
    assert _listed(ctx, {"book": OIL, "after": "win", "then": "yes"}) == {"T6"}
    assert _listed(ctx, {"book": OIL, "after": "loss"}) == {"T16"}


def test_the_chance_line_cannot_be_written_without_its_band():  # gate 2
    chance = _module("services.production.api.chance")
    inside, refused = _built(chance, "inside"), _built(chance, "NoComparison")
    LO = _module("services.shared.conditions.leave_out")
    for not_a_band in (True, "inside", {"inside": True}, 1):
        with pytest.raises(refused):
            inside(not_a_band)
    assert inside(None) is False
    assert inside(LO.band_of([-100.0] * 10, -300.0, 3)) is False  # every set sums to -300
    source = HIDDEN.read_text(encoding="utf-8")
    assert CHANCE in source
    for said in re.finditer(re.escape(CHANCE), source):
        tag = source[source.rfind("{%", 0, said.start()):]
        assert re.match(r"\{%-?\s*if\s+[\w.]+\s*\|\s*inside\s*-?%\}", tag), tag[:80]


def test_the_page_on_the_40_trip_fixture(client):
    LO = _module("services.shared.conditions.leave_out")
    page = client.get(S.fact_href("hidden"))
    assert page.status_code == 200
    paras = _paras(page.text)
    got = {(a.get("data-previous"), a.get("data-figure")): (a, said) for a, said in paras}
    assert set(got) == {("win", "record"), ("win", "then"), ("loss", "record"), ("loss", "then")}
    for state, net, n in (("win", -2500, 3), ("loss", -22150, 27)):
        attrs, said = got[(state, "record")]
        assert said.startswith(f"{RECORD} {formatting.rupees(Decimal(net))} net on {n} trades"
                               f" opened right after a {state} that day.")
        inside = LO.band_of([float(x) for x in POOL], float(net), n).inside
        assert (CHANCE in said) is inside  # inside the band is the result, never a blank
        assert (attrs["data-known"], attrs["data-rung"]) == ("ONLY_AFTER", "SEEN")
        attrs, said = got[(state, "then")]
        assert said == f"{THEN} not enough trades yet."  # no comparison, so no chance line
        assert (attrs["data-known"], attrs["data-rung"]) == ("AT_CLICK", "SEEN")
    for _, said in paras:
        assert not re.search(r"finding|saved|avoid|\bcost|\bkept", said.lower()), said


# Review, 18 Nov: a rule that is reached but picks nothing is compared with nothing.
#   2026-02-02  T21 +100, T22 +40 after a win   2026-02-03  T23 +100, T24 +60 after a win
#   2026-02-04  T25 +100, T26 -10 after a win
# At a minimum of 2, T26 has T22 and T24 before it at +100: up, so nothing is picked.
ZERO = [
    trip(21, "2026-02-02", 100), trip(22, "2026-02-02", 40, minute=10),
    trip(23, "2026-02-03", 100), trip(24, "2026-02-03", 60, minute=10),
    trip(25, "2026-02-04", 100), trip(26, "2026-02-04", -10, minute=10),
]


def test_a_rule_that_picked_nothing_says_so_and_draws_no_verdict():
    chance = _module("services.production.api.chance")
    LO = _module("services.shared.conditions.leave_out")
    row = _rows(ZERO, minimum=2)[(OIL, "win")]
    assert row.reached and row.then_ids == () and row.then_net == Decimal(0)
    assert chance.inside(row.then_band) is False  # a set of no trades is no comparison
    assert chance.inside(LO.band_of([1.0, 2.0], 0.0, 0)) is False
    ctx = SF.record_context(ZERO)
    ctx["previous_result"] = mx.previous_result_figures(ZERO, minimum=2)
    books = {b["book"]: b for b in SF._hidden_view(ctx)["books"]}
    p = {q["state"]: q for q in books[OIL]["previous"]}
    said = _text(str(p["win"]["then"]))
    assert said == ("no trade after a win was opened while your earlier ones after a win,"
                    " 2 or more, were down overall")
    assert not p["win"]["then_words"] and "0 trades" not in said


# Ruling, 24 Nov: the previous result is judged before charges; what is summed stays net.
#   A 09:20-09:30 gross +100, net -50: a win before charges, a loss after them.
#   B 09:40-09:50 gross -200, net -230: its previous result is A.
def _charged(**gross: str) -> list[mx.Trip]:
    return mx.load_trips([
        {"trip_id": i, "symbol": "WIDGETOIL", "trading_day": "2026-03-02",
         "entry_ts": f"2026-03-02T{opened}:00+05:30", "exit_ts": f"2026-03-02T{closed}:00+05:30",
         "holding_seconds": 600, "net": net, "lots": 1, "risk_unit_source": "premium_paid",
         **({"gross": gross[i]} if i in gross else {})}
        for i, opened, closed, net in (("A", "09:20", "09:30", "-50"),
                                       ("B", "09:40", "09:50", "-230"))
    ])


def test_the_previous_result_is_judged_before_charges():
    trips = _charged(A="100", B="-200")
    assert mx.previous_states(trips) == {"B": "win"}  # on net it is "loss"
    (row,) = mx.previous_result_figures(trips)
    assert (row.state, row.record_ids) == ("win", ("B",))
    assert row.record_net == Decimal(-230)  # what is summed stays net


def test_a_fixture_without_a_result_before_charges_is_judged_on_net():
    assert mx.previous_states(_charged()) == {"B": "loss"}


def test_the_loader_carries_the_result_before_charges_over_every_leg(client, engine):
    # Two legs of one position: gross +300 -100 = +200, net +250 -140 = +110.
    with make_session(engine) as sess:
        trader = sess.scalars(select(m.Trader).where(m.Trader.login_id == "fx")).one()
        imp = loader.current_import(sess, trader)
        for leg, strike, gross, net in (("leg-1", 5100, 300, 250), ("leg-2", 5000, -100, -140)):
            sess.add(m.Trip(
                import_id=imp.id, trip_id=leg, position_id="P919", trading_day="2026-10-01",
                exchange="MCX", symbol="WIDGETOIL", segment="OPT", direction="LONG",
                option_type="CE", strike=Decimal(strike),
                entry_ts=datetime(2026, 10, 1, 10, 0, tzinfo=IST),
                exit_ts=datetime(2026, 10, 1, 10, 5, tzinfo=IST), quantity=100,
                entry_price=Decimal(100), exit_price=Decimal(100), gross=Decimal(gross),
                fees=Decimal(gross - net), net=Decimal(net), fees_available=True,
                risk_unit_source=s.RiskUnitSourceV1.PREMIUM_PAID))
        sess.commit()
        trips, _ = loader.load_for(sess, trader)
    (position,) = [t for t in trips if t.trip_id == "P919"]
    assert position.net == Decimal(110)
    assert getattr(position, "gross", None) == Decimal(200)


# Review, 24 Nov: a set that is its whole pool is the only set of its size, so no draw can
# differ from it and it is compared with nothing.
def test_a_whole_pool_is_no_comparison():
    chance = _module("services.production.api.chance")
    LO = _module("services.shared.conditions.leave_out")
    pool = [-40.0, 7.0, 3.0]
    assert chance.inside(LO.band_of(pool, sum(pool), len(pool))) is False


# Founder, 24 Nov (919 Q1: b): when every random set gives the same sum there is no chance line.
#   3 of ten at -100: every set is -300, so the band is one value.
#   3 of ten, nine at -100 and one a hair lower: the sums differ, so the comparison stands.
def test_a_band_of_one_value_is_no_comparison():
    chance = _module("services.production.api.chance")
    LO = _module("services.shared.conditions.leave_out")
    for figure in (-100.0, -0.1):  # a whole rupee, and a value no float holds exactly
        pool = [figure] * 10
        band = LO.band_of(pool, sum(pool[:3]), 3)
        assert band.size < band.pool_size and band.band[0] == band.band[1]
        assert chance.inside(band) is False


def test_a_band_whose_ends_barely_differ_is_still_compared():
    chance = _module("services.production.api.chance")
    LO = _module("services.shared.conditions.leave_out")
    band = LO.band_of([-100.0] * 9 + [-100.0000000001], -300.0, 3)
    assert 0 < band.band[1] - band.band[0] < 1e-9  # no tolerance: differing at all is enough
    assert chance.inside(band) is True


# 15 days, each 10:00 +100 and 10:10 +40 or -60 in turn. Every trade with a previous result is
# after a win: 8 at +40 and 7 at -60 = -100 on 15 trades, which is the whole pool.
WHOLE = [
    t for d in range(1, 16) for t in (
        trip(2 * d + 99, f"2026-04-{d:02d}", 100),
        trip(2 * d + 100, f"2026-04-{d:02d}", 40 if d % 2 else -60, minute=10))
]


def test_the_page_draws_no_verdict_on_a_whole_pool(client, monkeypatch):
    real = loader.load_for
    monkeypatch.setattr(loader, "load_for", lambda *a, **kw: (WHOLE, real(*a, **kw)[1]))
    page = client.get(S.fact_href("hidden"))
    assert page.status_code == 200
    got = {(a.get("data-previous"), a.get("data-figure")): said for a, said in _paras(page.text)}
    assert set(got) == {("win", "record"), ("win", "then")}
    said = got[("win", "record")]
    assert said.startswith(f"{RECORD} {formatting.rupees(Decimal(-100))} net on 15 trades"
                           " opened right after a win that day.")
    assert CHANCE not in said


# TICKET-919 (research seat, 25 Nov, comment 17381; D9 option b, carried from TICKET-1081): the
# page that shows the 30 says it was picked, not learned, on its own line under that block.
#   40 days, each 10:00 +100 then 10:10 -50: 40 trades after a win. The 31st has 30 earlier ones
#   down overall, so the warm-up is reached and the 30 is shown.
PICKED = "The 30 is a starting point we picked, not one learned from your trades."
REACHED = [
    t for d in range(40) for t in (
        trip(2 * d + 500, (datetime.fromisoformat("2026-01-01") + timedelta(days=d)).date().isoformat(), 100),
        trip(2 * d + 501, (datetime.fromisoformat("2026-01-01") + timedelta(days=d)).date().isoformat(), -50,
             minute=10))
]


def test_the_30_is_labelled_as_picked_not_learned(client, monkeypatch):
    real = loader.load_for
    monkeypatch.setattr(loader, "load_for", lambda *a, **kw: (REACHED, real(*a, **kw)[1]))
    html = client.get(S.fact_href("hidden")).text
    then = re.search(r'<p\b[^>]*data-figure="then"[^>]*>.*?</p>', html, re.DOTALL)
    assert then and "30 or more" in _text(then.group(0))  # the block shows the 30
    own = re.findall(r"<p\b[^>]*>\s*" + re.escape(PICKED) + r"\s*</p>", html)
    assert len(own) == 1 and html.count(PICKED) == 1  # once, and on a line of its own
    assert 'data-figure' not in own[0]  # a label, never a figure
    after = html[then.end():]
    assert re.match(r"\s*" + re.escape(own[0]), after)  # directly under the block


def test_the_30_label_is_absent_while_the_block_does_not_show_the_30(client):
    html = client.get(S.fact_href("hidden")).text
    assert f"{THEN} not enough trades yet." in _text(html)  # the 40-trip page: 30 not shown
    assert PICKED not in _text(html)
