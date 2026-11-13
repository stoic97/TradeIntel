"""TICKET-839: the losing run and worst-day pages link that day's journal.

Each worst-day block links the journal of its day; the run page links the journal of the
day the run began and asks what the trader remembers. A day with no journal shows no link.
The link opens the newest version. Figures here are synthetic.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

from sqlalchemy import select

from services.production.api import formatting
from services.production.db import models as m
from services.production.db.session import make_session
from services.shared.schemas import scope_v1 as s
from tests.unit.api.test_no_claims import CLAIM_PATTERNS, NEVER_USED

WORST = "/mirror/fact/worst-days"
RUN = "/mirror/fact/run"
BLOCK = re.compile(r'<details class="day-block" id="day-([^"]+)">(.*?)</details>', re.DOTALL)
# TICKET-903: the link names the page it came from, so the journal links back.
JOURNAL = re.compile(r'href="/journals/(\d+)\?from=(?:worst-days|run)"')
ASKS = re.compile(r"You lost (\d+) in a row on (\d{2} \w{3} \d{4})\. What do you remember\?")


def text_of(html: str) -> str:
    return " ".join(re.sub(r"<[^>]+>", " ", html).replace("&#39;", "'").split())


def _journals(engine, *, top: int = 1, skip: set[str] = frozenset()) -> None:
    """A DAY journal for every trading day in the fixture but `skip`; versions 1..top."""
    with make_session(engine) as sess:
        imp = sess.scalars(select(m.Import)).first()
        days = sorted(set(sess.scalars(select(m.Trip.trading_day))) - set(skip))
        for day in days:
            for version in range(1, top + 1):
                sess.add(m.Journal(
                    trader_id=imp.trader_id, import_id=imp.id, unit=s.JournalUnit.DAY,
                    period_start=day, period_end=day, version_no=version,
                    generated_at=datetime.now(UTC), trip_ids="[]", sections="{}"))
        sess.commit()


def _day_of(engine, journal_id: str) -> str:
    with make_session(engine) as sess:
        return sess.get(m.Journal, int(journal_id)).period_start


def blocks(html: str) -> dict[str, str]:
    found = dict(BLOCK.findall(html))
    assert len(found) == 5, "the fixture has five worst days"
    return found


# ---------- Worst-day blocks ----------


def test_each_worst_day_block_links_that_days_journal(client, engine):
    _journals(engine)
    for iso, block in blocks(client.get(WORST).text).items():
        opened = JOURNAL.findall(block)
        assert len(opened) == 1, iso
        assert _day_of(engine, opened[0]) == iso


def test_a_worst_day_without_a_journal_shows_no_link(client, engine):
    """A trader whose journals cover other days: that one block has no link, the rest do."""
    first = next(iter(blocks(client.get(WORST).text)))
    _journals(engine, skip={first})
    for iso, block in blocks(client.get(WORST).text).items():
        assert bool(JOURNAL.search(block)) == (iso != first), iso


def test_with_no_journals_at_all_the_worst_days_page_links_none(client):
    assert not JOURNAL.search(client.get(WORST).text)


def test_a_worst_day_link_opens_its_newest_version(client, engine):
    _journals(engine, top=2)
    with make_session(engine) as sess:
        latest = {j.id for j in sess.scalars(select(m.Journal).where(m.Journal.version_no == 2))}
    opened = {int(i) for i in JOURNAL.findall(client.get(WORST).text)}
    assert opened and opened <= latest


# ---------- The losing run page ----------


def test_the_run_page_links_the_journal_of_the_day_the_run_began_and_asks(client, engine):
    _journals(engine)
    page = client.get(RUN).text
    opened = JOURNAL.findall(page)
    assert len(opened) == 1
    asked = ASKS.search(text_of(page))
    assert asked, "the page asks what the trader remembers"
    assert formatting.day(_day_of(engine, opened[0])) == asked.group(2)
    assert int(asked.group(1)) >= 1


def test_the_run_page_without_a_journal_for_that_day_shows_no_link_and_no_question(client):
    page = client.get(RUN).text
    assert not JOURNAL.search(page)
    assert not ASKS.search(text_of(page))


def test_the_run_link_opens_the_newest_version(client, engine):
    _journals(engine, top=2)
    with make_session(engine) as sess:
        latest = {j.id for j in sess.scalars(select(m.Journal).where(m.Journal.version_no == 2))}
    opened = {int(i) for i in JOURNAL.findall(client.get(RUN).text)}
    assert opened and opened <= latest


# ---------- No new claim ----------


def test_the_new_words_ask_and_do_not_explain(client, engine):
    _journals(engine)
    for url in (WORST, RUN):
        said = text_of(client.get(url).text).lower()
        for word in NEVER_USED:
            assert not re.search(rf"\b{re.escape(word)}\b", said), (url, word)
        for pattern, why in CLAIM_PATTERNS:
            found = re.search(pattern, said)
            assert found is None, f"{url}: {why}: {found.group(0)!r}"