"""Journals lead with the days worth writing about, and ask fewer questions [TICKET-826].

Every trade below is synthetic. The history, worked by hand (lots, then net per trade):

    day          trades                                              net   why it matters
    2025-02-03   1,+50   1,+50                                      +100   nothing flagged
    2025-02-04   1,-100  1,+10                                       -90   5th worst
    2025-02-05   1,-200  1,+10                                      -190   4th worst
    2025-02-06   1,-300  1,+10                                      -290   3rd worst
    2025-02-07   1,-400  1,+10                                      -390   2nd worst
    2025-02-10   1,-500  1,+10                                      -490   worst
    2025-02-11   1,-40  1,-10  1,-10  3,-30  1,+100                  +10   longest run: 4
    2025-02-12   1,+5  1,-20  1,+5  1,+5  1,+5  1,+5                  +5   busiest: 6 trades
    2025-02-13   1,+50   1,+60                                      +110   nothing flagged
    2025-02-14   1,+50   1,+50                                      +100   the file's last day

Which five to start with: the run's day, the busiest day, then the worst days in order
until there are five. So 11 Feb, 12 Feb, 10 Feb, 7 Feb, 6 Feb.

Usual size: 27 option trades, 29 lots (26 of 1 lot, 1 of 3), so 1.074, read as "about 1.1".
"""

from __future__ import annotations

import os
import re
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from services.production.api.app import create_app
from services.production.db import models as m
from services.production.db.session import make_engine, make_session, run_migrations
from services.shared.schemas import scope_v1 as s
from tests.unit.api.test_upload import CSRF, sign_up

HEADER = (
    "Date,Time,Name,Buy/Sell,Order,Exchange,Segment,Quantity/Lot,Trade Price,Trade Value,Status"
)
OPTION = "WIDGETOIL 28 FEB 5000 CALL"
LOT = 100

HISTORY = {
    "2025-02-03": [(1, 50), (1, 50)],
    "2025-02-04": [(1, -100), (1, 10)],
    "2025-02-05": [(1, -200), (1, 10)],
    "2025-02-06": [(1, -300), (1, 10)],
    "2025-02-07": [(1, -400), (1, 10)],
    "2025-02-10": [(1, -500), (1, 10)],
    "2025-02-11": [(1, -40), (1, -10), (1, -10), (3, -30), (1, 100)],
    "2025-02-12": [(1, 5), (1, -20), (1, 5), (1, 5), (1, 5), (1, 5)],
    "2025-02-13": [(1, 50), (1, 60)],
    "2025-02-14": [(1, 50), (1, 50)],
}
START_WITH = ["2025-02-11", "2025-02-12", "2025-02-10", "2025-02-07", "2025-02-06"]
EARLIER = ["2025-02-13", "2025-02-05", "2025-02-04", "2025-02-03"]


def _rows(day: str, trades: list[tuple[int, int]]) -> list[str]:
    rows = []
    for n, (lots, net) in enumerate(trades):
        quantity = lots * LOT
        paid = quantity * 50
        got = paid + net
        hour, opened, closed = 10 + n, f"{10 + n}:00:00", f"{10 + n}:05:00"
        assert hour < 23
        rows.append(f"{day},{opened},{OPTION},BUY,INTRADAY,MCX,Commodity,{quantity},"
                    f"50.00,{paid:.2f},Traded")
        rows.append(f"{day},{closed},{OPTION},SELL,INTRADAY,MCX,Commodity,{quantity},"
                    f"{got / quantity:.2f},{got:.2f},Traded")
    return rows


FILE = "\n".join(
    [HEADER, *[row for day, trades in HISTORY.items() for row in _rows(day, trades)]]
) + "\n"


@pytest.fixture()
def engine(scope_environment):
    built = make_engine(os.environ["SCOPE_DB"])
    run_migrations(built)
    return built


@pytest.fixture()
def client(engine):
    signed_in = sign_up(TestClient(create_app()), engine, "WORTH", "worth")
    token = CSRF.search(signed_in.get("/upload").text).group(1)
    sent = signed_in.post("/upload", files={"file": ("t.csv", FILE.encode(), "text/csv")},
                          data={"csrf_token": token}, follow_redirects=False)
    assert sent.status_code == 303, sent.text
    return signed_in


def _journal_ids(engine) -> dict[str, int]:
    with make_session(engine) as sess:
        rows = sess.scalars(select(m.Journal).order_by(m.Journal.version_no)).all()
        return {j.period_start: j.id for j in rows}


def _listed_days(engine, html: str) -> list[str]:
    days_by_id = {v: k for k, v in _journal_ids(engine).items()}
    return [days_by_id[int(i)] for i in re.findall(r'href="/journals/(\d+)"', html)]


def _readable(html: str) -> str:
    return " ".join(re.sub(r"<[^>]+>", " ", html).split())


def _outside_the_rest(html: str) -> str:
    return re.sub(r"<details.*?</details>", "", html, flags=re.DOTALL)


def _trade_heads(html: str) -> list[str]:
    return re.findall(r'<p class="journal-trade__head"><span>(Trade \d+)</span>', html)


def _second_upload(engine) -> None:
    """The question's floor: a second upload. Nothing in it changes a Journal."""
    with make_session(engine) as sess:
        trader = sess.scalars(select(m.Trader).where(m.Trader.login_id == "worth")).one()
        raw = m.RawFile(trader_id=trader.id, sha256="e" * 64, original_name="g.csv",
                        size=1, stored_path="/tmp/g", uploaded_at=datetime.now(UTC))
        sess.add(raw)
        sess.flush()
        sess.add(m.Import(trader_id=trader.id, raw_file_id=raw.id, source_account="A",
                          adapter_id="dhan_tradebook_v1", adapter_version="1",
                          filemap_version="1", code_version="fixturesha",
                          outcome=s.ImportOutcome.ACCEPTED_PARTIAL_FIELDS,
                          rows_in=0, rows_parsed=0, rows_excluded=0,
                          fees_available=False, version_no=2, trips_reconstructed=0,
                          density_default_unit="day", created_at=datetime.now(UTC)))
        sess.commit()


# ---------- The list ----------


def test_the_fixture_is_the_history_worked_above(engine, client):
    """Every assertion below depends on this: nine Journals, none for the last day."""
    assert sorted(_journal_ids(engine)) == sorted(set(HISTORY) - {"2025-02-14"})


def test_the_list_leads_with_the_five_days(engine, client):
    html = client.get("/journals").text
    assert "Start with these 5 days" in _readable(html)
    assert _listed_days(engine, html) == START_WITH, "run, busiest, then worst days in order, five in all"


def test_each_day_on_the_list_says_why_it_is_there(client):
    text = _readable(client.get("/journals").text)
    assert "Your longest losing run: 4 losses in a row" in text
    assert "Your busiest day: 6 trades" in text
    assert "This was one of your five worst days" in text


def test_the_rest_stays_behind_earlier(engine, client):
    text = _readable(client.get("/journals").text)
    assert "You have 4 earlier Journals" in text


def test_the_calendar_holds_every_day_each_with_one_state(engine, client):
    """TICKET-906: this said earlier held every other day - no day on both lists.

    The calendar holds every day. The guard is now one day, one state, one destination:
    a day the list starts with reads worth a look on the calendar too, and leads to the
    same Journal from both.
    """
    html = client.get("/journals/catch-up").text
    assert _listed_days(engine, html) == sorted(START_WITH + EARLIER), "every day, in date order"
    surface = client.get("/journals").text
    ids = _journal_ids(engine)
    for day in START_WITH:
        cell = re.search(rf'<a\b[^>]*data-day="{day}"[^>]*>', html).group(0)
        assert 'data-state="worth"' in cell, day
        assert f'href="/journals/{ids[day]}"' in cell and f'href="/journals/{ids[day]}"' in surface, day


def test_earlier_no_longer_calls_itself_behind_the_most_recent(client):
    text = _readable(client.get("/journals/catch-up").text)
    assert "five most recent" not in text


def test_a_journal_that_covers_more_than_a_day_is_not_named():
    """Weekly or per-10-trade Journals are not days, so the list keeps the latest five."""
    from services.production.api import days_worth_a_look as worth

    class Period:
        period_start, period_end = "2025-02-03", "2025-02-07"

    flags = {"2025-02-04": [worth.Flag("One of them", "/mirror/fact/run")]}
    assert worth.to_start_with([Period()], flags) == []


def _trip(day, at, net):
    from services.production.mirror import metrics as mx

    entry = datetime.fromisoformat(f"{day}T{at}:00+05:30")
    return mx.Trip(f"{day}-{at}", "WIDGETOIL", day, entry, entry + timedelta(minutes=5), 300,
                   Decimal(net), 1, s.RiskUnitSourceV1.PREMIUM_PAID)


def test_a_run_across_two_days_is_named_on_both_but_only_its_first_leads():
    from services.production.api import days_worth_a_look as worth

    trips = [_trip("2025-02-03", "10:00", -1), _trip("2025-02-03", "11:00", -1),
             _trip("2025-02-04", "10:00", -1), _trip("2025-02-05", "10:00", 9)]
    flags = worth.flags_by_day(trips)
    assert next(iter(flags)) == "2025-02-03"
    labels = [f.label for f in flags["2025-02-04"]]
    assert "Part of your longest losing run: 3 losses in a row" in labels


def test_a_day_that_made_money_is_never_one_of_the_worst():
    """With five days or fewer, every day is in the five. A winning day isn't a bad one."""
    from services.production.api import days_worth_a_look as worth

    trips = [_trip("2025-02-03", "10:00", 9), _trip("2025-02-04", "10:00", -9)]
    flags = worth.flags_by_day(trips)
    assert "2025-02-03" not in flags
    assert [f.label for f in flags["2025-02-04"]] == ["This was one of your five worst days"]


def test_a_run_of_one_and_a_tie_for_busiest_name_nothing():
    """One loss is not a run. Every day at the same count has no busiest day."""
    from services.production.api import days_worth_a_look as worth

    trips = [_trip("2025-02-03", "10:00", 9), _trip("2025-02-04", "10:00", -9),
             _trip("2025-02-05", "10:00", 9)]
    labels = [f.label for day in worth.flags_by_day(trips).values() for f in day]
    assert labels == ["This was one of your five worst days"]


# ---------- What a day says ----------


@pytest.mark.parametrize(("day", "label", "href"), [
    ("2025-02-10", "This was one of your five worst days", "/mirror/fact/worst-days"),
    ("2025-02-04", "This was one of your five worst days", "/mirror/fact/worst-days"),
    ("2025-02-11", "Your longest losing run: 4 losses in a row", "/mirror/fact/run"),
    ("2025-02-12", "Your busiest day: 6 trades", "/mirror/fact/busiest"),
])
def test_a_flagged_day_links_the_finding(engine, client, day, label, href):
    html = client.get(f"/journals/{_journal_ids(engine)[day]}").text
    assert label in _readable(html)
    assert f'href="{href}' in html


def test_an_unflagged_day_claims_nothing(engine, client):
    html = client.get(f"/journals/{_journal_ids(engine)['2025-02-13']}").text
    assert "/mirror/fact/" not in html


def test_the_size_line_stays_on_the_day(engine, client):
    html = client.get(f"/journals/{_journal_ids(engine)['2025-02-11']}").text
    assert ("On 11 Feb 2025 you went from 1 lot to 3 after 3 losses. Your usual is about 1.1 lots."
            in _readable(html))


def test_a_day_whose_size_never_rose_has_no_size_line(engine, client):
    html = client.get(f"/journals/{_journal_ids(engine)['2025-02-12']}").text
    assert "you went from" not in _readable(html)


# ---------- Fewer questions ----------


def test_the_first_trade_and_the_biggest_loss_are_asked(engine, client):
    html = client.get(f"/journals/{_journal_ids(engine)['2025-02-12']}").text
    assert _trade_heads(_outside_the_rest(html)) == ["Trade 1", "Trade 2"]


def test_when_the_first_trade_is_the_biggest_loss_the_size_up_trade_is_asked(engine, client):
    html = client.get(f"/journals/{_journal_ids(engine)['2025-02-11']}").text
    assert _trade_heads(_outside_the_rest(html)) == ["Trade 1", "Trade 4"]
    text = _readable(html)
    assert "your first trade, and the biggest loss of the day" in text
    assert "the trade where you went to 3 lots" in text


def test_every_other_trade_can_still_be_answered(engine, client):
    html = client.get(f"/journals/{_journal_ids(engine)['2025-02-11']}").text
    assert sorted(_trade_heads(html)) == [f"Trade {n}" for n in range(1, 6)]
    assert "The other 3 trades" in _readable(html)


def test_a_day_of_two_trades_asks_both_and_hides_nothing(engine, client):
    html = client.get(f"/journals/{_journal_ids(engine)['2025-02-13']}").text
    assert _trade_heads(_outside_the_rest(html)) == ["Trade 1", "Trade 2"]
    assert "<details" not in html
    assert "The trades, one at a time" in _readable(html)


def test_nothing_is_required_stays(engine, client):
    html = client.get(f"/journals/{_journal_ids(engine)['2025-02-11']}").text
    assert "Nothing on this page is required." in _readable(html)


def test_an_answer_on_a_trade_not_asked_about_stays_in_view(engine, client):
    journal_id = _journal_ids(engine)["2025-02-11"]
    html = client.get(f"/journals/{journal_id}").text
    assert not re.search(r"<details[^>]*\bopen\b", html), "nothing answered yet, so closed"

    with make_session(engine) as sess:
        rows = sess.scalars(select(m.Trip).order_by(m.Trip.entry_ts)).all()
        second_trade = [r for r in rows if r.trading_day == "2025-02-11"][1].trip_id
    client.post(f"/journals/{journal_id}/field", data={
        "trip_id": second_trade, "rationale": "Saw a level.",
        "csrf_token": CSRF.search(html).group(1),
    })

    html = client.get(f"/journals/{journal_id}").text
    assert re.search(r"<details[^>]*\bopen\b", html)
    assert "Saw a level." in html


# ---------- The ₹500 question ----------


def _open_three(engine, client) -> list[int]:
    ids = list(_journal_ids(engine).values())
    for journal_id in ids[:3]:
        client.get(f"/journals/{journal_id}")
    _second_upload(engine)
    return ids


def test_the_question_is_on_one_journal_not_every_journal(engine, client):
    ids = _open_three(engine, client)
    assert 'id="one-question"' in client.get(f"/journals/{ids[3]}").text
    for other in (ids[0], ids[4], ids[5]):
        assert 'id="one-question"' not in client.get(f"/journals/{other}").text


def test_the_question_stays_on_that_journal_until_answered(engine, client):
    ids = _open_three(engine, client)
    first = client.get(f"/journals/{ids[3]}").text
    assert 'id="one-question"' in client.get(f"/journals/{ids[3]}").text

    client.post(f"/journals/{ids[3]}/wtp", data={
        "answer": "maybe", "csrf_token": CSRF.search(first).group(1),
    })
    assert 'id="one-question"' not in client.get(f"/journals/{ids[3]}").text


# ---------- Which trades to ask about, on its own ----------


def _t(net, lots=1):
    return {"trip_id": f"{net}/{lots}", "net": Decimal(net), "lots": lots}


def _asked(trades):
    from services.production.api import asking

    return [(a.index, a.why) for a in asking.trades_to_ask(trades)]


def test_two_trades_or_fewer_are_all_asked_with_no_reasons():
    assert _asked([_t(-5)]) == [(0, None)]
    assert _asked([_t(-5), _t(-9)]) == [(0, None), (1, None)]


def test_no_trades_asks_nothing():
    assert _asked([]) == []


def test_the_biggest_loss_is_the_second_trade_asked():
    assert _asked([_t(5), _t(-9), _t(-20), _t(5)]) == [
        (0, "your first trade"), (2, "the biggest loss of the day"),
    ]


def test_a_tied_biggest_loss_is_the_earlier_one():
    assert _asked([_t(5), _t(-9), _t(-9)]) == [
        (0, "your first trade"), (1, "the biggest loss of the day"),
    ]


def test_the_size_up_trade_is_the_first_to_reach_the_days_largest_size():
    trades = [_t(-40), _t(-10), _t(-10, 2), _t(-10, 3), _t(5, 3)]
    assert _asked(trades) == [
        (0, "your first trade, and the biggest loss of the day"),
        (3, "the trade where you went to 3 lots"),
    ]


def test_a_day_with_no_loss_and_a_rise_asks_the_size_up_trade():
    assert _asked([_t(5), _t(5), _t(5, 2)]) == [
        (0, "your first trade"), (2, "the trade where you went to 2 lots"),
    ]


def test_with_no_second_trade_to_name_only_the_first_is_asked():
    assert _asked([_t(-40), _t(5), _t(5)]) == [
        (0, "your first trade, and the biggest loss of the day"),
    ]
    assert _asked([_t(5), _t(5), _t(5)]) == [(0, "your first trade")]


def test_a_share_trade_has_no_size_to_go_up():
    """Lots count on options only (TICKET-797): 4,000 shares is not a size-up."""
    assert _asked([_t(-40), _t(5, None), _t(5, None)]) == [
        (0, "your first trade, and the biggest loss of the day"),
    ]


def _line(trades, usual="1.074"):
    from services.production.api import asking

    return asking.size_line("2025-02-11", trades, Decimal(usual))


def test_the_size_line_counts_the_losses_before_the_first_rise():
    """1 lot, two losses, then 2, then 4: the rise starts after two."""
    trades = [_t(-1), _t(-1), _t(-1, 2), _t(-1, 4), _t(5, 4)]
    assert _line(trades) == ("On 11 Feb 2025 you went from 1 lot to 4 after 2 losses. "
                             "Your usual is about 1.1 lots.")


def test_one_loss_reads_in_the_singular():
    assert _line([_t(-1), _t(-1, 2), _t(5)]) == (
        "On 11 Feb 2025 you went from 1 lot to 2 after 1 loss. Your usual is about 1.1 lots.")


def test_a_size_that_fell_back_on_the_way_up_says_nothing():
    """1, 2, 1, 3 as "from 1 lot to 3 after 1 loss" reads as one jump. It wasn't."""
    assert _line([_t(-1), _t(-1, 2), _t(-1), _t(-1, 3)]) is None


def test_a_win_on_the_way_up_says_nothing():
    """The line says size kept rising while losing. A win in the climb breaks that."""
    assert _line([_t(-1), _t(5, 2), _t(-1, 3)]) is None


def test_a_rise_after_a_win_says_nothing():
    """The line is about going bigger after losing. A rise after a win isn't that."""
    assert _line([_t(5), _t(-1, 2), _t(5)]) is None


def test_a_flat_day_says_nothing():
    assert _line([_t(-1), _t(-1), _t(-1)]) is None


def test_no_usual_size_says_nothing():
    from services.production.api import asking

    assert asking.size_line("2025-02-11", [_t(-1), _t(-1, 2)], None) is None
