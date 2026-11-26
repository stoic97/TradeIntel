"""TICKET-1006: what you do next. Three facts in chapter 3, after "After two straight losses":

* ``back-in``, how fast the next trade came after a loss and after a win, as his medians;
* ``same-way``, whether the next trade needed the underlying the same way or the other way;
* ``next-day``, the day he traded next after his best days and his worst days, against his
  other next days.

Counts and medians only, each group opening its trades. On a phone each sits in the list under
the dial (1002); on desktop each has its wedge. Every trade here is made up, and the expected
figures are worked by hand in the comments.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from services.production.api import dial as Dl
from services.production.api import factor_map, findings
from services.production.api import glossary as GL
from services.production.api import scope_facts as SF
from services.production.api import scope_geometry as G
from services.production.api import scope_map as S
from services.production.api import trade_list as TL
from services.production.mirror import metrics as mx
from services.shared.schemas import scope_v1 as s
from tests.helpers.no_claims import CLAIM_PATTERNS, NEVER_USED
from tests.unit.api import figure_pages as P

IST = ZoneInfo("Asia/Kolkata")
D = Decimal
NEW = ("back-in", "same-way", "next-day")
FIT = -13  # the layout's own limit (test_dial_states_facts)


def leg(kind: str | None, side: str, net) -> mx.TradeLine:
    seg = "OPT" if kind else "FUT"
    return mx.TradeLine("NIFTY", seg, side, 1, None, None, D(str(net)),
                        strike=D("24000") if kind else None, option_type=kind)


def trip(tid, day, opened, closed, net, *legs, lots=1):
    entry = datetime.fromisoformat(f"{day}T{opened}:00").replace(tzinfo=IST)
    leave = datetime.fromisoformat(f"{day}T{closed}:00").replace(tzinfo=IST)
    lines = legs or (leg("CE", "Buy", net),)
    return mx.Trip(trip_id=tid, symbol="NIFTY", trading_day=day, entry_ts=entry, exit_ts=leave,
                   holding_seconds=int((leave - entry).total_seconds()), net=D(str(net)), lots=lots,
                   risk_unit_source=s.RiskUnitSourceV1.PREMIUM_PAID, is_option=True, lines=lines)


def next_trades(trips):
    assert hasattr(mx, "next_trades"), "metrics has no next_trades()"
    return mx.next_trades(trips)


def day_after(trips):
    assert hasattr(mx, "day_after"), "metrics has no day_after()"
    return mx.day_after(trips)


# ---------- the pairs: each trade and the last trade that closed before it opened, that day ----------
# 2 Mar:
#   a1 bought call (long)   09:15-09:30  -100  loss
#   a2 bought call (long)   09:34-09:50  +200  prev a1 (loss): 4 minutes, the same way
#   a3 bought put (short)   10:01-10:20     0  prev a2 (win): 11 minutes, the other way
#   a4 bought put (short)   10:25-10:40   -50  prev a3, which finished level: in neither group
#   a5 bought call          10:35-10:45   +30  opened before a4 closed, so a4 isn't its previous:
#                                               prev a3 again, level, in neither group
#   a6 a call spread        10:50-11:00   -20  prev a5 (win): 5 minutes; no single direction
# 3 Mar:
#   b1 sold put (long)      09:20-09:40  -300  loss
#   b2 sold call (short)    09:46-10:00  +100  prev b1 (loss): 6 minutes, the other way
# After a loss: a2 (4), b2 (6): median 5. After a win: a3 (11), a6 (5): median 8. Level: 2.
# Same way after a loss: 1 of 2 (a2); after a win: 0 of 1 (a3); a6 left out, no single direction.
PAIRS = [
    trip("a1", "2026-03-02", "09:15", "09:30", -100),
    trip("a2", "2026-03-02", "09:34", "09:50", 200),
    trip("a3", "2026-03-02", "10:01", "10:20", 0, leg("PE", "Buy", 0)),
    trip("a4", "2026-03-02", "10:25", "10:40", -50, leg("PE", "Buy", -50)),
    trip("a5", "2026-03-02", "10:35", "10:45", 30),
    trip("a6", "2026-03-02", "10:50", "11:00", -20, leg("CE", "Buy", -60), leg("CE", "Sell", 40)),
    trip("b1", "2026-03-03", "09:20", "09:40", -300, leg("PE", "Sell", -300)),
    trip("b2", "2026-03-03", "09:46", "10:00", 100, leg("CE", "Sell", 100)),
]


def test_each_trade_is_paired_with_the_last_trade_that_closed_before_it():
    nt = next_trades(PAIRS)
    assert [t.trip_id for t in nt.after_loss] == ["a2", "b2"]
    assert [t.trip_id for t in nt.after_win] == ["a3", "a6"]
    assert nt.scratch == 2  # a4 and a5 came after a3, which finished level
    assert nt.group_of == {"a2": "loss", "b2": "loss", "a3": "win", "a6": "win"}


def test_an_overlapping_trade_is_not_next():
    nt = next_trades(PAIRS)
    assert nt.minutes["a6"] == D(5)  # after a5, not after a4, which it never overlapped
    assert "a5" not in nt.group_of   # a5 opened while a4 was open: its previous is a3


def test_the_medians_are_his():
    nt = next_trades(PAIRS)
    assert (nt.loss_median, nt.win_median) == (D(5), D(8))


def test_same_way_counts_and_a_spread_left_out():
    nt = next_trades(PAIRS)
    assert (nt.same_after_loss, nt.other_after_loss) == (1, 1)
    assert (nt.same_after_win, nt.other_after_win) == (0, 1)
    assert nt.no_direction == 1


@pytest.mark.skip(reason="superseded by the founder's ruling of 24 Nov 2026 (TICKET-1006): back in is B1, after a loss against after a win or a level trade, 30 each; see test_back_in_b1.py. Assertion kept as it was.")
def test_the_back_in_line():
    figs = facts_of(PAIRS)
    assert words(figs["back-in"]["line"]) == (
        "After a loss your next trade came a median 5 minutes later; after a win, 8.")


def test_the_same_way_line_under_thirty_is_counts():
    figs = facts_of(PAIRS)
    assert words(figs["same-way"]["line"]) == (
        "After a loss, your next trade went the same way 1 of 2 times; after a win, 0 of 1. "
        "Too few for a rate: a rate needs 30 trades in each group.")


# 40 days, each: x loses (bought call), then y wins, then z.
#   y the same way as x on days 0-29 (bought call), the other way on 30-39 (bought put).
#   z the same way as y on days 0-19; the other way on 20-29 (z a put after y's call) and on
#   30-39 (z a call after y's put).
# After a loss: 30 of 40 the same way, 75 of 100. After a win: 20 of 40, 50 of 100.
def many_pairs():
    out = []
    for i in range(40):
        day = (datetime(2026, 1, 1, tzinfo=IST) + timedelta(days=i)).date().isoformat()
        y_kind = "CE" if i < 30 else "PE"
        z_kind = "CE" if i < 20 or i >= 30 else "PE"
        out += [trip(f"x{i}", day, "09:15", "09:30", -10),
                trip(f"y{i}", day, "09:40", "09:50", 20, leg(y_kind, "Buy", 20)),
                trip(f"z{i}", day, "10:00", "10:10", -5, leg(z_kind, "Buy", -5))]
    return out


@pytest.mark.skip(reason="superseded: every rate reads N of 100 in every sentence (the rates-of-100 rule on main); the after-a-win half now reads \"50 of 100\", pinned in test_same_way_pairs_and_day_after_page. Assertion left as written.")
def test_the_same_way_rates_from_thirty():
    figs = facts_of(many_pairs())
    assert words(figs["same-way"]["line"]) == (
        "After a loss, your next trade went the same way 75 of 100 times; after a win, 50.")


# ---------- the day after a big day ----------
# Ten days he closed trades on, results by day:
#   d1 +500 (1 trade)  d2 -400 (4 trades, 2 lots each)  d3 +50 (1)  d4 +300 (2)  d5 -10 (2)
#   d6 -600 (2)  d7 +20 (1)  d8 +400 (2)  d9 -300 (3)  d10 +10 (1)
# A tenth of ten is under three, so three each. Best: d1, d8, d4. Worst: d6, d2, d9.
# Each day's previous traded day decides its group:
#   after a best day:  d2 (after d1), d5 (after d4), d9 (after d8): 9 trades on 3 days, 3 a day;
#                      lots 8 + 2 + 3 = 13 on 9 trades, 1.444, shown 1.4
#   after a worst day: d3, d7, d10: 3 trades on 3 days, 1 a day, 1 lot
#   other next days:   d4, d6, d8: 6 trades on 3 days, 2 a day, 1 lot
DAYS = {1: (500, 1, 1), 2: (-400, 4, 2), 3: (50, 1, 1), 4: (300, 2, 1), 5: (-10, 2, 1),
        6: (-600, 2, 1), 7: (20, 1, 1), 8: (400, 2, 1), 9: (-300, 3, 1), 10: (10, 1, 1)}


def big_days():
    out = []
    for n, (net, count, lots) in DAYS.items():
        day = f"2026-03-{n + 1:02d}"
        for k in range(count):
            out.append(trip(f"d{n}t{k}", day, f"1{k}:00", f"1{k}:30", D(net) / count, lots=lots))
    return out


def test_best_and_worst_days_and_their_next_days():
    da = day_after(big_days())
    assert da.best == ("2026-03-02", "2026-03-09", "2026-03-05")
    assert da.worst == ("2026-03-07", "2026-03-03", "2026-03-10")
    assert {g: len(da.groups[g]) for g in ("best", "worst", "other")} == {"best": 9, "worst": 3, "other": 6}
    assert da.days_in == {"best": 3, "worst": 3, "other": 3}


def test_the_next_day_line():
    figs = facts_of(big_days())
    assert words(figs["next-day"]["line"]) == (
        "On the days after your best days you took 3 trades a day at 1.4 lots; "
        "after your worst days, 1 at 1; usually 2 at 1.")


def test_fewer_than_six_traded_days_draws_nothing():
    few = [t for t in big_days() if t.trading_day <= "2026-03-04"]  # three days
    assert day_after(few).state is s.ResultState.INSUFFICIENT_SAMPLE
    assert facts_of(few)["next-day"]["state"] == "not-enough"


# ---------- taps: each group opens its trades ----------

def listed(key, record, **query) -> int:
    assert key in S.FACTS, f"no fact {key}"
    return TL.listing(key, SF.record_context(record), {k: str(v) for k, v in query.items()}, {})["shown"]


@pytest.mark.skip(reason="superseded by the founder's ruling of 24 Nov 2026 (TICKET-1006): back in is B1, after a loss against after a win or a level trade, 30 each; see test_back_in_b1.py. Assertion kept as it was.")
def test_the_after_filter_opens_each_group():
    assert listed("back-in", PAIRS) == 4
    assert listed("back-in", PAIRS, after="loss") == 2
    assert listed("back-in", PAIRS, after="win") == 2
    assert listed("same-way", PAIRS) == 3  # a6 has no single direction
    # The after filter is shared with 996's size; only `only` differs, and an unoffered filter
    # fails nothing. Same way again's list, by loss and by win, must make the whole list.
    by_loss, by_win = listed("same-way", PAIRS, after="loss"), listed("same-way", PAIRS, after="win")
    assert 0 < by_loss < 3 and 0 < by_win < 3 and by_loss + by_win == 3


def test_the_next_day_filter_opens_each_group():
    assert listed("next-day", big_days(), next_day="best") == 9
    assert listed("next-day", big_days(), next_day="worst") == 3
    assert listed("next-day", big_days(), next_day="other") == 6


def test_the_filters_and_facts_are_on_the_factor_map():
    names = {f.name for f in TL.FILTERS}
    assert {"after", "next_day"} <= names
    on_map_filters = {k for f in factor_map.FACTORS for k in f.filters}
    on_map_facts = {k for f in factor_map.FACTORS for k in f.facts}
    assert {"after", "next_day"} <= on_map_filters
    assert set(NEW) <= on_map_facts


# ---------- wired as `down` is ----------

def test_three_facts_in_chapter_three_after_down():
    three = S.chapter(3)
    assert [f.key for f in three.facts] == ["down", *NEW, "busiest", "after-close"]  # After you closed ends the chapter
    assert all(not S.FACTS[k].on_phone_dial for k in NEW)
    assert all(k in findings.LABELS for k in NEW)
    assert all(S.FACTS[k].chart in G.CHARTS for k in NEW)
    assert all(S.FACTS[k].chart in SF.CARD_H for k in NEW)


@pytest.fixture()
def demo():
    from services.production.api.app import create_app
    app = create_app()
    client = TestClient(app)
    P._sign_up(client, app.state.engine, "visitor")
    P._consent(client)
    client.post("/upload/demo", data={"csrf_token": P._token(client, "/upload")}, follow_redirects=False)
    return client


def main_of(html: str) -> str:
    return re.search(r"<main.*?</main>", html, re.DOTALL).group(0)


def test_each_page_opens_and_says_no_claim(demo):
    for key in NEW:
        r = demo.get(f"/mirror/fact/{key}")
        assert r.status_code == 200, key
        body = main_of(r.text)
        assert "<script" not in body
        said = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", body)).lower()
        assert not [w for w in NEVER_USED if re.search(rf"\b{re.escape(w)}\b", said)], key
        assert not [p for p, _ in CLAIM_PATTERNS if re.search(p, said, re.IGNORECASE)], key
        for phrase in ("your rule", "your plan", "your system", "rush", "tend to"):
            assert phrase not in said, (key, phrase)
        assert demo.get(f"/mirror/fact/{key}/trades").status_code == 200


def test_on_a_phone_they_sit_in_the_list_and_on_desktop_each_has_its_wedge(demo):
    html = demo.get("/mirror/chapter/3").text
    phone, desktop = html.split('<div class="scope scope--desktop">', 1)
    rows = re.findall(r'<li class="scope__list-row".*?</li>', phone, flags=re.DOTALL)
    assert len(rows) == 4  # the three facts above and After you closed
    for row in rows:
        said = " ".join(re.sub(r"<[^>]+>", " ", row).split()).lower()
        assert set(re.findall(r"[a-z]+", said)) & GL.nouns(), said
    assert len(re.findall(r'<a class="scope__slice', desktop.split("</svg>")[0])) == 6


def test_the_desktop_dial_clears_with_five_wedges():
    from tests.helpers.hub_answers import CTX
    from tests.helpers.scope_chapters import IMP

    view = SF.chapter_view(3, SF.facts(CTX, IMP))
    assert "desktop_items" in view, "chapter 3 has no fact off the phone dial"
    items = view["desktop_items"]
    assert len(items) == 6  # After you closed is the sixth wedge
    z = G.SIZES["desktop"]
    rr = G.radii(z["R"])
    sec = G.sectors(len(items), False)
    lay = G.layout_contents(items, sec, rr, z["figSizesChapter"])
    for i, b in enumerate(lay["blocks"]):
        assert G.block_clearance(sec["slices"][i], sec["span"], lay["radius"][i], b, rr) >= FIT, items[i]["name"]
    assert len(Dl.scope_dial(view, "desktop").split('class="scope__slice')) - 1 == 6


# ---------- helpers ----------

def facts_of(record):
    from tests.helpers.scope_chapters import IMP
    figs = SF.facts(SF.record_context(record), IMP)
    assert all(k in figs for k in NEW), "the three facts are not drawn"
    return figs


def words(markup) -> str:
    return " ".join(re.sub(r"<[^>]+>", " ", str(markup)).split()).replace(" ,", ",").replace(" .", ".").replace(" ;", ";")
