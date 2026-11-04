"""What we read is a short receipt: what changed in a line, every day behind a toggle [TICKET-815].

A long table of mostly identical days is what stopped a trader reading on. A day that lost rows
is never silent (day_versions.py), so it stays outside the toggle. The result stays off this
page: the guess comes next and is asked before anything is shown.
"""

from __future__ import annotations

from sqlalchemy import select

from services.production.db import models as m
from services.production.db.session import make_session
from tests.unit.api.templating import template_env
from tests.unit.api.test_restyle_journal_pages import CONTEXT, day
from tests.unit.api.test_upload import _two_days, client, engine, upload  # noqa: F401

MORE = (
    b"2026-10-15,13:30:00,WIDGETOIL 19 NOV 5100 CALL,BUY,INTRADAY,MCX,"
    b"Commodity,100,53.00,5300.00,Traded\n"
    b"2026-10-15,14:30:00,WIDGETOIL 19 NOV 5100 CALL,SELL,INTRADAY,MCX,"
    b"Commodity,100,52.00,5200.00,Traded\n"
)


def latest_page(client, engine) -> str:  # noqa: F811
    with make_session(engine) as sess:
        newest = sess.scalars(select(m.Import).order_by(m.Import.id.desc())).first().id
    return client.get(f"/imports/{newest}").text


def later(**changes) -> str:
    context = {**CONTEXT["import_review.html#later"], **changes}
    return template_env().get_template("import_review.html").render(
        title="T", csrf_token="x", **context
    )


def test_a_first_upload_keeps_its_days_behind_a_toggle(client, engine):  # noqa: F811
    upload(client, content=_two_days())
    page = latest_page(client, engine)
    assert page.index("<details") < page.index("Every day, with its row count")


def test_the_toggle_says_how_many_days(client, engine):  # noqa: F811
    upload(client, content=_two_days())
    page = latest_page(client, engine)
    with make_session(engine) as sess:
        days = len(sess.scalars(select(m.TradingDayVersion)).all())
    assert f"Show all {days} days" in page


def test_a_first_upload_claims_no_change(client, engine):  # noqa: F811
    upload(client, content=_two_days())
    assert "Since your last upload" not in latest_page(client, engine)


def test_a_later_upload_says_what_changed(client, engine):  # noqa: F811
    upload(client, content=_two_days())
    upload(client, content=_two_days() + MORE)
    page = " ".join(latest_page(client, engine).split())
    assert "Since your last upload, 1 day changed: 15 Oct" in page


def test_what_changed_shows_before_the_toggle(client, engine):  # noqa: F811
    upload(client, content=_two_days())
    upload(client, content=_two_days() + MORE)
    page = latest_page(client, engine)
    assert page.index("Since your last upload") < page.index("<details") < page.index("Rows before")


def test_the_receipt_shows_no_result(client, engine):  # noqa: F811
    """The guess comes next, and it is asked before anything is shown."""
    upload(client, content=_two_days())
    assert "₹" not in latest_page(client, engine)


def test_nothing_changed_says_so():
    assert "Since your last upload, no day changed." in later(changed_days=[], shrunk_days=[])


def test_many_changes_are_counted_not_all_listed():
    page = later(
        changed_days=[f"2026-09-0{i}" for i in range(1, 6)], shrunk_days=[]
    )
    assert "5 days changed: 01 Sep, 02 Sep, 03 Sep and 2 more." in page


def test_a_day_that_lost_rows_is_never_behind_the_toggle():
    page = later(
        days=[day("2026-09-08", 90, 80, shrank=True)],
        changed_days=["2026-09-08"], shrunk_days=["2026-09-08"],
    )
    assert "08 Sep has fewer rows than before." in page
    assert page.index("fewer rows than before") < page.index("<details")


def test_two_days_that_lost_rows_read_in_the_plural():
    page = later(changed_days=["2026-09-07", "2026-09-08"], shrunk_days=["2026-09-07", "2026-09-08"])
    assert "07 Sep, 08 Sep have fewer rows than before." in page
