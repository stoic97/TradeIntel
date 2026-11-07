"""Home after sign-in leads with the verdict and "Days worth a look" [TICKET-830].

The history is the synthetic one in test_journals_worth_writing, worked by hand there. Here:

    All option trades. The ten days come to +100 -90 -190 -290 -390 -490 +10 +5 +110 +100,
    which is -1,125, across 27 trades.

    The three days to look at: 11 Feb 2025 (longest run, 5 trades, +10), 12 Feb 2025 (busiest,
    6 trades, +5), 10 Feb 2025 (the worst day, 2 trades, -490).
"""

from __future__ import annotations

import json
import os
import re
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from services.production.api.app import create_app
from services.production.db import models as m
from services.production.db.session import make_engine, make_session, run_migrations
from services.shared.schemas import scope_v1 as s
from tests.unit.api.test_journals_worth_writing import FILE
from tests.unit.api.test_upload import CSRF, sign_up


def _readable(html: str) -> str:
    return " ".join(re.sub(r"<[^>]+>", "", html).replace("&#39;", "'").split())


def _upload(client, body: str) -> None:
    token = CSRF.search(client.get("/upload").text).group(1)
    sent = client.post("/upload", files={"file": ("t.csv", body.encode(), "text/csv")},
                       data={"csrf_token": token}, follow_redirects=False)
    assert sent.status_code == 303, sent.text


@pytest.fixture()
def engine(scope_environment):
    built = make_engine(os.environ["SCOPE_DB"])
    run_migrations(built)
    return built


@pytest.fixture()
def client(engine):
    signed_in = sign_up(TestClient(create_app()), engine, "HOME-1", "home-1")
    _upload(signed_in, FILE)
    return signed_in


def _card(client) -> str:
    return re.search(r'<a class="scope-card on-navy".*?</a>', client.get("/").text,
                     flags=re.DOTALL).group(0)


def _rows(client) -> list[str]:
    return re.findall(r'<a class="latest__row".*?</a>', client.get("/").text, flags=re.DOTALL)


# ---------- The card ----------


def test_the_card_says_the_verdict(client):
    assert "Your option trades lost ₹1,125." in _readable(_card(client))


def test_the_card_no_longer_leads_with_the_share(client):
    card = _readable(_card(client))
    assert "of your losses" not in card
    assert "%" not in card


def test_the_two_screens_say_the_same_sentence(client):
    home = _readable(client.get("/").text)
    scope = client.get("/mirror").text
    said = _readable(re.search(r"<h1[^>]*>(.*?)</h1>", scope, flags=re.DOTALL).group(1))
    assert said == "Your option trades lost ₹1,125."
    assert said in home


def test_the_card_goes_to_the_report_and_says_so(client):
    card = _card(client)
    assert 'href="/mirror"' in card
    assert "Open your report" in _readable(card)
    assert "Open the Scope" not in card


def test_the_card_says_which_import_it_read(client):
    assert re.search(r"Your report · Import \d+ · \d\d \w{3} \d{4}", _readable(_card(client)))


def test_the_card_splits_options_from_the_rest_only_when_both_exist(client):
    assert "Stocks, ETFs and futures" not in _card(client)


# ---------- Days worth a look ----------


def test_days_worth_a_look_replaces_latest_journals(client):
    body = client.get("/").text
    assert '<h2 class="card-title">Days worth a look</h2>' in body
    assert "Latest Journals" not in body


def test_the_three_days_are_the_ones_the_report_named_in_its_order(client):
    days = [re.search(r"\d\d \w{3} \d{4}", _readable(r)).group(0) for r in _rows(client)]
    assert days == ["11 Feb 2025", "12 Feb 2025", "10 Feb 2025"]


@pytest.mark.parametrize(("index", "words"), [
    (0, ("Your longest losing run: 4 losses in a row", "5 trades", "+₹10")),
    (1, ("Your busiest day: 6 trades", "6 trades", "+₹5")),
    (2, ("This was one of your five worst days", "2 trades", "−₹490")),
])
def test_each_day_says_why_and_its_trades_and_rupees(client, index, words):
    row = _readable(_rows(client)[index])
    for word in words:
        assert word in row


def test_a_day_links_its_journal(client, engine):
    with make_session(engine) as sess:
        journal = sess.scalars(select(m.Journal).where(m.Journal.period_start == "2025-02-11")).one()
        wanted = journal.id
    assert f'href="/journals/{wanted}"' in _rows(client)[0]


def test_all_days_stays_a_way_to_the_rest(client):
    assert 'href="/journals">All days</a>' in client.get("/").text


def test_home_and_the_journal_list_agree_on_the_days(client):
    """Home shows the first three of the same list, so the two can't disagree."""
    on_home = re.findall(r'href="/journals/(\d+)"', "".join(_rows(client)))
    on_list = re.findall(r'href="/journals/(\d+)"', client.get("/journals").text)
    assert on_home == on_list[:3]


# ---------- What stays, and the empty states ----------


def test_the_upload_card_stays_word_for_word(client):
    text = _readable(client.get("/").text)
    assert "Upload new trades" in text
    assert "A new file replaces the days it covers." in text


def test_no_upload_yet_still_goes_where_the_trader_belongs(engine):
    fresh = sign_up(TestClient(create_app()), engine, "HOME-2", "home-2")
    assert fresh.get("/", follow_redirects=False).status_code == 303


def test_a_record_with_no_journal_yet_has_the_verdict_and_no_empty_list(engine):
    """One day, the file's last: it has a result but no Journal, so no list and no heading."""
    one_day = "\n".join(FILE.split("\n")[:1] + [
        row for row in FILE.split("\n")[1:] if row.startswith("2025-02-14")
    ]) + "\n"
    signed_in = sign_up(TestClient(create_app()), engine, "HOME-3", "home-3")
    _upload(signed_in, one_day)
    body = signed_in.get("/").text
    assert "Your option trades made ₹100." in _readable(body)
    assert "Days worth a look" not in body
    assert "Latest Journals" not in body


def test_journals_that_cover_more_than_a_day_keep_the_latest_under_their_own_name(client, engine):
    """A flag is about a day. With no single-day Journal, nothing can be named: latest it is."""
    with make_session(engine) as sess:
        trader = sess.scalars(select(m.Trader).where(m.Trader.login_id == "home-1")).one()
        imp = sess.scalars(select(m.Import)).one()
        for journal in sess.scalars(select(m.Journal)).all():
            sess.delete(journal)
        sess.add(m.Journal(
            trader_id=trader.id, import_id=imp.id, unit=s.JournalUnit.WEEK,
            period_start="2025-02-10", period_end="2025-02-14", version_no=1,
            generated_at=datetime.now(UTC), opened_at=None, trip_ids=json.dumps([]), sections="{}",
        ))
        sess.commit()
    body = client.get("/").text
    assert '<h2 class="card-title">Latest Journals</h2>' in body
    assert "Days worth a look" not in body
    assert "This was one of your five worst days" not in body
