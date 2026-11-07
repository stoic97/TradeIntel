"""A stored file read by older reconstruction can be read again, when he asks [TICKET-844].

Reconstruction runs at upload and pages read the stored trips of the latest import, so a
fix never reached anyone who had already uploaded, and sending the same bytes was refused.

The file below is synthetic. Its figures are worked by hand. One option, 50 units a time:

    Day 1  bought 5000, sold 4500   -500
           bought 5000, sold 4700   -300      the day -800
    Day 2  bought 5000, sold 5100   +100
           SOLD 6000, bought 5500   +500      a sold option
    Day 3  bought 5000, sold 5040    +40
           bought 5000, sold 5060    +60      the day +100, the file's last day

"Older code" here is reconstruction that refuses a sold option, as it once did:

    older:  5 trades, 1 refused, total -800 + 100 + 100        = -600
    newer:  6 trades, 0 refused, total -800 + 100 + 500 + 100  = -100

Day 3 is the last day and no download date is stated, so it has no Journal. Day 1 did not
change and Day 2 did, so a re-read writes a Journal version for Day 2 alone.
"""

from __future__ import annotations

import hashlib
import html
import re
import threading
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update

from services.production import demo
from services.production.api import admin_view, limits, routes_upload
from services.production.charges import record as charges
from services.production.ctr import reconstruct as rc
from services.production.ctr.intake import pipeline as pl
from services.production.db import models as m
from services.production.db.session import make_session
from services.production.journal import constants as k
from services.production.mirror import feedback as FB
from services.production.mirror import loader
from services.shared.schemas import scope_v1 as s
from tests.conftest import TEST_FILE_KEY
from tests.unit.api.test_upload import (  # noqa: F401
    CSRF,
    DUPES,
    PNL,
    client,
    engine,
    sign_up,
    upload,
)

HEADER = "Date,Time,Name,Buy/Sell,Order,Exchange,Segment,Quantity/Lot,Trade Price,Trade Value,Status"
OPTION = "NIFTY 25 JAN 20000 CALL"
READ_WITH_NEWER_CODE = "read with newer code"
FIGURES_MAY_DIFFER = "figures may differ"
OFFER_BUTTON = "Read this file again"
TABLES = (m.RawFile, m.Import, m.ImportRow, m.Trip, m.SkippedTrip, m.OpenPosition,
          m.TradingDayVersion, m.Journal, m.ChargeStatement, m.ReportFeedback)


def _row(day: str, time: str, side: str, value: int) -> str:
    return (f"{day},{time},{OPTION},{side},INTRADAY,NSE,Derivative,50,{value / 50:.2f},"
            f"{value:.2f},Traded")


FILE = "\n".join([
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
]).encode() + b"\n"
A_LATER_FILE = FILE + _row("2024-01-04", "10:30:00", "BUY", 5000).encode() + b"\n" \
    + _row("2024-01-04", "10:40:00", "SELL", 5010).encode() + b"\n"
NAME = "TRADE_HISTORY_one.csv"


# ---- helpers


def upload_older(client, monkeypatch, content=FILE, *, logic=True, name=NAME,  # noqa: F811
                 export_date=None):
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


def send(client, content=FILE, name=NAME, export_date=None):  # noqa: F811
    csrf = CSRF.search(client.get("/upload").text).group(1)
    data = {"csrf_token": csrf}
    if export_date:
        data["export_date"] = export_date
    return client.post("/upload", files={"file": (name, content, "text/csv")}, data=data,
                       follow_redirects=False)


def read_again(client, import_id: int, **kwargs):  # noqa: F811
    csrf = CSRF.search(client.get("/upload").text).group(1)
    return client.post(f"/imports/{import_id}/read-again", data={"csrf_token": csrf},
                       follow_redirects=False, **kwargs)


def imports(engine) -> list[m.Import]:  # noqa: F811
    with make_session(engine) as sess:
        return list(sess.scalars(select(m.Import).order_by(m.Import.id)).all())


def counts(engine) -> dict[str, int]:  # noqa: F811
    with make_session(engine) as sess:
        return {t.__tablename__: sess.scalar(select(func.count()).select_from(t)) for t in TABLES}


def current(engine):  # noqa: F811
    with make_session(engine) as sess:
        return loader.current_import(sess, sess.scalars(select(m.Trader)).first())


def trips_of(engine, import_id: int) -> list[m.Trip]:  # noqa: F811
    with make_session(engine) as sess:
        return list(sess.scalars(select(m.Trip).where(m.Trip.import_id == import_id)
                                 .order_by(m.Trip.id)).all())


def total(engine, import_id: int) -> Decimal:  # noqa: F811
    return sum((t.net for t in trips_of(engine, import_id)), Decimal(0))


def journals(engine) -> list[tuple[str, int]]:  # noqa: F811
    with make_session(engine) as sess:
        rows = sess.scalars(select(m.Journal).order_by(m.Journal.id)).all()
        return [(j.period_start, j.version_no) for j in rows]


def words(page: str) -> str:
    page = re.sub(r"<(script|style|svg)\b.*?</\1>", " ", page, flags=re.DOTALL)
    return html.unescape(" ".join(re.sub(r"<[^>]+>", " ", page).split()))


def ending(client) -> str:  # noqa: F811
    page = client.get("/mirror/fact/not-told")
    assert page.status_code == 200
    return words(page.text)


def stored_path(engine) -> Path:  # noqa: F811
    with make_session(engine) as sess:
        return Path(sess.scalars(select(m.RawFile)).first().stored_path)


def store_instead(engine, content: bytes) -> None:  # noqa: F811
    """The stored blob now holds other bytes under the same name: what a re-read will find."""
    stored_path(engine).write_bytes(Fernet(TEST_FILE_KEY.encode()).encrypt(content))


def assert_nothing_written(before, engine):  # noqa: F811
    assert counts(engine) == before


# ---- 1. out of date means reconstruction changed, not any deploy


def imp_like(**over):
    fields = {"reconstruction_version": rc.RECONSTRUCTION_VERSION, "adapter_id": "dhan_tradebook_v1",
              "adapter_version": "1", "code_version": "abc", "profile_versions": "{}"}
    return m.Import(**{**fields, **over})


def test_there_is_one_reconstruction_version():
    assert isinstance(rc.RECONSTRUCTION_VERSION, str) and rc.RECONSTRUCTION_VERSION


def test_a_new_import_carries_the_version(client, engine):  # noqa: F811
    send(client)
    assert imports(engine)[0].reconstruction_version == rc.RECONSTRUCTION_VERSION


def test_an_import_from_before_this_feature_reads_as_out_of_date():
    assert pl.out_of_date(imp_like(reconstruction_version=None))


def test_a_deploy_alone_does_not_make_an_import_out_of_date():
    assert not pl.out_of_date(imp_like(code_version="a-later-deploy"))


def test_a_new_version_makes_an_import_out_of_date(monkeypatch):
    stored = imp_like()
    monkeypatch.setattr(rc, "RECONSTRUCTION_VERSION", "a-later-version")
    assert pl.out_of_date(stored)


def test_a_new_file_map_makes_an_import_out_of_date():
    assert pl.out_of_date(imp_like(adapter_version="an-older-map"))


def test_a_profile_change_does_not_make_an_import_out_of_date():
    """A profile is read live when a page draws (loader.load_for), so it reaches him without
    a re-read, and asking him to re-read for one would change nothing he reads."""
    assert not pl.out_of_date(imp_like(profile_versions='{"NSE:NIFTY": "an-older-version"}'))


def test_the_migration_keeps_one_head():
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    assert len(ScriptDirectory.from_config(Config("alembic.ini")).get_heads()) == 1


# ---- 3. the refusal stays when nothing would change, and says which file


def test_the_same_current_file_is_refused_naming_it(client, engine):  # noqa: F811
    send(client)
    before = counts(engine)
    second = send(client, name="another name this time.csv")
    assert second.status_code == 400
    page = words(second.text)
    with make_session(engine) as sess:
        uploaded = sess.scalars(select(m.RawFile)).one().uploaded_at
    assert NAME in page
    assert uploaded.astimezone(limits.INDIA).strftime("%d %b %Y") in page
    assert "12 rows" in page
    assert "broker" not in page.split("You have already", 1)[1].split("Nothing was added")[0]
    assert "download it again" not in page
    assert OFFER_BUTTON not in page
    assert_nothing_written(before, engine)


def test_a_file_name_is_escaped_in_the_refusal(client):  # noqa: F811
    send(client, name="<b>mine</b>.csv")
    page = send(client).text
    assert "<b>mine</b>" not in page
    assert "&lt;b&gt;mine&lt;/b&gt;" in page


# ---- 2. asked, never silent


def test_the_refusal_offers_a_read_when_the_import_is_out_of_date(client, engine, monkeypatch):  # noqa: F811
    upload_older(client, monkeypatch)
    before = counts(engine)
    second = send(client)
    assert second.status_code == 400
    assert f'action="/imports/{imports(engine)[0].id}/read-again"' in second.text
    assert OFFER_BUTTON in second.text
    assert NAME in second.text
    assert "may change" in second.text
    assert_nothing_written(before, engine)


def test_the_offer_is_a_post_with_a_token(client, engine, monkeypatch):  # noqa: F811
    upload_older(client, monkeypatch)
    form = re.search(r'<form[^>]*read-again.*?</form>', send(client).text, re.DOTALL).group(0)
    assert 'method="post"' in form
    assert 'name="csrf_token"' in form


def test_no_get_changes_data(client, engine, monkeypatch):  # noqa: F811
    upload_older(client, monkeypatch)
    before = counts(engine)
    response = client.get(f"/imports/{imports(engine)[0].id}/read-again")
    assert response.status_code == 405
    assert_nothing_written(before, engine)


def test_a_read_without_a_token_is_refused(client, engine, monkeypatch):  # noqa: F811
    upload_older(client, monkeypatch)
    before = counts(engine)
    response = client.post(f"/imports/{imports(engine)[0].id}/read-again")
    assert response.status_code == 403
    assert_nothing_written(before, engine)


def test_the_account_row_of_the_current_import_offers_it(client, engine, monkeypatch):  # noqa: F811
    upload_older(client, monkeypatch)
    page = client.get("/account").text
    assert f'action="/imports/{imports(engine)[0].id}/read-again"' in page
    assert OFFER_BUTTON in page


def test_only_the_current_row_is_offered(client, engine, monkeypatch):  # noqa: F811
    upload_older(client, monkeypatch)
    upload_older(client, monkeypatch, A_LATER_FILE, name="later.csv")
    first, second = imports(engine)
    page = client.get("/account").text
    assert f'action="/imports/{second.id}/read-again"' in page
    assert f'action="/imports/{first.id}/read-again"' not in page


def test_the_account_row_offers_nothing_when_current(client):  # noqa: F811
    send(client)
    assert OFFER_BUTTON not in client.get("/account").text


def test_after_it_the_page_says_so(client, engine, monkeypatch):  # noqa: F811
    upload_older(client, monkeypatch)
    response = read_again(client, imports(engine)[0].id)
    assert response.status_code == 303
    page = words(client.get(response.headers["location"]).text)
    assert READ_WITH_NEWER_CODE in page
    assert FIGURES_MAY_DIFFER in page
    assert "Trades: 6 now, 5 before." in page


def test_an_ordinary_upload_says_no_such_thing(client):  # noqa: F811
    response = send(client)
    assert READ_WITH_NEWER_CODE not in client.get(response.headers["location"]).text


def test_a_refusal_of_an_older_file_says_what_the_record_reads(client, engine, monkeypatch):  # noqa: F811
    """The wrong file was picked more than once when two exports had near-identical names."""
    upload_older(client, monkeypatch)
    upload_older(client, monkeypatch, A_LATER_FILE, name="later.csv")
    before = counts(engine)
    page = words(send(client).text)
    assert NAME in page
    assert "later.csv" in page
    assert OFFER_BUTTON not in page
    assert_nothing_written(before, engine)


def test_a_refused_file_sent_again_says_it_could_not_be_read(client, engine):  # noqa: F811
    upload(client, content=PNL, name="pnl.csv")
    before = counts(engine)
    page = words(upload(client, content=PNL, name="pnl.csv").text)
    assert "pnl.csv" in page
    assert "could not read" in page
    assert "0 rows" not in page
    assert OFFER_BUTTON not in page
    assert_nothing_written(before, engine)


def test_a_charges_file_sent_as_a_tradebook_names_it_with_no_rows(client, engine):  # noqa: F811
    send(client)
    bytes_ = b"Date,Total Charges\n2024-01-02,10.00\n"
    with make_session(engine) as sess:
        trader = sess.scalars(select(m.Trader)).one()
        sess.add(m.RawFile(trader_id=trader.id, sha256=hashlib.sha256(bytes_).hexdigest(),
                           original_name="charges.csv", size=len(bytes_), stored_path="/tmp/c",
                           uploaded_at=datetime.now(UTC)))
        sess.commit()
    response = send(client, bytes_, "charges.csv")
    assert response.status_code == 400
    assert "charges.csv" in words(response.text)
    assert OFFER_BUTTON not in response.text


# ---- the ticket's gate: a stored file read under older logic, then re-read


def test_a_reread_shows_the_new_figures_and_leaves_the_old_import(client, engine, monkeypatch):  # noqa: F811
    upload_older(client, monkeypatch)
    old = imports(engine)[0]
    assert (old.trips_reconstructed, old.trips_refused) == (5, 1)
    assert total(engine, old.id) == Decimal(-600)
    old_trips = [(t.id, t.trip_id, t.net) for t in trips_of(engine, old.id)]
    with make_session(engine) as sess:
        old_rows = [(r.id, r.status, r.flag) for r in sess.scalars(
            select(m.ImportRow).where(m.ImportRow.import_id == old.id))]

    assert read_again(client, old.id).status_code == 303

    first, second = imports(engine)
    assert (second.trips_reconstructed, second.trips_refused) == (6, 0)
    assert total(engine, second.id) == Decimal(-100)
    assert second.version_no == 2
    assert second.supersedes_import_id == first.id
    assert second.reconstruction_version == rc.RECONSTRUCTION_VERSION
    assert current(engine).id == second.id

    assert first.trips_reconstructed == 5
    assert first.reconstruction_version is None
    assert [(t.id, t.trip_id, t.net) for t in trips_of(engine, first.id)] == old_trips
    with make_session(engine) as sess:
        assert old_rows == [(r.id, r.status, r.flag) for r in sess.scalars(
            select(m.ImportRow).where(m.ImportRow.import_id == old.id))]


def test_a_reread_writes_no_new_raw_file(client, engine, monkeypatch):  # noqa: F811
    upload_older(client, monkeypatch)
    read_again(client, imports(engine)[0].id)
    first, second = imports(engine)
    assert second.raw_file_id == first.raw_file_id
    assert counts(engine)["raw_file"] == 1


def test_the_report_reads_the_new_trades(client, engine, monkeypatch):  # noqa: F811
    upload_older(client, monkeypatch)
    assert "1 sold-option trade is not yet counted" in words(client.get("/mirror").text)
    read_again(client, imports(engine)[0].id)
    assert "not yet counted" not in words(client.get("/mirror").text)
    assert "sold-option" not in words(client.get("/mirror/chapter/1").text)
    with make_session(engine) as sess:
        trips, imp = loader.load_for(sess, sess.scalars(select(m.Trader)).one())
    assert imp.id == imports(engine)[1].id
    assert sum((t.net for t in trips), Decimal(0)) == Decimal(-100)


# ---- 5. confirmed duplicates


def dup_groups(page: str) -> list[str]:
    return re.findall(r'name="dup_group" value="([^"]+)"', page)


def confirm(client, import_id: int, group: str):  # noqa: F811
    page = client.get(f"/imports/{import_id}").text
    return client.post(f"/imports/{import_id}/confirm-duplicates",
                       data={"dup_group": group, "csrf_token": CSRF.search(page).group(1)},
                       follow_redirects=False)


def excluded_rows(engine, import_id: int) -> list[tuple[int, str, s.RowFlag | None]]:  # noqa: F811
    with make_session(engine) as sess:
        return [(r.row_no, r.status, r.flag) for r in sess.scalars(
            select(m.ImportRow).where(m.ImportRow.import_id == import_id,
                                      m.ImportRow.status == "EXCLUDED")
            .order_by(m.ImportRow.row_no))]


def test_a_reread_keeps_what_he_confirmed(client, engine, monkeypatch):  # noqa: F811
    """Two groups confirmed of three in the file: rows 4 and 5 stay set aside and only the
    third group is still asked about. Without the carry, every group comes back."""
    data = (DUPES / "duplicated_block.csv").read_bytes()
    upload_older(client, monkeypatch, data, logic=False)
    first = imports(engine)[0].id
    groups = dup_groups(client.get(f"/imports/{first}").text)
    assert len(groups) == 3

    with monkeypatch.context() as older:
        older.setattr(rc, "RECONSTRUCTION_VERSION", None, raising=False)
        confirm(client, first, groups[0])
        confirm(client, imports(engine)[-1].id, groups[1])
    confirmed = imports(engine)[-1]
    expected = [(4, "EXCLUDED", s.RowFlag.TRADER_CONFIRMED_DUPLICATE),
                (5, "EXCLUDED", s.RowFlag.TRADER_CONFIRMED_DUPLICATE)]
    assert excluded_rows(engine, confirmed.id) == expected

    assert read_again(client, confirmed.id).status_code == 303

    reread = imports(engine)[-1]
    assert reread.id != confirmed.id
    assert reread.rows_excluded == 2
    assert excluded_rows(engine, reread.id) == expected
    assert dup_groups(client.get(f"/imports/{reread.id}").text) == [groups[2]]


def test_a_second_confirmation_keeps_the_first(client, engine):  # noqa: F811
    """The path the re-read shares: it read the file afresh and carried only the new group."""
    upload(client, DUPES / "duplicated_block.csv")
    first = imports(engine)[0].id
    groups = dup_groups(client.get(f"/imports/{first}").text)
    confirm(client, first, groups[0])
    confirm(client, imports(engine)[-1].id, groups[1])
    assert imports(engine)[-1].rows_excluded == 2


# ---- 5. export date


def test_the_stated_download_date_carries(client, engine, monkeypatch):  # noqa: F811
    upload_older(client, monkeypatch, export_date="2024-01-10")
    assert ("2024-01-04", 1) in journals(engine), "the last day has its Journal on that date"
    read_again(client, imports(engine)[0].id)
    second = imports(engine)[1]
    assert second.export_date == "2024-01-10"
    assert second.export_date_source == "trader"
    assert [j for j in journals(engine) if j[0] == "2024-01-04"] == [("2024-01-04", 1)]


# ---- 5. journals


def test_a_new_version_only_where_a_day_really_changed(client, engine, monkeypatch):  # noqa: F811
    upload_older(client, monkeypatch)
    assert journals(engine) == [("2024-01-02", 1), ("2024-01-03", 1)]
    read_again(client, imports(engine)[0].id)
    assert journals(engine) == [("2024-01-02", 1), ("2024-01-03", 1), ("2024-01-03", 2)]


def test_a_reread_with_no_real_change_writes_no_journal(client, engine, monkeypatch):  # noqa: F811
    upload_older(client, monkeypatch, logic=False)
    before = journals(engine)
    assert before
    read_again(client, imports(engine)[0].id)
    assert len(imports(engine)) == 2
    assert journals(engine) == before


def journal_id(engine, day: str, version: int) -> int:  # noqa: F811
    with make_session(engine) as sess:
        return sess.scalars(select(m.Journal.id).where(
            m.Journal.period_start == day, m.Journal.version_no == version)).one()


def answer(client, engine, journal: int, **data):  # noqa: F811
    csrf = CSRF.search(client.get(f"/journals/{journal}").text).group(1)
    response = client.post(f"/journals/{journal}/field", data={**data, "csrf_token": csrf},
                           follow_redirects=False)
    assert response.status_code in (200, 303)


def test_answers_stay_with_their_day(client, engine, monkeypatch):  # noqa: F811
    upload_older(client, monkeypatch)
    same_day = journal_id(engine, "2024-01-02", 1)
    changed_day = journal_id(engine, "2024-01-03", 1)
    answer(client, engine, same_day, field="note", value="A note on the first day")
    answer(client, engine, changed_day, field="note", value="A note on the second day")

    read_again(client, imports(engine)[0].id)

    same_page = words(client.get(f"/journals/{same_day}").text)
    assert "A note on the first day" in same_page
    new_page = words(client.get(f"/journals/{journal_id(engine, '2024-01-03', 2)}").text)
    assert "A note on the second day" in new_page
    assert "A note on the first day" not in new_page


def test_a_trade_answer_follows_a_trade_that_did_not_change(client, engine, monkeypatch):  # noqa: F811
    upload_older(client, monkeypatch)
    old = imports(engine)[0]
    kept = next(t for t in trips_of(engine, old.id) if t.trading_day == "2024-01-03")
    answer(client, engine, journal_id(engine, "2024-01-03", 1), trip_id=kept.trip_id,
           rationale="Why I took the kept trade")
    read_again(client, old.id)
    new_page = client.get(f"/journals/{journal_id(engine, '2024-01-03', 2)}").text
    assert "Why I took the kept trade" in new_page  # it is the value of a form's field


def test_a_changed_journal_says_why(client, engine, monkeypatch):  # noqa: F811
    upload_older(client, monkeypatch)
    read_again(client, imports(engine)[0].id)
    page = words(client.get(f"/journals/{journal_id(engine, '2024-01-03', 2)}").text)
    assert "A later upload changed this period" not in page
    assert "read your file again with newer code" in page


def test_a_journal_that_did_not_change_says_nothing_is_left_uncounted(client, engine, monkeypatch):  # noqa: F811
    """It keeps the old import, whose refused count no longer describes his record."""
    upload_older(client, monkeypatch)
    day = journal_id(engine, "2024-01-02", 1)
    assert "sold-option" in words(client.get(f"/journals/{day}").text)
    read_again(client, imports(engine)[0].id)
    assert "sold-option" not in words(client.get(f"/journals/{day}").text)


# ---- 5. charges


def test_net_still_shows_after_a_reread(client, engine, monkeypatch):  # noqa: F811
    """Charges of 110 and 60 on days 1 and 2: net -100 - 170 = -270 against the new gross,
    on 2 of the 3 days of the upload."""
    upload_older(client, monkeypatch)
    with make_session(engine) as sess:
        trader = sess.scalars(select(m.Trader)).one()
        raw = sess.scalars(select(m.RawFile)).one()
        charges.record_statement(sess, trader, raw, "fixture", {
            "2024-01-02": Decimal(110), "2024-01-03": Decimal(60)})
        sess.commit()
    read_again(client, imports(engine)[0].id)
    with make_session(engine) as sess:
        trader = sess.scalars(select(m.Trader)).one()
        view = charges.build(sess, trader, loader.current_import(sess, trader))
    assert view.gross == Decimal(-100)
    assert view.net == Decimal(-270)
    assert (view.covered_days, view.trading_days) == (2, 3)
    assert "Net of those: −₹270" in words(client.get("/mirror").text)


# ---- 5. whole-report feedback


def test_the_whole_report_question_asks_again(client, engine, monkeypatch):  # noqa: F811
    upload_older(client, monkeypatch)
    old = imports(engine)[0].id
    with make_session(engine) as sess:
        trader = sess.scalars(select(m.Trader)).one()
        FB.record_report_answer(sess, trader=trader, import_id=old, answer="wrong", note=None)
        sess.commit()
    assert "Recorded. Thank you." in ending(client)
    read_again(client, old)
    assert "Recorded. Thank you." not in ending(client)
    with make_session(engine) as sess:
        assert FB.report_answer(sess, sess.scalars(select(m.Trader)).one(), old) is not None


# ---- 5. what changed: one file read again is not a new file


def test_the_ending_does_not_call_it_a_new_file(client, engine, monkeypatch):  # noqa: F811
    upload_older(client, monkeypatch)
    read_again(client, imports(engine)[0].id)
    page = ending(client)
    assert "What changed since your last file" not in page
    assert "in your last file" not in page
    assert "What changed when this file was read again" in page
    assert "Trades: 6 now, 5 before." in page
    assert "Trading days: 3 now, 3 before." in page


def test_the_ending_still_compares_two_files(client, engine):  # noqa: F811
    send(client)
    send(client, A_LATER_FILE, "later.csv")
    page = ending(client)
    assert "What changed since your last file" in page
    assert "in your last file" in page


def test_the_uploads_line_says_read_again(client, engine, monkeypatch):  # noqa: F811
    upload_older(client, monkeypatch)
    read_again(client, imports(engine)[0].id)
    page = words(client.get("/account").text)
    assert "Same file, read again with newer code." in page
    assert "+0" not in page
    assert "0 rows," not in page


def test_the_review_does_not_say_since_your_last_upload(client, engine, monkeypatch):  # noqa: F811
    upload_older(client, monkeypatch)
    read_again(client, imports(engine)[0].id)
    page = words(client.get(f"/imports/{imports(engine)[1].id}").text)
    assert "Since your last upload" not in page
    assert "no day changed" not in page
    assert "the row count is the same on every day" in page


def test_a_confirmation_on_current_code_does_not_claim_newer_code(client, engine):  # noqa: F811
    upload(client, DUPES / "duplicated_block.csv")
    first = imports(engine)[0].id
    response = confirm(client, first, dup_groups(client.get(f"/imports/{first}").text)[0])
    assert READ_WITH_NEWER_CODE not in client.get(response.headers["location"]).text


def test_a_confirmation_on_an_older_import_says_newer_code_read_it(client, engine, monkeypatch):  # noqa: F811
    """Confirming re-reads the file, so a trader on older code gets newer figures: asked or
    not, it is never silent."""
    upload_older(client, monkeypatch, (DUPES / "duplicated_block.csv").read_bytes(), logic=False)
    first = imports(engine)[0].id
    response = confirm(client, first, dup_groups(client.get(f"/imports/{first}").text)[0])
    assert READ_WITH_NEWER_CODE in words(client.get(response.headers["location"]).text)


# ---- 5. the demo


def load_demo(client, monkeypatch):  # noqa: F811
    with monkeypatch.context() as older:
        older.setattr(rc, "RECONSTRUCTION_VERSION", None, raising=False)
        csrf = CSRF.search(client.get("/upload").text).group(1)
        assert client.post("/upload/demo", data={"csrf_token": csrf},
                           follow_redirects=False).status_code == 303


def test_a_demo_read_again_stays_a_demo(client, engine, monkeypatch):  # noqa: F811
    load_demo(client, monkeypatch)
    response = send(client, demo.FILE.read_bytes(), demo.FILE_NAME)
    assert response.status_code == 400
    assert OFFER_BUTTON in response.text
    read_again(client, imports(engine)[0].id)
    _first, second = imports(engine)
    assert second.source_account == demo.ACCOUNT
    assert second.export_date == demo.EXPORT_DATE
    assert demo.LINE in words(client.get("/mirror").text)
    with make_session(engine) as sess:
        trader = sess.scalars(select(m.Trader)).one()
        assert not demo.has_real_record(sess, trader)
        assert demo.demo_import(sess, trader).id == second.id


def test_a_real_upload_after_a_demo_reread_has_nothing_behind_it(client, engine, monkeypatch):  # noqa: F811
    load_demo(client, monkeypatch)
    read_again(client, imports(engine)[0].id)
    upload(client, DUPES / "clean.csv")
    only = imports(engine)
    assert len(only) == 1
    assert only[0].source_account == "A"
    assert only[0].version_no == 1
    assert counts(engine)["raw_file"] == 1
    assert demo.LINE not in words(client.get(f"/imports/{only[0].id}").text)


# ---- 5. which file


def test_another_traders_import_is_a_404(client, engine, monkeypatch):  # noqa: F811
    upload_older(client, monkeypatch)
    theirs = imports(engine)[0].id
    before = counts(engine)
    sign_up(client, engine, "U-2", "someone-else")
    assert read_again(client, theirs).status_code == 404
    assert_nothing_written(before, engine)


def test_an_import_that_does_not_exist_is_a_404(client):  # noqa: F811
    assert read_again(client, 999).status_code == 404


def test_a_superseded_file_cannot_become_current(client, engine, monkeypatch):  # noqa: F811
    upload_older(client, monkeypatch)
    upload_older(client, monkeypatch, A_LATER_FILE, name="later.csv")
    first, second = imports(engine)
    before = counts(engine)
    assert read_again(client, first.id).status_code == 404
    assert_nothing_written(before, engine)
    assert current(engine).id == second.id


def test_a_rejected_file_cannot_become_current(client, engine, monkeypatch):  # noqa: F811
    upload_older(client, monkeypatch)
    upload(client, content=PNL, name="pnl.csv")
    good, rejected = imports(engine)
    before = counts(engine)
    assert read_again(client, rejected.id).status_code == 404
    assert_nothing_written(before, engine)
    assert current(engine).id == good.id


def test_consent_is_still_needed(client, engine, monkeypatch):  # noqa: F811
    upload_older(client, monkeypatch)
    token = CSRF.search(client.get("/upload").text).group(1)
    with make_session(engine) as sess:
        trader = sess.scalars(select(m.Trader)).one()
        sess.add(m.ConsentEvent(
            trader_id=trader.id, purpose=s.ConsentPurpose.DIAGNOSIS, scope="fixture",
            terms_version="fixture", granted=False, method="fixture", wording_shown="fixture",
            at=datetime.now(UTC)))
        sess.commit()
    before = counts(engine)
    response = client.post(f"/imports/{imports(engine)[0].id}/read-again",
                           data={"csrf_token": token}, follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/consent"
    assert_nothing_written(before, engine)


# ---- 5. limits: costly, so repeating it does nothing


def test_a_reread_is_not_counted_as_a_file(client, engine, monkeypatch):  # noqa: F811
    upload_older(client, monkeypatch)
    read_again(client, imports(engine)[0].id)
    with make_session(engine) as sess:
        assert limits._files_today(sess, sess.scalars(select(m.Trader)).one()) == 1


def test_a_reread_works_at_the_days_limit(client, engine, monkeypatch):  # noqa: F811
    upload_older(client, monkeypatch)
    monkeypatch.setattr(k, "UPLOADS_PER_ACCOUNT_PER_DAY", 1)
    assert read_again(client, imports(engine)[0].id).status_code == 303
    assert len(imports(engine)) == 2


def test_a_reread_when_already_current_writes_nothing(client, engine):  # noqa: F811
    send(client)
    before = counts(engine)
    response = read_again(client, imports(engine)[0].id)
    assert response.status_code == 303
    assert response.headers["location"] == f"/imports/{imports(engine)[0].id}"
    assert_nothing_written(before, engine)


def test_a_double_click_reads_once(client, engine, monkeypatch):  # noqa: F811
    upload_older(client, monkeypatch)
    first = imports(engine)[0].id
    one = read_again(client, first)
    after_one = counts(engine)
    two = read_again(client, first)
    assert one.headers["location"] == two.headers["location"]
    assert_nothing_written(after_one, engine)
    assert len(imports(engine)) == 2


def test_two_clicks_at_the_same_moment_read_once(client, engine, monkeypatch):  # noqa: F811
    upload_older(client, monkeypatch)
    first = imports(engine)[0].id
    token = CSRF.search(client.get("/upload").text).group(1)
    at_once = threading.Barrier(2)
    answers: list[int] = []

    def click():
        same_browser = TestClient(client.app, cookies=dict(client.cookies))
        at_once.wait()
        answers.append(same_browser.post(f"/imports/{first}/read-again",
                                         data={"csrf_token": token},
                                         follow_redirects=False).status_code)

    clicks = [threading.Thread(target=click) for _ in range(2)]
    for t in clicks:
        t.start()
    for t in clicks:
        t.join()
    assert answers == [303, 303]
    assert len(imports(engine)) == 2


# ---- 5. failure: the old import stays current, and it is said plainly


def assert_refused_in_words(response, before, engine, status):  # noqa: F811
    assert response.status_code == status
    page = words(response.text)
    assert "not read again" in page
    assert "Nothing changed" in page
    assert "Internal Server Error" not in page
    assert_nothing_written(before, engine)
    assert current(engine).id == imports(engine)[0].id


def test_a_missing_stored_file_is_said_plainly(client, engine, monkeypatch):  # noqa: F811
    upload_older(client, monkeypatch)
    before = counts(engine)
    stored_path(engine).unlink()
    assert_refused_in_words(read_again(client, imports(engine)[0].id), before, engine, 503)


def test_a_stored_file_the_key_cannot_open_is_said_plainly(client, engine, monkeypatch):  # noqa: F811
    upload_older(client, monkeypatch)
    before = counts(engine)
    stored_path(engine).write_bytes(b"not what was stored")
    assert_refused_in_words(read_again(client, imports(engine)[0].id), before, engine, 503)


def test_a_file_that_now_rejects_leaves_the_old_import(client, engine, monkeypatch):  # noqa: F811
    upload_older(client, monkeypatch)
    before = counts(engine)
    store_instead(engine, PNL)
    assert_refused_in_words(read_again(client, imports(engine)[0].id), before, engine, 422)


def test_a_file_that_now_rebuilds_no_trade_leaves_the_old_import(client, engine, monkeypatch):  # noqa: F811
    upload_older(client, monkeypatch)
    before = counts(engine)
    store_instead(engine, "\n".join(
        [HEADER, _row("2024-01-02", "09:30:00", "BUY", 5000)]).encode() + b"\n")
    assert_refused_in_words(read_again(client, imports(engine)[0].id), before, engine, 422)


def test_a_failure_writing_journals_leaves_the_old_import(client, engine, monkeypatch):  # noqa: F811
    upload_older(client, monkeypatch)
    before = counts(engine)

    def fails(*_args, **_kwargs):
        raise loader.MisdeclaredQuantityUnit("a size no one can hold")

    monkeypatch.setattr(routes_upload.gen, "for_import", fails)
    assert_refused_in_words(read_again(client, imports(engine)[0].id), before, engine, 422)


def test_a_reread_respects_the_production_gate(client, engine, monkeypatch):  # noqa: F811
    import dataclasses

    from services.production.ctr.adapters import filemap

    upload_older(client, monkeypatch)
    before = counts(engine)
    client.app.state.settings = dataclasses.replace(client.app.state.settings, production=True)

    def unchecked(file_map):
        raise filemap.UnverifiedFileMap("nobody has opened this broker's app")

    monkeypatch.setattr(filemap, "require_verified", unchecked)
    assert read_again(client, imports(engine)[0].id).status_code == 503
    assert_nothing_written(before, engine)


# ---- 6. the admin page stays true


def admin_view_of(engine):  # noqa: F811
    with make_session(engine) as sess:
        sess.execute(update(m.Trader).values(development_data=False))
        sess.commit()
    with make_session(engine) as sess:
        return admin_view.build(sess, running_version="the-deploy", production=False)


def test_the_admin_page_does_not_call_a_reread_an_upload(client, engine, monkeypatch):  # noqa: F811
    upload_older(client, monkeypatch)
    read_again(client, imports(engine)[0].id)
    text = str(admin_view_of(engine))
    assert "rikk uploaded a file" in text
    assert text.count("rikk uploaded a file") == 1
    assert "rikk had a file read again" in text


def test_a_re_read_clears_would_read_differently(client, engine, monkeypatch):  # noqa: F811
    upload_older(client, monkeypatch)
    assert admin_view_of(engine)["rows"][0]["reads_differently"] == "yes"
    read_again(client, imports(engine)[0].id)
    assert admin_view_of(engine)["rows"][0]["reads_differently"] == "no"
