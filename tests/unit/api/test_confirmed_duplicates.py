"""A row the trader confirms as a duplicate is out of the record [TICKET-851].

Confirming marked the rows set aside and kept the trips already built, so the row still
counted. Confirmed rows now leave before pairing, through the path a fresh reading uses.

The file below is synthetic and its figures are worked by hand. Every fill is 50 units and
the figure is the fill's whole value. The CALL has three flagged groups, written A, B and C:

    Day  Time   Side  Value
    2    09:30  BUY   5000   row 1  A
    2    09:30  BUY   5000   row 2  A, the copy
    2    09:40  BUY   6000   row 3
    2    09:50  SELL  6500   row 4
    2    10:00  SELL  7000   row 5
    3    09:30  BUY   5500   row 8
    3    09:40  SELL  5800   row 9  B
    3    09:40  SELL  5800   row 10 B, the copy
    4    09:30  BUY   6200   row 13 C
    4    09:30  BUY   6200   row 14 C, the copy
    4    09:40  SELL  6400   row 15

The PUT stands apart and never changes: day 2 +100, day 3 +50, day 4 -100, day 5 +200 and
+300, so five trades and +550.

Pairing the CALL oldest-first, with no group confirmed:

    5000 -> 6500  +1500
    5000 -> 7000  +2000
    6000 -> 5800   -200      held from day 2 to day 3
    5500 -> 5800   +300
    6200 -> 6400   +200      the other 6200 is still open

    5 trades, +3800. With the PUT: 10 trades, +4350, 1 position open.

All three confirmed:

    5000 -> 6500  +1500
    6000 -> 7000  +1000      this SELL now closes the 6000, because the copy of 5000 is gone
    5500 -> 5800   +300
    6200 -> 6400   +200

    4 trades, +3000. With the PUT: 9 trades, +3550, nothing open.

Taking away the trade built from each copy would have left +2000 of the old total gone and
the 6000 still paired with 5800, which is -200, and is not what the file now says. That is
why rows leave before pairing and nothing is subtracted afterwards. Every combination:

    Confirmed   CALL pairing                                          Trades  Gross  Open
    none        as above                                                10    4350    1
    A           1500, 1000, 300, sold 5800 -> bought 6200 -400, 200     10    3150    0
    B           1500, 2000, -200, 5500 -> 6400 +900; 6200 x2 open        9    4750    1
    C           as none, with no 6200 left open                         10    4350    0
    A, B        1500, 1000, 300, 200; one 6200 open                      9    3550    1
    A, C        1500, 1000, 300, -400; the SELL at 6400 opens a short    9    2950    1
    B, C        1500, 2000, -200, 900; one 6200 open                     9    4750    1
    A, B, C     as above                                                 9    3550    0

Rows by day: 7, 5, 5 and 4 in the file, 21 in all; 6, 4, 4 and 4 with all confirmed, 18.
"""

from __future__ import annotations

import dataclasses
import hashlib
import itertools
import json
import re
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update

from services.production.api import admin_view, limits
from services.production.api.app import create_app
from services.production.ctr import reconstruct as rc
from services.production.ctr.intake import persist
from services.production.ctr.intake import pipeline as pl
from services.production.db import models as m
from services.production.db.session import make_session
from services.production.journal import constants as k
from services.production.journal import fields as journal_fields
from services.production.journal import sections as sec
from services.production.mirror import loader
from services.shared.schemas import scope_v1 as s
from tests.unit.api.test_read_again import (
    FILE as OTHER_FILE,
)
from tests.unit.api.test_read_again import (
    answer,
    confirm,
    counts,
    current,
    imports,
    read_again,
    send,
    stored_path,
    words,
)
from tests.unit.api.test_upload import CSRF, DUPES, client, engine, sign_up  # noqa: F401

HEADER = "Date,Time,Name,Buy/Sell,Order,Exchange,Segment,Quantity/Lot,Trade Price,Trade Value,Status"
CALL = "NIFTY 25 JAN 20000 CALL"
PUT = "NIFTY 25 JAN 20000 PUT"
LAST_DAY_COMPLETE = "2024-01-10"
FIRST_ROW_OF = {"A": 1, "B": 9, "C": 13}
THE_COPY_OF = {"A": 2, "B": 10, "C": 14}
SET_ASIDE_ONE = ("You told us 1 row repeats a trade already in the file. It is set aside, and "
                 "your figures were rebuilt without it.")
SET_ASIDE_THREE = ("You told us 3 rows repeat a trade already in the file. They are set aside, "
                   "and your figures were rebuilt without them.")
FROM_A_CONFIRMATION = "Rows you confirmed as duplicates were set aside, which changed this period."


def _row(day: str, time: str, name: str, side: str, value: int) -> str:
    return (f"2024-01-{day},{time},{name},{side},MARGIN,NSE,Derivative,50,{value / 50:.2f},"
            f"{value:.2f},Traded")


TEXT = "\n".join([
    HEADER,
    _row("02", "09:30:00", CALL, "BUY", 5000),
    _row("02", "09:30:00", CALL, "BUY", 5000),
    _row("02", "09:40:00", CALL, "BUY", 6000),
    _row("02", "09:50:00", CALL, "SELL", 6500),
    _row("02", "10:00:00", CALL, "SELL", 7000),
    _row("02", "11:00:00", PUT, "BUY", 4000),
    _row("02", "11:10:00", PUT, "SELL", 4100),
    _row("03", "09:30:00", CALL, "BUY", 5500),
    _row("03", "09:40:00", CALL, "SELL", 5800),
    _row("03", "09:40:00", CALL, "SELL", 5800),
    _row("03", "11:00:00", PUT, "BUY", 4000),
    _row("03", "11:10:00", PUT, "SELL", 4050),
    _row("04", "09:30:00", CALL, "BUY", 6200),
    _row("04", "09:30:00", CALL, "BUY", 6200),
    _row("04", "09:40:00", CALL, "SELL", 6400),
    _row("04", "11:00:00", PUT, "BUY", 4000),
    _row("04", "11:10:00", PUT, "SELL", 3900),
    _row("05", "11:00:00", PUT, "BUY", 4000),
    _row("05", "11:10:00", PUT, "SELL", 4200),
    _row("05", "12:00:00", PUT, "BUY", 4000),
    _row("05", "12:10:00", PUT, "SELL", 4300),
]) + "\n"
FILE = TEXT.encode()

TRIP_ID = re.compile(r"\b[0-9a-f]{16,64}\b")

CONTEXT = pl.ImportContext(trader_id="fx", source_account="A", code_version="testsha")


def plan(text: str = TEXT, **kwargs) -> pl.ImportPlan:
    return pl.plan_import(text, context=CONTEXT, **kwargs)


GROUP = {name: next(r.dup_group for r in plan().rows if r.row_no == row)
         for name, row in FIRST_ROW_OF.items()}


def groups(names: str) -> set[str]:
    return {GROUP[name] for name in names}


def gross(trips) -> Decimal:
    return sum((t.gross_pnl for t in trips), Decimal(0))


def bytes_of(trips) -> str:
    """Every field of every trip, in order. If this moves, a trip moved."""
    return hashlib.sha256("\n".join(t.model_dump_json() for t in trips).encode()).hexdigest()


# ---- the plan: rows leave before pairing


@pytest.mark.parametrize(("names", "trades", "total", "still_open"), [
    ("", 10, "4350", 1),
    ("A", 10, "3150", 0),
    ("B", 9, "4750", 1),
    ("C", 10, "4350", 0),
    ("AB", 9, "3550", 1),
    ("AC", 9, "2950", 1),
    ("BC", 9, "4750", 1),
    ("ABC", 9, "3550", 0),
])
def test_every_combination_reads_as_worked_by_hand(names, trades, total, still_open):
    read = plan(confirmed_groups=groups(names))
    assert len(read.trips) == trades
    assert gross(read.trips) == Decimal(total)
    assert read.open_positions == still_open


def test_removing_a_copy_changes_how_the_fills_pair():
    """The later SELL closes the 6000 once the copy of 5000 has gone: +1000, not +2000."""
    pairs = {(t.entry_price * t.quantity, t.exit_price * t.quantity)
             for t in plan(confirmed_groups=groups("ABC")).trips}
    assert (Decimal(5000), Decimal(7000)) not in pairs
    assert (Decimal(6000), Decimal(5800)) not in pairs
    assert (Decimal(6000), Decimal(7000)) in pairs


def test_a_row_removed_can_turn_a_position_round():
    """With only A confirmed, one SELL too many on day 3 opens a short that day 4 closes."""
    short = [t for t in plan(confirmed_groups=groups("A")).trips if t.direction.value == "SHORT"]
    assert [(t.entry_price * t.quantity, t.exit_price * t.quantity, t.gross_pnl)
            for t in short] == [(Decimal(5800), Decimal(6200), Decimal(-400))]


def test_positions_are_built_from_the_trips_that_remain():
    read = plan(confirmed_groups=groups("ABC"))
    legs = {id(leg) for position in read.positions for leg in position.legs}
    assert legs == {id(trip) for trip in read.trips}
    assert len(read.positions) == 9


def test_refused_trades_follow_the_rows_that_remain(monkeypatch):
    """Under reconstruction that refuses a sold option, A's short is refused and A and B's isn't."""
    real = rc.reconstruct
    monkeypatch.setattr(rc, "reconstruct",
                        lambda fills, **kw: real(fills, **{**kw, "short_options": False}))
    assert plan().skipped == ()
    assert len(plan(confirmed_groups=groups("A")).skipped) == 1
    assert plan(confirmed_groups=groups("AB")).skipped == ()


def test_the_file_with_all_three_confirmed_counts_its_rows_truly():
    read = plan(confirmed_groups=groups("ABC"))
    assert (read.rows_in, read.rows_parsed, read.rows_excluded) == (21, 18, 3)
    statuses = [r.status for r in read.rows]
    assert statuses.count("PARSED") == read.rows_parsed
    assert statuses.count("EXCLUDED") == read.rows_excluded
    assert read.rows_parsed + read.rows_excluded == read.rows_in
    assert {r.row_no for r in read.rows if r.status == "EXCLUDED"} == set(THE_COPY_OF.values())


def test_days_count_the_rows_that_remain():
    read = plan(confirmed_groups=groups("ABC"))
    assert [(d.trading_day[-2:], d.rows_after) for d in read.day_diffs] == [
        ("02", 6), ("03", 4), ("04", 4), ("05", 4)]


def test_a_day_that_lost_a_copy_shrank_against_the_reading_before():
    existing = {d.trading_day: d.rows_after for d in plan().day_diffs}
    read = pl.plan_import(TEXT, context=dataclasses.replace(CONTEXT, existing_days=existing),
                          confirmed_groups=groups("A"))
    by_day = {d.trading_day[-2:]: d for d in read.day_diffs}
    assert by_day["02"].diff is s.DayDiff.SHRUNK and by_day["02"].rows_after == 6
    assert by_day["03"].diff is s.DayDiff.IDENTICAL


def test_the_fixture_named_in_the_ticket_loses_what_was_confirmed():
    """Six rows, each twice over. Confirmed: bought 5100, sold 5120, and 300 units still open."""
    text = (DUPES / "duplicated_block.csv").read_text()
    names = {r.dup_group for r in plan(text).rows if r.dup_group}
    assert len(names) == 3
    read = plan(text, confirmed_groups=names)
    assert [t.gross_pnl for t in read.trips] == [Decimal(20)]
    assert read.open_positions == 1
    assert (read.rows_in, read.rows_parsed, read.rows_excluded) == (6, 3, 3)


def test_identical_rows_we_could_not_read_stay_accounted_for():
    """A group can be rows that never became fills. Confirmed, nothing goes missing."""
    bad = "2024-01-02,09:30:00,NOT A CONTRACT,BUY,MARGIN,NSE,Derivative,50,100.00,5000.00,Traded"
    text = TEXT + f"{bad}\n{bad}\n"
    group = next(r.dup_group for r in plan(text).rows if r.row_no == 22)
    read = plan(text, confirmed_groups={group})
    statuses = [r.status for r in read.rows]
    assert (read.rows_in, read.rows_parsed, read.rows_excluded) == (23, 21, 1)
    assert statuses.count("REJECTED") == 1
    assert bytes_of(read.trips) == bytes_of(plan(text).trips)


def test_a_group_not_in_the_file_changes_nothing():
    assert plan(confirmed_groups={"not-a-group"}).digest() == plan().digest()


# ---- rows and trips cannot disagree


def test_nothing_can_change_a_plans_rows_without_its_trips():
    assert not hasattr(pl.ImportPlan, "with_rows")
    assert not hasattr(pl, "with_confirmed_groups")


def test_the_digest_follows_what_was_confirmed():
    digests = {names: plan(confirmed_groups=groups(names)).digest()
               for r in range(4) for names in map("".join, itertools.combinations("ABC", r))}
    assert len(set(digests.values())) == len(digests), "every combination reads differently"
    for order in itertools.permutations("ABC"):
        assert plan(confirmed_groups=[GROUP[name] for name in order]).digest() == digests["ABC"]


def test_a_confirmation_moves_the_digest_even_when_no_trip_moved():
    """C takes away only an open position: no trade changes, and the reading still differs."""
    read = plan(confirmed_groups=groups("C"))
    assert bytes_of(read.trips) == bytes_of(plan().trips)
    assert read.digest() != plan().digest()


# ---- an unconfirmed suspected duplicate stays exactly as it is


@pytest.mark.parametrize(("source", "trips_sha256", "digest"), [
    ("this file",
     "35bc41bad8dee244ea14fecd7a4722cc1714f0dbd718c521c3864327eb7bc43d",
     "6afb45c7724c64b88a523d4dd8c370d44e684c55fb006e94d9e2c4dd81f0111c"),
    ("duplicated_block.csv",
     "c08db29ea6cbfdcc8576a916091f0d7bb12224deca1bdba54cb1069c3ce36f64",
     "be192e0c097f7d8af8664661c35a79dbfe5a69e8aecba5190b4f4e515a42c0bd"),
])
def test_a_file_with_none_confirmed_reads_byte_for_byte_as_before(source, trips_sha256, digest):
    """The two hashes were taken from the code before this change."""
    text = TEXT if source == "this file" else (DUPES / source).read_text()
    assert bytes_of(plan(text).trips) == trips_sha256
    assert plan(text).digest() == digest


def test_asking_for_no_group_is_the_same_reading():
    assert plan(confirmed_groups=()).digest() == plan().digest()


def test_confirming_one_group_leaves_the_others_suspected_and_counted():
    read = plan(confirmed_groups=groups("A"))
    by_row = {r.row_no: r for r in read.rows}
    for name in "BC":
        for row in (FIRST_ROW_OF[name], THE_COPY_OF[name]):
            assert by_row[row].status == "PARSED"
            assert by_row[row].flag is s.RowFlag.SUSPECTED_DUPLICATE
    assert by_row[1].flag is None and by_row[1].status == "PARSED"
    assert by_row[2].flag is s.RowFlag.TRADER_CONFIRMED_DUPLICATE
    assert by_row[2].status == "EXCLUDED"


# ---- through the route


def upload_it(client, engine, content=FILE, name="one.csv"):  # noqa: F811
    assert send(client, content, name, LAST_DAY_COMPLETE).status_code == 303
    return imports(engine)[-1].id


def confirm_named(client, engine, name: str):  # noqa: F811
    """Confirm a group from the current import's own page, as he would."""
    return confirm(client, imports(engine)[-1].id, GROUP[name])


def _stored(engine, import_id: int) -> dict:  # noqa: F811
    """What a reading says, without what differs by when it was written."""
    with make_session(engine) as sess:
        imp = sess.get(m.Import, import_id)
        trader = sess.get(m.Trader, imp.trader_id)
        newest: dict[str, m.Journal] = {}
        for journal in sess.scalars(select(m.Journal).where(m.Journal.trader_id == trader.id)
                                    .order_by(m.Journal.id)):
            newest[journal.period_start] = journal
        return {
            "counts": (imp.outcome, imp.rows_in, imp.rows_parsed, imp.rows_excluded,
                       imp.trips_reconstructed, imp.trips_refused),
            "rows": [(r.row_no, r.status, r.flag, r.dup_group) for r in sess.scalars(
                select(m.ImportRow).where(m.ImportRow.import_id == imp.id)
                .order_by(m.ImportRow.row_no))],
            "trips": [(t.trip_id, t.occurrence, t.position_id, t.trading_day, t.direction,
                       t.quantity, t.entry_price, t.exit_price, t.gross, t.net)
                      for t in sess.scalars(select(m.Trip).where(m.Trip.import_id == imp.id)
                                            .order_by(m.Trip.id))],
            "open": len(sess.scalars(select(m.OpenPosition)
                                     .where(m.OpenPosition.import_id == imp.id)).all()),
            "refused": [t.reason for t in sess.scalars(
                select(m.SkippedTrip).where(m.SkippedTrip.import_id == imp.id))],
            "days": persist.existing_days(sess, trader=trader, source_account=imp.source_account),
            "journals": {day: json.dumps(sec.own_facts(json.loads(j.sections)), sort_keys=True)
                         for day, j in newest.items()},
        }


def _journal_versions(engine) -> dict[str, int]:  # noqa: F811
    with make_session(engine) as sess:
        latest: dict[str, int] = {}
        for journal in sess.scalars(select(m.Journal).order_by(m.Journal.id)):
            latest[journal.period_start[-2:]] = journal.version_no
        return latest


def _journal_id(engine, day: str, version: int) -> int:  # noqa: F811
    with make_session(engine) as sess:
        return sess.scalars(select(m.Journal.id).where(
            m.Journal.period_start == f"2024-01-{day}", m.Journal.version_no == version)).one()


@pytest.fixture()
def all_at_once():
    return plan(confirmed_groups=groups("ABC"))


@pytest.mark.parametrize("order", list(itertools.permutations("ABC")), ids="".join)
def test_group_by_group_in_any_order_is_all_at_once(client, engine, order, all_at_once):  # noqa: F811
    upload_it(client, engine)
    for name in order:
        assert confirm_named(client, engine, name).status_code == 303

    stored = _stored(engine, imports(engine)[-1].id)
    assert [(t[3], t[4], t[8]) for t in stored["trips"]] == [
        (t.entry_ts.date().isoformat(), t.direction.value, t.gross_pnl)
        for t in all_at_once.trips]
    assert stored["open"] == all_at_once.open_positions == 0
    assert stored["counts"] == (all_at_once.outcome, 21, 18, 3, 9, 0)
    assert [(n, status, flag, group) for n, status, flag, group in stored["rows"]] == [
        (r.row_no, r.status, r.flag, r.dup_group) for r in all_at_once.rows]
    assert stored["days"] == {d.trading_day: d.rows_after for d in all_at_once.day_diffs}


def test_every_order_leaves_the_same_record_and_journals(engine):  # noqa: F811
    """Each order on its own trader, and everything stored read back. A trip's id names its
    trader, so ids are compared with the trader taken out."""
    seen = []
    for number, order in enumerate(itertools.permutations("ABC")):
        trader = sign_up(TestClient(create_app()), engine, f"U-{number}", f"order-{number}")
        assert send(trader, FILE, "one.csv", LAST_DAY_COMPLETE).status_code == 303
        for name in order:
            confirm_named(trader, engine, name)
        stored = _stored(engine, imports(engine)[-1].id)
        seen.append(TRIP_ID.sub("id", json.dumps(stored, default=str, sort_keys=True)))
    assert len(set(seen)) == 1


def test_figures_after_confirming_are_the_ones_worked_by_hand(client, engine):  # noqa: F811
    upload_it(client, engine)
    assert _stored(engine, imports(engine)[0].id)["counts"][4] == 10
    for name in "ABC":
        confirm_named(client, engine, name)
    newest = current(engine)
    with make_session(engine) as sess:
        trips = sess.scalars(select(m.Trip).where(m.Trip.import_id == newest.id)).all()
        assert sum((t.gross for t in trips), Decimal(0)) == Decimal(3550)
        trader = sess.scalars(select(m.Trader)).one()
        loaded, imp = loader.load_for(sess, trader)
        assert imp.id == newest.id and len(loaded) == 9
    assert newest.trips_reconstructed == 9


def test_the_earlier_reading_keeps_every_row_and_trade(client, engine):  # noqa: F811
    first = upload_it(client, engine)
    before = _stored(engine, first)
    for name in "ABC":
        confirm_named(client, engine, name)
    after = _stored(engine, first)
    for part in ("counts", "rows", "trips", "open", "refused"):
        assert after[part] == before[part], part


# ---- journals


def test_a_journal_gets_a_new_version_only_where_the_day_really_changed(client, engine):  # noqa: F811
    """C takes away only what was open, so no trade moves and no Journal is written."""
    upload_it(client, engine)
    assert _journal_versions(engine) == {"02": 1, "03": 1, "04": 1, "05": 1}
    confirm_named(client, engine, "C")
    assert _journal_versions(engine) == {"02": 1, "03": 1, "04": 1, "05": 1}
    confirm_named(client, engine, "A")
    versions = _journal_versions(engine)
    assert versions["05"] == 1, "the PUT's last day has nothing from any group"
    assert versions["02"] == 2


def test_answers_stay_with_their_day(client, engine):  # noqa: F811
    upload_it(client, engine)
    changes, stays = _journal_id(engine, "02", 1), _journal_id(engine, "05", 1)
    answer(client, engine, changes, field="note", value="A note on the changed day")
    answer(client, engine, stays, field="note", value="A note on the quiet day")
    for name in "ABC":
        confirm_named(client, engine, name)

    assert _journal_id(engine, "05", 1) == stays, "no new version"
    newer = _journal_id(engine, "02", 2)
    with make_session(engine) as sess:
        said = {journal: journal_fields.current(sess, journal=sess.get(m.Journal, journal),
                                                field="note", trip_id=None).value
                for journal in (stays, changes, newer)}
    assert said == {stays: "A note on the quiet day", changes: "A note on the changed day",
                    newer: "A note on the changed day"}
    assert "A note on the quiet day" not in client.get(f"/journals/{newer}").text


def test_a_journal_changed_by_a_confirmation_says_so(client, engine):  # noqa: F811
    """No later upload happened, so the page must not say one did."""
    upload_it(client, engine)
    confirm_named(client, engine, "A")
    page = words(client.get(f"/journals/{_journal_id(engine, '02', 2)}").text)
    assert FROM_A_CONFIRMATION in page
    assert "A later upload changed this period" not in page


# ---- what he reads


def test_the_review_says_what_happened_with_one_row(client, engine):  # noqa: F811
    upload_it(client, engine)
    response = confirm_named(client, engine, "A")
    page = words(client.get(response.headers["location"]).text)
    assert SET_ASIDE_ONE in page


def test_the_review_says_what_happened_with_three_rows_and_counts_them(client, engine):  # noqa: F811
    upload_it(client, engine)
    for name in "ABC":
        response = confirm_named(client, engine, name)
    page = words(client.get(response.headers["location"]).text)
    assert SET_ASIDE_THREE in page
    assert ("Rows in the file 21 rows Rows we could read 18 rows Rows set aside 3 rows "
            "Trades rebuilt 9 trades") in page


def test_a_review_with_nothing_confirmed_says_nothing_of_it(client, engine):  # noqa: F811
    first = upload_it(client, engine)
    assert "rebuilt without" not in client.get(f"/imports/{first}").text


def test_the_review_compares_with_the_last_reading_not_an_upload(client, engine):  # noqa: F811
    """A confirmation sent no file."""
    upload_it(client, engine)
    response = confirm_named(client, engine, "A")
    page = words(client.get(response.headers["location"]).text)
    assert "Since your last upload" not in page
    assert "Against the last reading of this file, 1 day changed" in page
    assert "fewer rows than before" in page


def test_the_rows_set_aside_page_gives_a_reason_for_each(client, engine):  # noqa: F811
    upload_it(client, engine)
    confirm_named(client, engine, "A")
    page = words(client.get("/mirror/fact/unread").text)
    assert "You told us this row repeats a trade already in the file." in page
    assert "None" not in page


def test_the_report_counts_rows_read_as_the_rows_that_remain(client, engine):  # noqa: F811
    upload_it(client, engine)
    for name in "ABC":
        confirm_named(client, engine, name)
    page = words(client.get("/mirror/fact/unread").text)
    assert "Rows in your file 21 Rows we read 18 Rows set aside 3" in page


def test_admin_does_not_call_a_set_aside_row_refused(client, engine):  # noqa: F811
    upload_it(client, engine)
    confirm_named(client, engine, "A")
    with make_session(engine) as sess:
        sess.execute(update(m.Trader).values(development_data=False))
        sess.commit()
        row = next(r for r in admin_view.build(sess, running_version="x", production=False)["rows"]
                   if r["login_id"] == "rikk")
    assert row["rows_read"] == "20 of 21"
    assert row["rows_refused"] == 0


def test_admin_shows_no_negative_count_for_a_row_the_old_code_counted_twice(client, engine):  # noqa: F811
    confirmed_as_it_used_to_be(client, engine, "1")
    with make_session(engine) as sess:
        sess.execute(update(m.Trader).values(development_data=False))
        sess.commit()
        row = next(r for r in admin_view.build(sess, running_version="x", production=False)["rows"]
                   if r["login_id"] == "rikk")
    assert row["rows_refused"] == 0


# ---- a confirmation adds no file


def test_a_confirmation_uses_up_no_upload(client, engine):  # noqa: F811
    upload_it(client, engine)
    for name in "ABC":
        confirm_named(client, engine, name)
    with make_session(engine) as sess:
        trader = sess.scalars(select(m.Trader)).one()
        assert limits._files_today(sess, trader) == 1
        assert len(sess.scalars(select(m.RawFile)).all()) == 1
        assert {i.raw_file_id for i in sess.scalars(select(m.Import))} == {
            sess.scalars(select(m.RawFile.id)).one()}


def test_a_confirmation_works_at_the_days_limit_and_leaves_the_next_file_alone(
    client, engine, monkeypatch,  # noqa: F811
):
    upload_it(client, engine)
    monkeypatch.setattr(k, "UPLOADS_PER_ACCOUNT_PER_DAY", 2)
    assert confirm_named(client, engine, "A").status_code == 303
    assert send(client, OTHER_FILE, "two.csv").status_code == 303, "the second file of two"
    assert send(client, b"anything", "three.csv").status_code == 429


# ---- only the file he is reading


def test_confirming_on_another_files_older_import_is_a_404(client, engine):  # noqa: F811
    """It would have made the older file the record the report reads."""
    first = upload_it(client, engine)
    upload_it(client, engine, OTHER_FILE, "two.csv")
    latest = current(engine).id
    before = counts(engine)
    response = confirm(client, first, GROUP["A"])
    assert response.status_code == 404
    assert counts(engine) == before
    assert current(engine).id == latest


def test_another_traders_import_is_a_404(client, engine):  # noqa: F811
    first = upload_it(client, engine)
    csrf_page = client.get(f"/imports/{first}").text
    assert GROUP["A"] in csrf_page
    other = sign_up(TestClient(create_app()), engine, "U-2", "someone-else")
    before = counts(engine)
    page = other.get("/upload").text
    response = other.post(f"/imports/{first}/confirm-duplicates",
                          data={"dup_group": GROUP["A"], "csrf_token": CSRF.search(page).group(1)},
                          follow_redirects=False)
    assert response.status_code == 404
    assert counts(engine) == before


def test_a_page_left_open_keeps_what_was_confirmed_since(client, engine):  # noqa: F811
    """Two tabs on the first reading, of the same file: the second confirmation is still added."""
    first = upload_it(client, engine)
    assert confirm(client, first, GROUP["A"]).status_code == 303
    assert confirm(client, first, GROUP["B"]).status_code == 303
    newest = imports(engine)[-1]
    assert newest.rows_excluded == 2
    assert current(engine).id == newest.id
    assert gross_stored(engine, newest.id) == Decimal(3550)


def gross_stored(engine, import_id: int) -> Decimal:  # noqa: F811
    with make_session(engine) as sess:
        return sum((t.gross for t in sess.scalars(
            select(m.Trip).where(m.Trip.import_id == import_id))), Decimal(0))


def test_a_double_click_reads_once(client, engine):  # noqa: F811
    first = upload_it(client, engine)
    assert confirm(client, first, GROUP["A"]).status_code == 303
    before = counts(engine)
    again = confirm(client, first, GROUP["A"])
    assert again.status_code == 303
    assert again.headers["location"] == f"/imports/{imports(engine)[-1].id}"
    assert counts(engine) == before


def test_a_stored_file_gone_missing_gets_the_failure_page(client, engine):  # noqa: F811
    first = upload_it(client, engine)
    stored_path(engine).unlink()
    before = counts(engine)
    response = confirm(client, first, GROUP["A"])
    assert response.status_code == 503
    assert "Your file was not read again" in response.text
    assert "We could not open your stored file" in response.text
    assert counts(engine) == before


# ---- imports already confirmed on the live database


def confirmed_as_it_used_to_be(client, engine, version: str | None) -> int:  # noqa: F811
    """A reading as the old code wrote it: rows marked, trips and counts from the whole file."""
    upload_it(client, engine)
    whole = plan()
    copies = set(THE_COPY_OF.values())
    rows = tuple(
        dataclasses.replace(r, status="EXCLUDED", flag=s.RowFlag.TRADER_CONFIRMED_DUPLICATE)
        if r.row_no in copies else
        dataclasses.replace(r, flag=None) if r.dup_group else r
        for r in whole.rows
    )
    stale = dataclasses.replace(whole, rows=rows, rows_excluded=3, reconstruction_version=version)
    with make_session(engine) as sess:
        trader = sess.scalars(select(m.Trader)).one()
        raw = sess.scalars(select(m.RawFile)).one()
        imp = persist.write_reading(sess, trader=trader, plan=stale, raw=raw, source_account="A")
        sess.commit()
        return imp.id


@pytest.mark.parametrize("version", ["1", None])
def test_an_already_confirmed_import_is_offered_the_reread(client, engine, version):  # noqa: F811
    stale = confirmed_as_it_used_to_be(client, engine, version)
    with make_session(engine) as sess:
        assert pl.out_of_date(sess.get(m.Import, stale))
    assert "Read this file again" in client.get("/account").text
    assert f"/imports/{stale}/read-again" in client.get("/account").text
    assert "Read this file again" in send(client, FILE, "one.csv").text


@pytest.mark.parametrize("version", ["1", None])
def test_the_reread_applies_what_he_confirmed(client, engine, version):  # noqa: F811
    stale = confirmed_as_it_used_to_be(client, engine, version)
    assert gross_stored(engine, stale) == Decimal(4350), "the wrong figures it held"
    assert read_again(client, stale).status_code == 303
    newest = imports(engine)[-1]
    assert newest.id != stale
    assert gross_stored(engine, newest.id) == Decimal(3550)
    assert (newest.rows_in, newest.rows_parsed, newest.rows_excluded,
            newest.trips_reconstructed) == (21, 18, 3, 9)
    with make_session(engine) as sess:
        assert not pl.out_of_date(sess.get(m.Import, newest.id))
    page = words(client.get(f"/imports/{newest.id}").text)
    assert SET_ASIDE_THREE in page
    assert "read with newer code" in page


def test_an_import_read_by_the_old_code_makes_no_claim_it_was_rebuilt(client, engine):  # noqa: F811
    """Its figures still hold those rows, so the sentence would be untrue."""
    stale = confirmed_as_it_used_to_be(client, engine, "1")
    assert "rebuilt without" not in client.get(f"/imports/{stale}").text


def test_a_file_with_nothing_confirmed_reads_the_same_after_the_offer(client, engine, monkeypatch):  # noqa: F811
    """The offer's cost: a re-read that changes no figure, and writes no Journal."""
    with monkeypatch.context() as older:
        older.setattr(rc, "RECONSTRUCTION_VERSION", "1")
        first = upload_it(client, engine)
    before = _stored(engine, first)
    versions = _journal_versions(engine)
    assert read_again(client, first).status_code == 303
    after = _stored(engine, imports(engine)[-1].id)
    assert after["trips"] == before["trips"]
    assert after["rows"] == before["rows"]
    assert _journal_versions(engine) == versions
