"""The Mirror, told as the Scope: fixed order, the trades behind every fact, no claims.

The pages format what the metric functions return and compute nothing, so these
tests are about what a trader sees across Scope home, the four chapters and the
twelve fact pages: the chapters in the order the PRD fixes, every fact two taps from
home with every trade behind it, a thin sample said rather than shown as a bare
number, and no sentence that asserts a cause or recommends an action. They were the
long Mirror page's tests; each protects the same thing on the pages that replaced it.

The last of those is the one with teeth. v1 shows counted facts. The moment a
template says 'because' or 'you should', the product has made a claim it has not
earned and the research gate exists to prevent.
"""

from __future__ import annotations

import re

from fastapi.testclient import TestClient

from services.production.api import scope_map as S
from services.production.api.app import create_app
from services.production.db import models as m
from services.production.db.session import make_session

CSRF = re.compile(r'name="csrf_token"\s+value="([^"]+)"')

# Words the product never uses, from PRD 7.5 and the Workbook's never-use list.
# These are claims by their nature: there is no sentence in which the product may
# call a trader's behaviour tilt or name his edge.
NEVER_USED = [
    "tilt",
    "revenge",
    "emotional",
    "psychology",
    "disease",
    "cure",
    "edge",
    "alpha",
    "expectancy",
    "discipline",
    "mistake",
    "should have",
]

# Patterns that ASSERT a cause, a grade or a recommendation. Banned as claims --
# which is why the test exempts section 6.7, whose whole job is to say the product
# does none of these. A rule against making claims is not a rule against denying
# them, and the first version of this guard did not know the difference: it banned
# "caused" and "we recommend" while 6.7 printed "cause" and "recommends", so both
# tests passed by luck. "The cause of this was" would have sailed through.
CLAIM_PATTERNS = [
    r"\bbecause\b",
    r"\bcaused by\b",
    r"\bthe cause of\b",
    r"\bdue to\b",
    r"\bled to\b",
    r"\bresulted from\b",
    r"\byou should\b",
    r"\bwe recommend\b",
    r"\btry to\b",
    r"\bconsider \w+ing\b",
    r"\byour score\b",
    r"\bwe estimate\b",
    r"\bcost you\b",
]

SECTION_6_7 = "what we have not told you"


def every_page(client) -> dict[str, str]:
    """Scope home, the chapters and the facts, as served."""
    urls = [
        "/mirror",
        *(S.chapter_href(c.number) for c in S.CHAPTERS),
        *(S.fact_href(k, lens=False) for k in S.FACTS),
    ]
    return {url: client.get(url).text for url in urls}


def test_scope_home_renders(client):
    assert client.get("/mirror").status_code == 200


def test_the_chapters_appear_on_home_in_the_order_the_prd_fixes(client):
    body = client.get("/mirror").text
    links = re.findall(r'href="/mirror/chapter/(\d)\?', body)
    assert links == ["1", "2", "3", "4"]


def test_every_fact_is_two_taps_from_home(client):
    """Handoff 4: Home, a chapter, a fact - never more than three."""
    reached = set()
    for n in re.findall(r'href="(/mirror/chapter/\d)\?', client.get("/mirror").text):
        reached |= set(re.findall(r'href="/mirror/fact/([a-z-]+)\?enter=lens"', client.get(n).text))
    assert reached == set(S.FACTS)


def test_the_headline_figures_are_the_fixture_figures(client):
    pages = every_page(client)
    assert "96%" in pages["/mirror"], "share of total, in Home's centre"
    assert "24,000" in pages["/mirror/fact/worst-days"], "five worst days"
    assert "15.8%" in pages["/mirror/fact/strike"], "strike rate"
    assert "3.0" in pages["/mirror/fact/hold"], "holding ratio"
    assert ">10<" in pages["/mirror/fact/run"], "longest losing run"


def test_a_fact_lists_the_trades_behind_it(client):
    """Was: the two-straight-losses drawer. Now its fact page, with all 17."""
    body = client.get("/mirror/fact/down").text
    assert body.count('<article class="trade">') == 17, "the condition count"
    assert "02 Sep" in body


def test_a_record_belongs_to_its_owner_only(client, engine):
    from datetime import UTC, datetime

    from services.production.accounts import auth

    with make_session(engine) as sess:
        sess.add(
            m.Trader(
                display_name="Other",
                login_id="other",
                password_hash=auth.hash_password("a-long-enough-password"),
                created_at=datetime.now(UTC),
                development_data=True,
            )
        )
        sess.commit()
    other = TestClient(create_app())
    csrf = CSRF.search(other.get("/login").text).group(1)
    other.post(
        "/login",
        data={"login_id": "other", "password": "a-long-enough-password", "csrf_token": csrf},
        follow_redirects=False,
    )
    for url in ("/mirror", "/mirror/fact/down", "/mirror/chapter/1"):
        body = other.get(url).text
        assert "96%" not in body and '<article class="trade">' not in body, url


def test_figures_are_labelled_gross_when_fees_are_absent(client):
    for url, body in every_page(client).items():
        if url in ("/mirror/fact/unread", "/mirror/fact/not-told"):
            continue  # rows and a disclaimer: no rupee figure to label
        assert "before brokerage and taxes" in body, url


def test_the_record_carries_its_lineage(client):
    pages = every_page(client)
    for url in ("/mirror", "/mirror/chapter/4", "/mirror/fact/unread", "/mirror/fact/not-told"):
        assert "fixturesha" in pages[url], url


def test_a_trader_with_no_history_is_told_so_not_shown_zeroes(engine):
    from datetime import UTC, datetime

    from services.production.accounts import auth

    with make_session(engine) as sess:
        sess.add(
            m.Trader(
                display_name="Empty",
                login_id="empty",
                password_hash=auth.hash_password("a-long-enough-password"),
                created_at=datetime.now(UTC),
                development_data=True,
            )
        )
        sess.commit()
    client = TestClient(create_app())
    csrf = CSRF.search(client.get("/login").text).group(1)
    client.post(
        "/login",
        data={"login_id": "empty", "password": "a-long-enough-password", "csrf_token": csrf},
        follow_redirects=False,
    )
    for url in ("/mirror", "/mirror/chapter/1", "/mirror/fact/share"):
        body = client.get(url).text
        assert "0%" not in body, "a zero is a figure; absence is not"
        assert "upload" in body.lower(), url


def test_no_page_uses_a_never_use_word(client):
    """PRD 7.5's never-use list, on what actually renders: anywhere in the page."""
    for url, body in every_page(client).items():
        for word in NEVER_USED:
            assert word not in body.lower(), f"{url} says {word!r}"


def test_no_page_asserts_a_cause_a_grade_or_a_recommendation(client):
    """The claim patterns, everywhere except section 6.7's disclaimer.

    6.7 exists to say the product names no cause and recommends nothing, which it
    cannot say without using those words. Its fact page is all disclaimer; on
    chapter 4 it is the last card. Everything else must not.
    """
    for url, body in every_page(client).items():
        if url == "/mirror/fact/not-told":
            continue
        body = body.lower()
        if url == "/mirror/chapter/4":
            assert body.count(SECTION_6_7) >= 1, "6.7's card is missing"
            body = body.split("nothing above names a cause")[0]
        for pattern in CLAIM_PATTERNS:
            found = re.search(pattern, body)
            assert found is None, f"{url} claims: {found.group(0)!r}"


def test_section_6_7_disclaims_what_it_must(client):
    """A disclaimer that drifts upward into the body would be a claim."""
    disclaimer = client.get("/mirror/fact/not-told").text.lower()
    for word in ("cause", "score", "recommend"):
        assert word in disclaimer, f"6.7 must disclaim {word!r}"


def test_the_unqualified_symbol_R_never_appears(client):
    """Decision 15: figures divided by a budget are labelled in words."""
    for url, body in every_page(client).items():
        assert not re.search(r"\b\d+(\.\d+)?\s*R\b", body), f"{url}: an unqualified R multiple"


def test_times_are_shown_in_the_instrument_timezone_not_utc(client):
    """Found 19 Oct in the browser: every time read five and a half hours early.

    The database normalises to UTC, which is right -- a stored instant must be
    unambiguous. The Mirror then rendered the stored value raw, so a 09:20 trade
    appeared as 03:50 and the clock section reported hours 03 to 06 for a day that
    ran 09 to 12. The unit tests missed it because the fixture JSON carries +05:30
    offsets and never goes through the database.

    This is TD-026 on screen: the trading day and the hour must both come from the
    instrument profile's timezone (definitions_v1.md section 1).
    """
    clock = client.get("/mirror/fact/clock").text
    assert "09:00" in clock or "10:00" in clock, "the clock is in IST"
    assert "03:00" not in clock and "04:00" not in clock, "the clock is in UTC"

    worst = client.get("/mirror/fact/worst-days").text
    assert "09:20" in worst or "09:30" in worst, "entry times are in IST"
    assert "03:50" not in worst, "entry times are in UTC"


def test_the_worst_hour_is_the_hour_the_fixture_says(client):
    """Appendix A: hour 10 IST is the worst at -13,250, with 21 trades."""
    body = client.get("/mirror/fact/clock").text
    assert "13,250" in body
    assert "6,850" in body, "hour 09"
