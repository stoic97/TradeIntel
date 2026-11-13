"""TICKET-867: /admin opens on who came, how far they got, and what's new since the last look.

Every account and date here is made up. "Last looked" is the admin's previous admin_view row,
which is already stored, so this collects nothing new.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from services.production import demo
from services.production.api import admin_view
from services.production.api import scope_map as SM
from services.production.db import models as m
from services.production.db.session import make_session
from services.shared.schemas import scope_v1 as s
from tests.unit.api.test_admin_page import (  # noqa: F401
    ADMIN,
    add_consent,
    add_dwell,
    add_import,
    add_journal,
    add_trader,
    admin_client,
    app,
    engine,
)

NOW = datetime(2026, 3, 20, 4, 30, tzinfo=UTC)
LONG_AGO = NOW - timedelta(days=30)
RECENT = NOW - timedelta(days=2)
LINES = ("Signed up", "Agreed to consent", "Tried the demo", "Uploaded a real file",
         "Read at least one fact", "Read all the facts", "Opened a journal",
         "Came back on a later day", "Asked would they pay", "Answered would they pay")


def built(engine, last_looked=None) -> dict:  # noqa: F811
    with make_session(engine) as sess:
        return admin_view.build(sess, running_version="x", production=False, now=NOW,
                                last_looked=last_looked)


def ladder(engine) -> dict[str, tuple[int, int]]:  # noqa: F811
    return {line["label"]: (line["all_time"], line["last_7_days"]) for line in built(engine)["ladder"]}


def add_person(engine, login, joined=LONG_AGO):  # noqa: F811
    return add_trader(engine, login, joined=joined)


def test_the_ladder_has_its_ten_lines_in_order(engine):  # noqa: F811
    assert [line["label"] for line in built(engine)["ladder"]] == list(LINES)


def test_an_old_sign_up_counts_for_all_time_and_not_the_last_7_days(engine):  # noqa: F811
    add_person(engine, "old")
    add_person(engine, "new", joined=RECENT)
    assert ladder(engine)["Signed up"] == (2, 1)


def test_consent_counts_a_grant_of_the_diagnosis_only(engine):  # noqa: F811
    agreed, withdrew = add_person(engine, "agreed"), add_person(engine, "withdrew")
    with make_session(engine) as sess:
        add_consent(sess, agreed, at=RECENT)
        add_consent(sess, withdrew, granted=False, at=RECENT)
        add_consent(sess, withdrew, purpose=s.ConsentPurpose.ENGINE_TESTING, at=RECENT)
        sess.commit()
    assert ladder(engine)["Agreed to consent"] == (1, 1)


def test_the_demo_and_a_real_file_are_separate_lines(engine):  # noqa: F811
    on_demo, on_real, refused = (add_person(engine, n) for n in ("on-demo", "on-real", "refused"))
    with make_session(engine) as sess:
        add_import(sess, on_demo, source=demo.ACCOUNT, at=RECENT, trips=1)
        add_import(sess, on_real, at=LONG_AGO, trips=1)
        add_import(sess, refused, outcome=s.ImportOutcome.REJECTED, rows=(1, 0, 0), at=RECENT)
        sess.commit()
    lines = ladder(engine)
    assert lines["Tried the demo"] == (1, 1)
    assert lines["Uploaded a real file"] == (2, 1), "a refused file was brought, as the File note says"


def test_reading_one_fact_and_all_of_them(engine):  # noqa: F811
    one, every = add_person(engine, "one"), add_person(engine, "every")
    with make_session(engine) as sess:
        add_dwell(sess, one, "money", at=LONG_AGO)
        for key in SM.FACTS:
            add_dwell(sess, every, key, at=RECENT)
        sess.commit()
    lines = ladder(engine)
    assert lines["Read at least one fact"] == (2, 1)
    assert lines["Read all the facts"] == (1, 1)


def test_read_all_dates_from_the_fact_that_finished_it(engine):  # noqa: F811
    trader = add_person(engine, "slow")
    with make_session(engine) as sess:
        for key in SM.FACTS:
            add_dwell(sess, trader, key, at=LONG_AGO)
        sess.commit()
    assert ladder(engine)["Read all the facts"] == (1, 0)


def test_a_journal_generated_by_the_upload_is_not_opened(engine):  # noqa: F811
    trader = add_person(engine, "someone")
    with make_session(engine) as sess:
        add_journal(sess, trader, add_import(sess, trader, at=LONG_AGO).id)
        sess.commit()
    assert ladder(engine)["Opened a journal"] == (0, 0)


def test_coming_back_means_a_later_day_in_india(engine):  # noqa: F811
    same_day = add_person(engine, "same-day")
    late = add_person(engine, "came-back")
    # 23:00 and 01:00 UTC are two days there, and both the morning of 2 Feb in India.
    same_in_india = add_person(engine, "same-in-india", joined=datetime(2026, 2, 1, 23, 0, tzinfo=UTC))
    # 18:00 and 19:00 UTC are one day there, and either side of midnight in India.
    next_in_india = add_person(engine, "next-in-india", joined=datetime(2026, 2, 1, 18, 0, tzinfo=UTC))
    with make_session(engine) as sess:
        add_consent(sess, same_day, at=LONG_AGO + timedelta(hours=1))
        add_consent(sess, late, at=RECENT)
        add_consent(sess, same_in_india, at=datetime(2026, 2, 2, 1, 0, tzinfo=UTC))
        add_consent(sess, next_in_india, at=datetime(2026, 2, 1, 19, 0, tzinfo=UTC))
        sess.commit()
    assert ladder(engine)["Came back on a later day"] == (2, 1)


def test_asked_and_answered_would_they_pay(engine):  # noqa: F811
    trader = add_person(engine, "someone")
    with make_session(engine) as sess:
        journal = add_journal(sess, trader, add_import(sess, trader, at=LONG_AGO).id)
        sess.add(m.WtpAsked(trader_id=trader, journal_id=journal.id, asked_at=RECENT))
        sess.add(m.WtpAnswer(trader_id=trader, journal_id=journal.id, answer="no", uploads_so_far=1,
                             days_since_first_upload=1, asked_at=LONG_AGO))
        sess.commit()
    lines = ladder(engine)
    assert lines["Asked would they pay"] == (1, 1)
    assert lines["Answered would they pay"] == (1, 0)


def test_a_development_account_moves_no_line(engine):  # noqa: F811
    add_trader(engine, "tester", dev=True, joined=RECENT)
    assert ladder(engine)["Signed up"] == (0, 0)


# ---------- New since you last looked ----------


def since(engine, last_looked) -> dict[str, int]:  # noqa: F811
    return {line["label"]: line["count"] for line in built(engine, last_looked)["new_since"]["lines"]}


def test_new_since_counts_only_what_came_after_the_last_look(engine):  # noqa: F811
    older, newer = add_person(engine, "older"), add_person(engine, "newer", joined=RECENT)
    with make_session(engine) as sess:
        add_import(sess, older, at=LONG_AGO)
        real = add_import(sess, newer, at=RECENT)
        add_import(sess, newer, source=demo.ACCOUNT, at=RECENT)
        add_import(sess, newer, outcome=s.ImportOutcome.REJECTED, rows=(1, 0, 0), at=RECENT)
        sess.add(m.ChapterFeedback(trader_id=newer, chapter=1, answer="wrong", import_id=real.id,
                                   answered_at=RECENT))
        sess.add(m.ReportFeedback(trader_id=newer, import_id=real.id, answer="accurate",
                                  answered_at=RECENT))
        sess.commit()
    assert since(engine, NOW - timedelta(days=7)) == {
        "Sign-ups": 1, "Demo loads": 1, "Real uploads": 1, "Refused files": 1, "Answers": 2}


def test_reading_a_file_again_is_not_a_new_upload(engine):  # noqa: F811
    trader = add_person(engine, "someone")
    with make_session(engine) as sess:
        first = add_import(sess, trader, at=LONG_AGO)
        add_import(sess, trader, at=RECENT, raw_file_id=first.raw_file_id)
        sess.commit()
    assert since(engine, NOW - timedelta(days=7))["Real uploads"] == 0


def test_a_first_look_says_so_and_counts_nothing_as_new(engine):  # noqa: F811
    add_person(engine, "someone", joined=RECENT)
    new_since = built(engine)["new_since"]
    assert new_since["last_looked"] is None
    assert new_since["lines"] == []


def test_the_route_reads_this_admins_previous_view(app, engine):  # noqa: F811
    client = admin_client(app, engine)
    first = client.get("/admin").text
    assert "This is your first look" in first
    second = client.get("/admin").text
    assert "New since you last looked" in second
    assert "This is your first look" not in second
    with make_session(engine) as sess:
        assert len(sess.scalars(select(m.AdminAction)).all()) == 2


def test_another_admins_view_is_not_my_last_look(app, engine, monkeypatch):  # noqa: F811
    client = admin_client(app, engine)
    with make_session(engine) as sess:
        sess.add(m.AdminAction(actor="trader:999999", action="admin_view", target=None, at=RECENT))
        sess.commit()
    assert "This is your first look" in client.get("/admin").text


# ---------- How it is drawn ----------


def test_new_since_is_at_the_very_top_and_the_ladder_comes_before_the_traders(app, engine):  # noqa: F811
    page = admin_client(app, engine).get("/admin").text
    assert page.index("This is your first look") < page.index("Who came and how far")
    assert page.index("Who came and how far") < page.index("Traders</h2>")


def test_the_cards_are_gone_and_nothing_unknowable_is_shown(app, engine):  # noqa: F811
    page = admin_client(app, engine).get("/admin").text
    assert "admin__cards" not in page
    assert "Reached the reveal" not in page
    assert "read none" not in page


def test_counts_only_no_percent_and_no_chart_in_the_ladder(app, engine):  # noqa: F811
    page = admin_client(app, engine).get("/admin").text
    section = page[page.index("Who came and how far"):page.index("Traders</h2>")]
    assert "%" not in section.split("System health")[0]
    assert "<svg" not in section


def test_said_wrong_keeps_a_plain_line(app, engine):  # noqa: F811
    assert "Said Wrong on any chapter" in admin_client(app, engine).get("/admin").text


def test_the_table_header_says_both_periods(app, engine):  # noqa: F811
    page = admin_client(app, engine).get("/admin").text
    assert re.search(r"All time</th>\s*<th[^>]*>Last 7 days", page)
