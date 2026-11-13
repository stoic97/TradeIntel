"""Where he reads a report built by older code, he is offered the re-read, and after it, told
what moved in rupees.

The file and its figures are test_read_again's, synthetic and worked by hand there: older
code refuses the sold option, so the option trades come to -600 and the five worst days
(all three days of the file) to -600; read again, both come to -100.
"""

from __future__ import annotations

import re
from decimal import Decimal

from services.production.api import formatting
from services.production.ctr.intake import pipeline as pl
from tests.unit.api.test_read_again import (  # noqa: F401
    A_LATER_FILE,
    client,
    engine,
    imports,
    read_again,
    send,
    upload_older,
    words,
)

OFFER = "Read your file again"
REPORT_PAGES = ("/", "/mirror", "/mirror/chapter/1", "/mirror/fact/worst-days",
                "/mirror/fact/worst-days/trades")
ALARMS = ("wrong", "error", "incorrect", "mistake", "warning", "out of date", "outdated")


def offers(page: str, import_id: int) -> bool:
    return f'action="/imports/{import_id}/read-again"' in page and OFFER in page


def test_every_page_he_reads_offers_the_reread(client, engine, monkeypatch):  # noqa: F811
    upload_older(client, monkeypatch)
    stale = imports(engine)[0].id
    for path in REPORT_PAGES:
        response = client.get(path)
        assert response.status_code == 200, path
        assert offers(response.text, stale), path


def test_the_offer_is_a_post_with_a_token(client, engine, monkeypatch):  # noqa: F811
    upload_older(client, monkeypatch)
    page = client.get("/mirror").text
    stale = imports(engine)[0].id
    found = re.search(rf'<form[^>]*method="post"[^>]*action="/imports/{stale}/read-again"[^>]*>(.*?)</form>',
                      page, re.DOTALL)
    assert found and 'name="csrf_token"' in found[1]


def test_a_stale_report_stays_readable(client, engine, monkeypatch):  # noqa: F811
    upload_older(client, monkeypatch)
    for path in REPORT_PAGES:
        page = words(client.get(path).text)
        assert "−₹" in page, path  # his figures are on it, beside the offer


def test_nothing_is_offered_when_the_report_is_current(client):  # noqa: F811
    send(client)
    for path in REPORT_PAGES:
        assert OFFER not in client.get(path).text, path


def test_the_offer_asks_the_one_check_that_decides_a_reread(client, engine, monkeypatch):  # noqa: F811
    """The same question the admin page and the read-again route ask, never the deploy."""
    upload_older(client, monkeypatch)
    monkeypatch.setattr(pl, "out_of_date", lambda imp: False)
    for path in REPORT_PAGES:
        assert OFFER not in client.get(path).text, path


def test_an_older_upload_page_offers_nothing(client, engine, monkeypatch):  # noqa: F811
    """Only the file the report reads can be read again, so only it is offered."""
    upload_older(client, monkeypatch)
    upload_older(client, monkeypatch, A_LATER_FILE, name="later.csv")
    first, second = imports(engine)
    assert not offers(client.get(f"/imports/{first.id}").text, first.id)
    assert offers(client.get("/mirror").text, second.id)


def test_the_offer_does_not_alarm(client, engine, monkeypatch):  # noqa: F811
    upload_older(client, monkeypatch)
    page = client.get("/mirror").text
    start = page.index('stale-line" role="note"')
    line = words(page[start:page.index("</form>", start)]).lower()
    assert not [w for w in ALARMS if w in line]
    assert "older reading" in line
    assert "nothing you told us is lost" in line


def test_after_the_reread_it_says_what_moved_in_rupees(client, engine, monkeypatch):  # noqa: F811
    upload_older(client, monkeypatch)
    response = read_again(client, imports(engine)[0].id)
    page = words(client.get(response.headers["location"]).text)
    was, now = formatting.rupees(Decimal(-600)), formatting.rupees(Decimal(-100))
    assert "What moved" in page
    assert f"Option trades {was} {now}" in page
    assert f"Your five worst days {was} {now}" in page


def test_after_the_reread_the_offer_is_gone(client, engine, monkeypatch):  # noqa: F811
    upload_older(client, monkeypatch)
    read_again(client, imports(engine)[0].id)
    for path in REPORT_PAGES:
        assert OFFER not in client.get(path).text, path


def test_an_ordinary_upload_says_nothing_moved(client):  # noqa: F811
    response = send(client)
    assert "What moved" not in words(client.get(response.headers["location"]).text)
