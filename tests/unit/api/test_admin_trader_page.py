"""TICKET-875: /admin/traders/<id>, one timeline of what a trader did.

The trail around a report, never the report (ADR-007). Every marker below is planted where
a trader's trades, words, money or a broker's file name could leak, and the rendered page
and the statements behind it are both held to not carrying them. All of it is invented.
"""

from __future__ import annotations

import re
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, select

from services.production import demo
from services.production.api import scope_map as SM
from services.production.api.app import create_app
from services.production.db import models as m
from services.production.db.session import make_session
from services.shared.schemas import scope_v1 as s
from tests.unit.api.test_admin_page import (
    ADMIN,
    THEN,
    add_budget,
    add_consent,
    add_dwell,
    add_field_entry,
    add_journal,
    row_counts,
    row_of,
    signed_in,
    view,
)

FILE_NAME_MARKER = "ACCOUNT1100MARKER"
NOTE_MARKER = "TYPEDNOTEMARKER"
JOURNAL_MARKER = "JOURNALTEXTMARKER"
LEAVING_MARKER = "LEAVINGWORDSMARKER"
WTP_MARKER = "WOULDPAYWORDSMARKER"
ROW_MARKER = "RAWROWMARKER"
RUPEE_REFUSAL = "Refused, it adds up to ₹98,765."
FIGURES = ("4321", "876543", "55501", "55502", "55503", "55504", "98,765")
EVERY_MARKER = (FILE_NAME_MARKER, NOTE_MARKER, JOURNAL_MARKER, LEAVING_MARKER, WTP_MARKER,
                ROW_MARKER, *FIGURES)


@pytest.fixture()
def app(monkeypatch):
    monkeypatch.setenv("ADMIN_LOGIN_IDS", ADMIN)
    return create_app()


@pytest.fixture()
def engine(app):
    return app.state.engine


def at(hours: int):
    return THEN + timedelta(hours=hours)


def add_trader(engine, login_id, *, joined=THEN) -> int:
    with make_session(engine) as sess:
        trader = m.Trader(display_name=login_id.title(), login_id=login_id, created_at=joined,
                          password_hash="not-a-real-hash", development_data=False)
        sess.add(trader)
        sess.commit()
        return trader.id


def add_import(sess, trader_id, *, outcome=s.ImportOutcome.ACCEPTED_WITH_EXCLUSIONS, rejection=None,
               rows=(10, 8, 2), at=THEN, source="A", raw_file_id=None, reconstruction=None) -> m.Import:
    if raw_file_id is None:
        raw = m.RawFile(trader_id=trader_id, sha256=f"{trader_id}-{at.isoformat()}",
                        original_name=FILE_NAME_MARKER, size=1, stored_path="nowhere", uploaded_at=at)
        sess.add(raw)
        sess.flush()
        raw_file_id = raw.id
    imp = m.Import(trader_id=trader_id, raw_file_id=raw_file_id, source_account=source,
                   adapter_id="made-up", adapter_version="1", filemap_version="1",
                   code_version="aaa1111", reconstruction_version=reconstruction, outcome=outcome,
                   rejection_text=rejection, rows_in=rows[0], rows_parsed=rows[1],
                   rows_excluded=rows[2], fees_available=False, version_no=1, created_at=at)
    sess.add(imp)
    sess.flush()
    return imp


def statements_for_one_load(engine, client, address: str) -> list[str]:
    seen: list[str] = []

    def note(_conn, _cursor, statement, _params, _context, _many):
        seen.append(statement)

    event.listen(engine, "before_cursor_execute", note)
    try:
        assert client.get(address).status_code == 200
    finally:
        event.remove(engine, "before_cursor_execute", note)
    return seen


def seed(engine, trader_id: int) -> None:
    """One of everything the page reads, an hour apart, carrying every marker it can."""
    with make_session(engine) as sess:
        add_consent(sess, trader_id, at=at(1))
        imp = add_import(sess, trader_id, at=at(2), rows=(10, 7, 2))
        sess.add(m.ImportRow(import_id=imp.id, row_no=1, raw_text=f"made-up,{ROW_MARKER}",
                             status="PARSED", reason=None, flag=s.RowFlag.SUSPECTED_DUPLICATE))
        sess.add(m.Trip(import_id=imp.id, trip_id="t1", trading_day="2026-03-02",
                        gross=Decimal(55501), fees=Decimal(55502), net=Decimal(55503),
                        fees_available=False, risk_unit_source=s.RiskUnitSourceV1.UNAVAILABLE))
        add_import(sess, trader_id, at=at(3), outcome=s.ImportOutcome.REJECTED, rows=(1, 0, 0),
                   rejection=RUPEE_REFUSAL)
        add_dwell(sess, trader_id, "money", ms=120_000, at=at(4))
        answer = m.ChapterFeedback(trader_id=trader_id, chapter=1, answer="wrong",
                                   import_id=imp.id, answered_at=at(5))
        sess.add(answer)
        sess.flush()
        sess.add(m.ChapterFeedbackReason(feedback_id=answer.id, reason="wrong_facts", given_at=at(5)))
        sess.add(m.ReportFeedback(trader_id=trader_id, import_id=imp.id, answer="accurate",
                                  note=f"I made {NOTE_MARKER}", answered_at=at(6)))
        journal = add_journal(sess, trader_id, imp.id, opened=at(7))
        add_field_entry(sess, journal.id, value=JOURNAL_MARKER, at=at(8))
        add_budget(sess, trader_id, at=at(9))
        sess.add(m.WtpAnswer(trader_id=trader_id, journal_id=journal.id, answer="maybe",
                             free_text=WTP_MARKER, uploads_so_far=1, days_since_first_upload=1,
                             asked_at=at(10)))
        sess.add(m.LeavingCardAnswer(trader_id=trader_id, outcome="answered", answer=LEAVING_MARKER,
                                     copy_version="x", answered_at=at(11)))
        sess.add(m.GuessAnswer(trader_id=trader_id, answer="unknown", labels_version="x",
                               import_id=imp.id, answered_at=at(12)))
        raw = m.RawFile(trader_id=trader_id, sha256="charges", original_name=FILE_NAME_MARKER,
                        size=1, stored_path="nowhere", uploaded_at=at(13))
        sess.add(raw)
        sess.flush()
        sess.add(m.ChargeStatement(trader_id=trader_id, raw_file_id=raw.id, reader="x",
                                   days='{"2026-03-02": "55504"}', uploaded_at=at(13)))
        sess.commit()


def client_for(app, engine) -> TestClient:
    return signed_in(app, add_trader(engine, ADMIN))


def trail(app, engine, trader_id: int) -> str:
    response = client_for(app, engine).get(f"/admin/traders/{trader_id}")
    assert response.status_code == 200
    return response.text


def lines(app, engine, trader_id: int) -> list[str]:
    from services.production.api import trader_trail

    with make_session(engine) as sess:
        return [line["text"] for line in trader_trail.build(sess, trader_id)["lines"]]


# ---------- Who sees it, and that looking is on the record ----------


def test_a_signed_out_visitor_gets_the_same_404_as_any_unknown_address(app, engine):
    trader_id = add_trader(engine, "someone")
    client = signed_in(app)
    unknown, page = client.get("/no-such-page"), client.get(f"/admin/traders/{trader_id}")
    assert page.status_code == unknown.status_code == 404
    assert page.text == unknown.text


def test_another_trader_gets_the_same_404_even_for_their_own_page(app, engine):
    trader_id = add_trader(engine, "someone")
    client = signed_in(app, trader_id)
    unknown, page = client.get("/no-such-page"), client.get(f"/admin/traders/{trader_id}")
    assert page.status_code == 404
    assert page.text == unknown.text


@pytest.mark.parametrize("address", ["/admin/traders/not-a-number", "/admin/traders/1/",
                                     "/admin/traders/-1", "/admin/traders/999",
                                     "/admin/traders/99999999999999999999999"])
@pytest.mark.parametrize("who", ["signed out", "trader"])
def test_no_address_under_it_says_anything_is_there(app, engine, address, who):
    ids = {"signed out": None, "trader": add_trader(engine, "someone")}
    client = signed_in(app, ids[who])
    unknown, page = client.get("/no-such-page"), client.get(address)
    assert page.status_code == 404
    assert page.text == unknown.text
    assert "location" not in page.headers


@pytest.mark.parametrize("address", ["/admin/traders/not-a-number", "/admin/traders/1/",
                                     "/admin/traders/999", "/admin/traders/٣",
                                     "/admin/traders/99999999999999999999999"])
def test_an_admin_gets_a_plain_404_for_what_is_not_a_trader(app, engine, address):
    assert client_for(app, engine).get(address).status_code == 404


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"])
def test_another_method_is_a_404_too_not_a_405(app, engine, method):
    trader_id = add_trader(engine, "someone")
    response = signed_in(app, trader_id).request(method, f"/admin/traders/{trader_id}")
    assert response.status_code == 404
    assert "allow" not in response.headers


def test_a_view_writes_one_admin_action_naming_who_was_looked_at_and_nothing_else(app, engine):
    trader_id = add_trader(engine, "someone")
    seed(engine, trader_id)
    client = client_for(app, engine)
    before = row_counts(engine)
    assert client.get(f"/admin/traders/{trader_id}").status_code == 200
    after = row_counts(engine)
    assert {t: after[t] - before[t] for t in after if after[t] != before[t]} == {"admin_action": 1}
    with make_session(engine) as sess:
        action = sess.scalars(select(m.AdminAction)).one()
        assert action.action == "admin_view_trader"
        assert action.target == f"trader:{trader_id}"
        assert action.actor.startswith("trader:")


def test_a_refused_or_failed_look_writes_nothing(app, engine):
    trader_id = add_trader(engine, "someone")
    admin = client_for(app, engine)
    before = row_counts(engine)
    signed_in(app, trader_id).get(f"/admin/traders/{trader_id}")
    signed_in(app).get(f"/admin/traders/{trader_id}")
    admin.get("/admin/traders/999")
    admin.get("/admin/traders/not-a-number")
    assert row_counts(engine) == before


# ---------- Opened from the table ----------


def test_the_trader_table_links_to_each_page(app, engine):
    trader_id = add_trader(engine, "someone")
    assert row_of(view(app, engine), "someone")["href"] == f"/admin/traders/{trader_id}"
    page = client_for(app, engine).get("/admin").text
    assert f'<a href="/admin/traders/{trader_id}">someone</a>' in page


def test_the_page_links_back_to_the_table(app, engine):
    assert '<a href="/admin">' in trail(app, engine, add_trader(engine, "someone"))


# ---------- What it shows, oldest first ----------


def test_an_account_that_only_signed_up_has_that_one_line(app, engine):
    assert lines(app, engine, add_trader(engine, "someone")) == ["Signed up"]


def test_the_timeline_is_oldest_first_with_every_action(app, engine):
    trader_id = add_trader(engine, "someone")
    seed(engine, trader_id)
    assert lines(app, engine, trader_id) == [
        "Signed up",
        "Consent given: diagnosis, terms version 1",
        ("Uploaded a real file: 10 rows in, 7 read, 2 set aside, 1 refused, 1 duplicate flagged, "
         "reconstruction version not recorded"),
        ("A file was refused: 1 row in, 0 read, 0 set aside, 1 refused, 0 duplicates flagged, "
         "reconstruction version not recorded. No reason we can show"),
        f"Read {SM.FACTS['money'].title}: 2 min in all",
        "Answered Wrong on chapter 1: Wrong facts",
        "Answered Accurate on the whole report, with a note",
        "Opened a journal",
        "Wrote in a journal: 1 entry",
        "Set a budget",
        "Answered would pay: maybe, with a note",
        "Leaving card: answered",
        "Answered the guess",
        "Sent a charges file",
    ]


def test_each_line_says_when_in_ist(app, engine):
    trader_id = add_trader(engine, "someone")
    with make_session(engine) as sess:
        add_consent(sess, trader_id, at=at(1))
        sess.commit()
    page = trail(app, engine, trader_id)
    assert "02 Mar 2026 10:00" in page  # 04:30 UTC
    assert "02 Mar 2026 11:00" in page


def test_a_refusal_gives_its_reason_only_in_our_own_words(app, engine):
    trader_id = add_trader(engine, "someone")
    with make_session(engine) as sess:
        add_import(sess, trader_id, outcome=s.ImportOutcome.REJECTED, rows=(1, 0, 0),
                   rejection="This looks like a ledger, and it has no trade times. Send the other.")
        sess.commit()
    assert any("Reason: a ledger, no trade times" in line for line in lines(app, engine, trader_id))


def test_the_demo_is_shown_as_the_demo(app, engine):
    trader_id = add_trader(engine, "someone")
    with make_session(engine) as sess:
        add_import(sess, trader_id, source=demo.ACCOUNT, rows=(9, 9, 0))
        sess.commit()
    assert any(line.startswith("Loaded the demo: 9 rows in, 9 read")
               for line in lines(app, engine, trader_id))


def test_a_file_read_again_says_so_and_gives_its_reconstruction_version(app, engine):
    trader_id = add_trader(engine, "someone")
    with make_session(engine) as sess:
        first = add_import(sess, trader_id, rows=(5, 5, 0))
        add_import(sess, trader_id, rows=(5, 5, 0), at=at(1), raw_file_id=first.raw_file_id,
                   reconstruction="2")
        sess.commit()
    found = lines(app, engine, trader_id)
    assert any(line.startswith("Uploaded a real file: 5 rows in") for line in found)
    assert any(line.startswith("A file was read again: 5 rows in") and
               line.endswith("reconstruction version 2") for line in found)


def test_old_keys_add_to_the_fact_they_moved_to_and_other_surfaces_are_left_out(app, engine):
    trader_id = add_trader(engine, "someone")
    with make_session(engine) as sess:
        add_dwell(sess, trader_id, "strike", ms=60_000)
        add_dwell(sess, trader_id, "math", ms=60_000)
        add_dwell(sess, trader_id, "no-such-fact")
        add_dwell(sess, trader_id, "money", surface="journal_section")
        sess.commit()
    assert lines(app, engine, trader_id) == [
        "Signed up", f"Read {SM.FACTS['math'].title}: 2 min in all"]


def test_a_withdrawn_consent_is_shown_as_withdrawn(app, engine):
    trader_id = add_trader(engine, "someone")
    with make_session(engine) as sess:
        add_consent(sess, trader_id, granted=False)
        sess.commit()
    assert "Consent withdrawn: diagnosis, terms version 1" in lines(app, engine, trader_id)


def test_a_day_said_to_look_wrong_names_the_day_only(app, engine):
    trader_id = add_trader(engine, "someone")
    with make_session(engine) as sess:
        imp = add_import(sess, trader_id)
        sess.add(m.ReportFeedback(trader_id=trader_id, import_id=imp.id, answer="wrong",
                                  trading_day="2026-03-02", note=NOTE_MARKER, answered_at=at(1)))
        sess.commit()
    assert "Said 02 Mar 2026 looks wrong, with a note" in lines(app, engine, trader_id)


def test_a_leaving_card_only_shown_says_shown(app, engine):
    trader_id = add_trader(engine, "someone")
    with make_session(engine) as sess:
        sess.add(m.LeavingCardShown(trader_id=trader_id, copy_version="x", shown_at=at(1)))
        sess.commit()
    assert "Leaving card: shown" in lines(app, engine, trader_id)


def test_a_would_pay_only_asked_says_asked(app, engine):
    trader_id = add_trader(engine, "someone")
    with make_session(engine) as sess:
        imp = add_import(sess, trader_id)
        journal = add_journal(sess, trader_id, imp.id)
        sess.add(m.WtpAsked(trader_id=trader_id, journal_id=journal.id, asked_at=at(1)))
        sess.commit()
    assert "Asked would pay" in lines(app, engine, trader_id)


# ---------- Deletion ----------


def test_a_deleted_account_keeps_its_deletion_on_the_page_and_nothing_else(app, engine):
    with make_session(engine) as sess:
        sess.add(m.DeletionRecord(trader_id=7001, requested_at=at(1), completed_at=at(2),
                                  what_removed=f"everything {NOTE_MARKER}"))
        sess.commit()
    assert lines(app, engine, 7001) == ["Deletion requested", "Deletion completed"]
    page = trail(app, engine, 7001)
    assert NOTE_MARKER not in page
    assert "This account was deleted" in page


def test_a_deletion_before_this_account_began_belongs_to_an_earlier_holder_of_the_id(app, engine):
    trader_id = add_trader(engine, "someone")
    with make_session(engine) as sess:
        sess.add(m.DeletionRecord(trader_id=trader_id, requested_at=THEN - timedelta(days=1),
                                  completed_at=THEN - timedelta(days=1)))
        sess.commit()
    assert lines(app, engine, trader_id) == ["Signed up"]


def test_a_deletion_request_on_a_live_account_is_on_its_timeline(app, engine):
    trader_id = add_trader(engine, "someone")
    with make_session(engine) as sess:
        sess.add(m.DeletionRecord(trader_id=trader_id, requested_at=at(1), completed_at=None))
        sess.commit()
    assert lines(app, engine, trader_id) == ["Signed up", "Deletion requested"]


def test_with_no_sign_up_time_there_is_no_sign_up_line_and_no_deletion_is_claimed(app, engine):
    trader_id = add_trader(engine, "old", joined=None)
    with make_session(engine) as sess:
        sess.add(m.DeletionRecord(trader_id=trader_id, requested_at=at(1), completed_at=None))
        sess.commit()
    assert lines(app, engine, trader_id) == []
    assert "Nothing stored yet" in trail(app, engine, trader_id)


# ---------- What it never shows ----------


def test_the_rendered_page_carries_none_of_the_markers(app, engine):
    trader_id = add_trader(engine, "someone")
    seed(engine, trader_id)
    page = trail(app, engine, trader_id)
    for marker in EVERY_MARKER:
        assert marker not in page, marker
    assert "₹" not in page
    for field in ("p&amp;l", "p&l", "pnl", "gross", "capital", "premium", "instrument"):
        assert field not in page.lower(), field
    assert not re.search(r"\b(net|fees)\b", page.lower())


def test_the_seed_really_holds_every_marker_so_the_absence_means_something(app, engine):
    trader_id = add_trader(engine, "someone")
    seed(engine, trader_id)
    with make_session(engine) as sess:
        assert sess.scalar(select(m.ReportFeedback.note)) == f"I made {NOTE_MARKER}"
        assert sess.scalar(select(m.JournalFieldEntry.value)) == JOURNAL_MARKER
        assert sess.scalar(select(m.WtpAnswer.free_text)) == WTP_MARKER
        assert sess.scalar(select(m.LeavingCardAnswer.answer)) == LEAVING_MARKER
        assert FILE_NAME_MARKER in set(sess.scalars(select(m.RawFile.original_name)))
        assert ROW_MARKER in sess.scalar(select(m.ImportRow.raw_text))
        assert sess.scalar(select(m.Trip.net)) == Decimal(55503)


def test_a_load_never_asks_for_a_trade_a_name_or_anything_typed(app, engine):
    trader_id = add_trader(engine, "someone")
    seed(engine, trader_id)
    client = client_for(app, engine)
    said = " ".join(statements_for_one_load(engine, client, f"/admin/traders/{trader_id}")).lower()
    assert not re.search(r"\b(from|join)\s+trip\b", said)
    # IS NOT NULL asks only whether a note exists, as /admin does: that is all it may name them for.
    said = re.sub(r"[\w.]+ is not null", "", said)
    for column in ("original_name", "raw_text", "free_text", "journal_field_entry.value",
                   "wording_shown", "capital_amount", "risk_budget_declaration.value",
                   "charge_statement.days", "what_removed", "leaving_card_answer.answer",
                   "journal.sections", "journal.trip_ids"):
        assert not re.search(rf"\b{re.escape(column)}\b", said), column


def test_the_page_says_what_it_leaves_out(app, engine):
    page = trail(app, engine, add_trader(engine, "someone"))
    assert "never trades, figures, journal text, typed notes" in page
    assert "a visit that writes nothing" in page


def test_the_page_has_no_script_or_control(app, engine):
    page = trail(app, engine, add_trader(engine, "someone"))
    assert "<script" not in page
    for tag in ("<form", "<button", "<input", "<select"):
        assert tag not in page, tag


def test_the_module_reads_only_named_columns_never_a_whole_model():
    source = Path("services/production/api/trader_trail.py").read_text()
    assert not re.search(r"select\(m\.[A-Za-z]+\)", source)
    assert "sess.get(" not in source
    assert "m.Trip" not in source
    assert "original_name" not in source
