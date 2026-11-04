"""The upload asks when the file was downloaded [TICKET-799].

definitions_v1 section 1: a day is complete when the upload holds a later day, or the
export date is after it, and the trader states that date on the form, pre-filled with
the upload date. The form never asked, so every upload's last day stayed incomplete
and its Journal was never written.
"""

from __future__ import annotations

import re
from datetime import timedelta

from sqlalchemy import select

from services.production.api.routes_budget import _today
from services.production.db import models as m
from services.production.db.session import make_session
from tests.unit.api.test_upload import (  # noqa: F401 - fixtures used by name
    CSRF,
    DUPES,
    _two_days,
    client,
    engine,
)

LAST_DAY = "2026-10-15"  # the last day in _two_days()
FIELD = re.compile(r'name="export_date"[^>]*\bmax="([^"]+)"[^>]*\bvalue="([^"]+)"')


def send(client, content: bytes, **fields):  # noqa: F811
    csrf = CSRF.search(client.get("/upload").text).group(1)
    return client.post(
        "/upload",
        files={"file": ("tradebook.csv", content, "text/csv")},
        data={"csrf_token": csrf, **fields},
        follow_redirects=False,
    )


def journal_days(engine) -> list[str]:  # noqa: F811
    with make_session(engine) as sess:
        return sorted(j.period_start for j in sess.scalars(select(m.Journal)).all())


def the_import(engine) -> m.Import:  # noqa: F811
    with make_session(engine) as sess:
        return sess.scalars(select(m.Import).order_by(m.Import.id.desc())).first()


def test_the_form_starts_at_the_upload_date_and_stops_there(client):  # noqa: F811
    limit, value = FIELD.search(client.get("/upload").text).groups()
    assert limit == value == _today().isoformat()


def test_a_download_after_the_last_day_writes_its_journal(client, engine):  # noqa: F811
    send(client, _two_days(), export_date="2026-10-20")
    assert journal_days(engine) == ["2026-10-14", LAST_DAY]


def test_a_download_on_the_last_day_leaves_it_incomplete(client, engine):  # noqa: F811
    """The market may still have been open when he downloaded it."""
    send(client, _two_days(), export_date=LAST_DAY)
    assert journal_days(engine) == ["2026-10-14"]


def test_the_import_records_the_date_and_that_the_trader_stated_it(client, engine):  # noqa: F811
    send(client, _two_days(), export_date="2026-10-20")
    imp = the_import(engine)
    assert (imp.export_date, imp.export_date_source) == ("2026-10-20", "trader")


def test_a_post_with_no_date_stays_unknown(client, engine):  # noqa: F811
    send(client, _two_days())
    imp = the_import(engine)
    assert (imp.export_date, imp.export_date_source) == (None, None)
    assert journal_days(engine) == ["2026-10-14"]


def test_a_future_date_is_refused_and_nothing_is_written(client, engine):  # noqa: F811
    tomorrow = (_today() + timedelta(days=1)).isoformat()
    response = send(client, _two_days(), export_date=tomorrow)
    assert response.status_code == 400
    assert the_import(engine) is None
    assert FIELD.search(response.text) is not None


def test_something_that_is_not_a_date_is_refused(client, engine):  # noqa: F811
    response = send(client, _two_days(), export_date="last week")
    assert response.status_code == 400
    assert the_import(engine) is None


def test_a_refused_file_still_shows_the_date(client):  # noqa: F811
    send(client, _two_days(), export_date="2026-10-20")
    response = send(client, _two_days(), export_date="2026-10-20")
    assert response.status_code == 400
    assert FIELD.search(response.text) is not None


def test_confirming_duplicates_keeps_the_date_he_stated(client, engine):  # noqa: F811
    """A confirmation is a new reading of the same file, downloaded when it was."""
    response = send(client, (DUPES / "duplicated_block.csv").read_bytes(),
                    export_date="2026-10-20")
    location = response.headers["location"]
    page = client.get(location).text
    group = re.search(r'name="dup_group" value="([^"]+)"', page).group(1)
    client.post(f"{location}/confirm-duplicates",
                data={"dup_group": group, "csrf_token": CSRF.search(page).group(1)})
    imp = the_import(engine)
    assert imp.version_no == 2
    assert (imp.export_date, imp.export_date_source) == ("2026-10-20", "trader")
