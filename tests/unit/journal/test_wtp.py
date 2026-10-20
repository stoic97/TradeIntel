"""The willingness-to-pay question, and when it may be asked (PRD 7.2, 11).

Asked once, in the THIRD Journal he opens -- not the third generated -- and not
before either a second upload or 14 days since the first, whichever comes first.

The three conditions exist because each blocks a different way of getting a
worthless answer. Opens rather than generations: a backfill generates sixty
Journals in a second and he has read none of them. A second upload or a fortnight:
asking a man who has used the product for four minutes what he would pay for it
produces a number about his politeness. And once: a question asked twice is a
request.

The answer is stored with uploads-so-far and days-since-first-upload, so a later
reader can tell whether it came from a man who had used the product for a fortnight
or one who clicked through three screens in an afternoon. Ten answers give a price
range; ten uninterpretable answers give nothing.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from services.production.db import models as m
from services.production.db.session import make_engine, make_session, run_migrations
from services.production.journal import constants as k
from services.production.journal import wtp
from services.shared.schemas import scope_v1 as s


@pytest.fixture()
def session():
    import os
    engine = make_engine(os.environ["SCOPE_DB"])
    run_migrations(engine)
    with make_session(engine) as sess:
        yield sess


def a_trader(session, first_upload_days_ago: int = 0) -> m.Trader:
    trader = m.Trader(display_name="F", login_id="f", password_hash="x",
                      created_at=datetime.now(UTC) - timedelta(days=first_upload_days_ago))
    session.add(trader)
    session.flush()
    return trader


def an_upload(session, trader, days_ago: int = 0) -> m.Import:
    when = datetime.now(UTC) - timedelta(days=days_ago)
    raw = m.RawFile(trader_id=trader.id, sha256=f"{trader.id}{days_ago}".ljust(64, "a"),
                    original_name="f", size=1, stored_path="/tmp/f", uploaded_at=when)
    session.add(raw)
    session.flush()
    imp = m.Import(trader_id=trader.id, raw_file_id=raw.id, source_account="A",
                   adapter_id="d", adapter_version="1", filemap_version="1",
                   code_version="c", outcome=s.ImportOutcome.ACCEPTED_PARTIAL_FIELDS,
                   rows_in=1, rows_parsed=1, rows_excluded=0, fees_available=False,
                   version_no=1, created_at=when)
    session.add(imp)
    session.flush()
    return imp


def journals(session, trader, imp, count: int, opened: int) -> list[m.Journal]:
    out = []
    for i in range(count):
        journal = m.Journal(
            trader_id=trader.id, import_id=imp.id, unit=s.JournalUnit.DAY,
            period_start=f"2026-09-{i + 1:02d}", period_end=f"2026-09-{i + 1:02d}",
            version_no=1, generated_at=datetime.now(UTC),
            opened_at=datetime.now(UTC) if i < opened else None,
            trip_ids=json.dumps([]), sections="{}")
        session.add(journal)
        out.append(journal)
    session.flush()
    return out


def test_a_backfill_alone_never_triggers_it(session):
    """Sixty Journals generated in a second, none of them read."""
    trader = a_trader(session)
    imp = an_upload(session, trader)
    journals(session, trader, imp, count=60, opened=0)
    session.commit()
    assert wtp.should_ask(session, trader=trader) is False


def test_two_opened_journals_are_not_enough(session):
    trader = a_trader(session, first_upload_days_ago=30)
    imp = an_upload(session, trader, days_ago=30)
    journals(session, trader, imp, count=10, opened=2)
    session.commit()
    assert wtp.should_ask(session, trader=trader) is False


def test_three_opened_after_a_fortnight_triggers_it(session):
    trader = a_trader(session, first_upload_days_ago=30)
    imp = an_upload(session, trader, days_ago=30)
    journals(session, trader, imp, count=10, opened=3)
    session.commit()
    assert wtp.should_ask(session, trader=trader) is True


def test_three_opened_on_the_first_day_does_not_trigger_it(session):
    """He has had the product for an afternoon."""
    trader = a_trader(session)
    imp = an_upload(session, trader, days_ago=0)
    journals(session, trader, imp, count=10, opened=3)
    session.commit()
    assert wtp.should_ask(session, trader=trader) is False


def test_a_second_upload_satisfies_the_floor_without_waiting(session):
    trader = a_trader(session)
    first = an_upload(session, trader, days_ago=1)
    an_upload(session, trader, days_ago=0)
    journals(session, trader, first, count=10, opened=3)
    session.commit()
    assert wtp.should_ask(session, trader=trader) is True


def test_the_floor_is_the_constant_not_a_literal(session):
    trader = a_trader(session)
    imp = an_upload(session, trader, days_ago=k.WTP_DAYS_SINCE_FIRST_UPLOAD - 1)
    journals(session, trader, imp, count=5, opened=3)
    session.commit()
    assert wtp.should_ask(session, trader=trader) is False


def test_it_is_asked_once(session):
    trader = a_trader(session)
    imp = an_upload(session, trader, days_ago=30)
    written = journals(session, trader, imp, count=10, opened=3)
    session.commit()
    assert wtp.should_ask(session, trader=trader) is True
    wtp.record(session, trader=trader, journal=written[0], answer="maybe",
               free_text="Depends what else is in it.")
    session.commit()
    assert wtp.should_ask(session, trader=trader) is False


def test_the_answer_is_stored_with_its_context(session):
    trader = a_trader(session)
    imp = an_upload(session, trader, days_ago=20)
    an_upload(session, trader, days_ago=2)
    written = journals(session, trader, imp, count=10, opened=3)
    session.commit()
    wtp.record(session, trader=trader, journal=written[0], answer="yes", free_text="")
    session.commit()

    answer = session.scalars(select(m.WtpAnswer)).one()
    assert answer.answer == "yes"
    assert answer.uploads_so_far == 2
    assert answer.days_since_first_upload == 20


def test_an_answer_outside_the_three_is_refused(session):
    trader = a_trader(session)
    imp = an_upload(session, trader, days_ago=30)
    written = journals(session, trader, imp, count=3, opened=3)
    session.commit()
    with pytest.raises(wtp.NotAnAnswer):
        wtp.record(session, trader=trader, journal=written[0], answer="probably",
                   free_text="")


def test_the_question_names_the_placeholder_price(session):
    assert str(k.WTP_PRICE_INR) in wtp.QUESTION
    assert "would you pay" in wtp.QUESTION.lower()
