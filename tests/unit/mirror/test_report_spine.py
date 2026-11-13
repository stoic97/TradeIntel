"""TICKET-903: the report's spine. One order, one header, one way in and out of every page.

Rikk's ruling, 13 Nov 2026 (round 2 section N; mockups/nav_v2.html):
- The rail on every report page: the full path, "N of 10", the pages grouped by chapter,
  the ones read filled, each a link. All pages: every page, ticked if read, with its short
  answer, and Home, Journal and Account. Previous and Next in the same place on every page,
  each naming where it goes; Next says so when it crosses into a new chapter.
- On a phone, a bar at the bottom: Previous | N of 10, All pages | Next.
- The same header on every signed-in page (extends TICKET-860).
- Continue names the next unread page, on Home and on the report.
- A Journal opened from a report page offers the way back to it, and Home when the page
  that opened it isn't known; a report page offers the way into that day's questions.
- The first-time walk is upload, receipt, reveal, report: Limits and the checks page leave it.

The order is scope_map.CHAPTERS read straight through. It is restated here once, only to
check that the product reads it from one place. A page is read once its dwell "view" is kept.
"""

from __future__ import annotations

import hashlib
import re
from datetime import UTC, datetime
from html import unescape
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from services.production.api import scope_map as S
from services.production.api.app import create_app
from services.production.db import models as m
from services.production.db.session import make_session

ORDER = [f.key for c in S.CHAPTERS for f in c.facts]
TITLE = {f.key: f.title for c in S.CHAPTERS for f in c.facts}
CHAPTER_OF = {f.key: c.number for c in S.CHAPTERS for f in c.facts}
LAST = "You've read the report. Start with your days worth a look."
TEMPLATES = Path("services/production/api/templates")
REPORT_TEMPLATES = [*sorted((TEMPLATES / "scope").rglob("*.html")),
                    *(TEMPLATES / n for n in ("reveal.html", "budget.html", "home_signed_in.html",
                                              "journal.html"))]
CSRF = re.compile(r'name="csrf_token"\s+value="([^"]+)"')

TAG = re.compile(r"<[^>]+>")
ANCHOR = re.compile(r"<a\b([^>]*)>(.*?)</a>", re.DOTALL)
ATTR = re.compile(r'([\w-]+)(?:="([^"]*)")?')
MAIN_NAV = re.compile(r'<nav class="bottom-nav[^"]*" aria-label="Main">(.*?)</nav>', re.DOTALL)
TABS = [("/", "Home"), ("/mirror", "Scope"), ("/journals", "Journal"), ("/account", "Account")]

SIGNED_IN = [
    "/", "/mirror", *[f"/mirror/chapter/{c.number}" for c in S.CHAPTERS],
    *[f"/mirror/fact/{k}" for k in ORDER], "/mirror/fact/math/trades", "/mirror/reveal",
    "/journals", "/account", "/budget", "/upload", "/imports/1", "/imports/1/charges",
    "/eligibility", "/settings/consent",
]


def anchors(html: str) -> list[dict]:
    """Every link: its attributes, unescaped, and its text with the tags taken out."""
    out = []
    for attrs, body in ANCHOR.findall(html):
        link = {name: unescape(value) for name, value in ATTR.findall(attrs)}
        link["text"] = " ".join(unescape(TAG.sub(" ", body)).split())
        out.append(link)
    return out


def path(href: str) -> str:
    return urlsplit(href).path


def spine(html: str, name: str) -> str:
    """The inside of the element marked data-spine="name"."""
    found = re.search(rf'<(\w+)\b[^>]*data-spine="{name}"[^>]*>(.*?)</\1>', html, re.DOTALL)
    assert found, f'no data-spine="{name}" on the page'
    return found.group(2)


def page_of(client, key: str) -> str:
    r = client.get(f"/mirror/fact/{key}")
    assert r.status_code == 200, (key, r.status_code)
    return r.text


def read(engine, login_id: str, *keys: str) -> None:
    """Pages read, as the page itself records it: a dwell "view" under the page's key."""
    with make_session(engine) as sess:
        trader = sess.scalars(select(m.Trader).where(m.Trader.login_id == login_id)).one()
        for key in keys:
            sess.add(m.DwellEvent(trader_id=trader.id, surface="mirror_line", key=key,
                                  event="view", at=datetime.now(UTC), duration_ms=1500))
        sess.commit()


def expected_next(i: int) -> tuple[str, str]:
    if i == len(ORDER) - 1:
        return "/journals", LAST
    key = ORDER[i + 1]
    if CHAPTER_OF[key] != CHAPTER_OF[ORDER[i]]:
        return f"/mirror/fact/{key}", f"Next, chapter {CHAPTER_OF[key]}: {TITLE[key]}"
    return f"/mirror/fact/{key}", f"Next: {TITLE[key]}"


def labelled(links: list[dict], rel: str) -> list[tuple[str, str]]:
    return [(path(a.get("href", "")), a.get("aria-label", "")) for a in links if a.get("rel") == rel]


def continues(html: str) -> list[tuple[str, str]]:
    return [(path(a.get("href", "")), a["text"]) for a in anchors(html) if a["text"].startswith("Continue:")]


def backs(html: str) -> list[tuple[str, str]]:
    found = []
    for a in anchors(html):
        text = a["text"].replace("\u2039", "").strip()
        if text.startswith("Back to ") and text != "Back to your report":
            found.append((path(a.get("href", "")), text))
    return found


# ---------- Gate 1: one order, read from one place ----------


def test_scope_map_holds_the_one_order():
    pages = getattr(S, "PAGES", None)
    assert pages is not None, "scope_map.PAGES: the report's pages, in reading order"
    assert [f.key for f in pages] == ORDER


@pytest.mark.parametrize("key", ORDER)
def test_the_rail_runs_in_that_order_marks_this_page_and_counts_it(client, key):
    rail = spine(page_of(client, key), "rail")
    segs = [a for a in anchors(rail) if "data-page" in a]
    assert [a["data-page"] for a in segs] == ORDER
    assert [path(a.get("href", "")) for a in segs] == [f"/mirror/fact/{k}" for k in ORDER]
    assert [a["data-page"] for a in segs if a.get("aria-current") == "page"] == [key]
    words = " ".join(unescape(TAG.sub(" ", rail)).split())
    assert f"{ORDER.index(key) + 1} of {len(ORDER)}" in words
    assert any(a.get("href", "") == "#all-pages" and a["text"] == f"All {len(ORDER)} pages"
               for a in anchors(rail))
    assert "path__crumbs--short" not in rail, "the full path, no cut-off names"
    assert S.chapter(CHAPTER_OF[key]).name in words and TITLE[key] in words


@pytest.mark.parametrize("key", ORDER)
def test_previous_and_next_name_their_page_from_the_same_order(client, key):
    i = ORDER.index(key)
    links = anchors(spine(page_of(client, key), "pn"))
    want_prev = [] if i == 0 else [(f"/mirror/fact/{ORDER[i - 1]}", f"Previous: {TITLE[ORDER[i - 1]]}")]
    assert labelled(links, "prev") == want_prev
    assert labelled(links, "next") == [expected_next(i)]


@pytest.mark.parametrize("key", ORDER)
def test_all_pages_lists_every_page_with_its_short_answer(client, key):
    panel = spine(page_of(client, key), "all-pages")
    items = [a for a in anchors(panel) if "data-page" in a]
    assert [a["data-page"] for a in items] == ORDER
    for a in items:
        assert TITLE[a["data-page"]] in a["text"], a
        rest = a["text"].replace(TITLE[a["data-page"]], "", 1)
        rest = re.sub(r"^(\u2713|\d+)\s*", "", rest.strip()).strip()
        assert rest, f"{a['data-page']}: no short answer beside its name"
    others = {path(a.get("href", "")) for a in anchors(panel) if "data-page" not in a}
    assert {"/", "/journals", "/account"} <= others


def test_no_template_writes_a_report_link_or_a_step_label_of_its_own():
    offenders = []
    patterns = (r'href="/mirror/(?:fact|chapter)/', r"\bNext[:,]", r"\bContinue:", r"\bPrevious:")
    for file in REPORT_TEMPLATES:
        text = file.read_text(encoding="utf-8")
        offenders += [f"{file.relative_to(TEMPLATES)}: {p}" for p in patterns if re.search(p, text)]
    assert offenders == []


def test_scope_facts_decides_no_step_of_its_own():
    source = Path("services/production/api/scope_facts.py").read_text(encoding="utf-8")
    found = re.findall(r'["\'](?:Next[:,]|Chapter \{|Start with chapter|Continue)', source)
    assert found == [], "the order and its labels are scope_map's alone"


# ---------- Gate 2: every report page has a next step ----------


@pytest.mark.parametrize("n", [c.number for c in S.CHAPTERS])
def test_each_chapter_goes_on_to_its_first_page(client, n):
    first = S.chapter(n).facts[0].key
    html = client.get(f"/mirror/chapter/{n}").text
    assert any(path(a.get("href", "")) == f"/mirror/fact/{first}" and a["text"] == f"Next: {TITLE[first]}"
               for a in anchors(html))


def test_what_we_read_and_the_last_page_have_a_way_on(client):
    assert labelled(anchors(spine(page_of(client, "unread"), "pn")), "next")
    last = anchors(spine(page_of(client, ORDER[-1]), "pn"))
    assert labelled(last, "next") == [("/journals", LAST)]


# ---------- Gate 3: one header, and the report's own bar on a phone ----------


@pytest.mark.parametrize("url", SIGNED_IN)
def test_every_signed_in_page_has_the_one_header(client, url):
    r = client.get(url)
    assert r.status_code == 200, (url, r.status_code)
    navs = MAIN_NAV.findall(r.text)
    assert len(navs) == 1, f"{url}: {len(navs)} main navs"
    tabs = [(a.get("href", ""), a["text"]) for a in anchors(navs[0])
            if "bottom-nav__item" in a.get("class", "")]
    assert tabs == TABS, url
    assert "home-bar" not in r.text, f"{url}: the separate Home bar is retired"


@pytest.mark.parametrize("url", SIGNED_IN)
def test_only_a_report_page_has_the_report_bar(client, url):
    is_report = url.startswith("/mirror/fact/") and url.count("/") == 3
    assert ('data-spine="rbar"' in client.get(url).text) == is_report, url


def test_the_report_bar_on_a_phone(client):
    i = ORDER.index("run")
    links = anchors(spine(page_of(client, "run"), "rbar"))
    assert labelled(links, "prev") == [(f"/mirror/fact/{ORDER[i - 1]}", f"Previous: {TITLE[ORDER[i - 1]]}")]
    assert labelled(links, "next") == [expected_next(i)]
    middle = [a for a in links if a.get("href", "") == "#all-pages"]
    assert len(middle) == 1
    assert f"{i + 1} of {len(ORDER)}" in middle[0]["text"] and "All pages" in middle[0]["text"]


def test_the_kits_stylesheet_is_untouched():
    ours = Path("services/production/api/static/css/components.css").read_bytes()
    kit = Path("docs/design/scope-kit/static/css/components.css").read_bytes()
    assert hashlib.sha256(ours).hexdigest() == hashlib.sha256(kit).hexdigest()


def test_the_handoff_says_what_903_changed():
    handoff = Path("docs/product/scope_engineering_handoff_v1.md").read_text(encoding="utf-8")
    assert "next/previous fact" not in handoff
    assert "TICKET-903" in handoff


# ---------- Gate 4: Continue names the next unread page ----------


def test_continue_names_the_first_page_before_anything_is_read(client):
    for url in ("/", "/mirror"):
        assert continues(client.get(url).text) == [
            (f"/mirror/fact/{ORDER[0]}", f"Continue: {TITLE[ORDER[0]]}")], url


def test_continue_moves_to_the_first_page_not_yet_read(client, engine):
    read(engine, "fx", ORDER[0], ORDER[1], ORDER[3])
    for url in ("/", "/mirror"):
        assert continues(client.get(url).text) == [
            (f"/mirror/fact/{ORDER[2]}", f"Continue: {TITLE[ORDER[2]]}")], url


def test_a_view_kept_under_an_old_key_counts(client, engine):
    read(engine, "fx", "worst-days", "best-worst-trades")  # the long page's key for money
    assert continues(client.get("/mirror").text) == [
        ("/mirror/fact/math", f"Continue: {TITLE['math']}")]


def test_with_every_page_read_continue_goes_away(client, engine):
    read(engine, "fx", *ORDER)
    for url in ("/", "/mirror"):
        assert continues(client.get(url).text) == [], url
    assert any(path(a.get("href", "")) == "/mirror" for a in anchors(client.get("/").text))


def test_the_rail_and_all_pages_fill_the_pages_read(client, engine):
    read(engine, "fx", "worst-days", "money")
    html = page_of(client, "math")
    for part in ("rail", "all-pages"):
        items = [a for a in anchors(spine(html, part)) if "data-page" in a]
        assert [a["data-page"] for a in items if "data-read" in a] == ["worst-days", "money"], part


# ---------- Gate 5: report <-> Journal, both ways ----------


@pytest.fixture()
def demo(engine):
    """A signed-in trader with the synthetic demo file, which has Journals (README rule 1)."""
    from tests.unit.api.test_upload import sign_up
    c = sign_up(TestClient(create_app()), engine, "S-903", "spine903")
    token = CSRF.search(c.get("/upload").text).group(1)
    assert c.post("/upload/demo", data={"csrf_token": token},
                  follow_redirects=False).status_code == 303
    return c


def _a_journal(engine) -> int:
    with make_session(engine) as sess:
        trader = sess.scalars(select(m.Trader).where(m.Trader.login_id == "spine903")).one()
        return sess.scalars(select(m.Journal.id).where(m.Journal.trader_id == trader.id)
                            .order_by(m.Journal.id)).first()


def test_a_journal_opened_from_a_report_page_offers_the_way_back(demo, engine):
    jid = _a_journal(engine)
    assert backs(demo.get(f"/journals/{jid}?from=run").text) == [
        ("/mirror/fact/run", f"Back to {TITLE['run']}")]


def test_a_journal_from_anywhere_else_goes_back_home(demo, engine):
    jid = _a_journal(engine)
    for url in (f"/journals/{jid}", f"/journals/{jid}?from=nope", f"/journals/{jid}?from=/admin"):
        assert backs(demo.get(url).text) == [("/", "Back to Home")], url


def test_report_pages_open_their_days_journal_with_the_way_back(demo):
    seen = 0
    for key in ("worst-days", "run", "busiest", "not-told"):
        hrefs = [a.get("href", "") for a in anchors(demo.get(f"/mirror/fact/{key}").text)
                 if re.match(r"/journals/\d+", a.get("href", ""))]
        seen += len(hrefs)
        assert all(parse_qs(urlsplit(h).query).get("from") == [key] for h in hrefs), (key, hrefs)
    assert seen, "no report page linked a day's journal"


def test_the_busiest_day_offers_that_days_questions(demo):
    html = demo.get("/mirror/fact/busiest").text
    assert any(a["text"] == "That day's questions"
               and re.fullmatch(r"/journals/\d+\?from=busiest", a.get("href", "")) for a in anchors(html))


# ---------- Gate 6: upload, receipt, reveal, report ----------


def test_the_reveal_goes_on_to_the_report():
    """Its one way on is the report's first page, from scope_map; Limits left the walk. Read from
    the template and the route: in a test the reveal waits behind the guess."""
    template = (TEMPLATES / "reveal.html").read_text(encoding="utf-8")
    assert 'href="/budget"' not in template and "/eligibility" not in template
    assert "worst_href" in template
    route = Path("services/production/api/routes_reveal.py").read_text(encoding="utf-8")
    assert "worst_href=SM.fact_href(SM.PAGES[0].key)" in route


def test_limits_no_longer_send_on_to_the_checks_page(client):
    assert "/eligibility" not in [path(a.get("href", "")) for a in anchors(client.get("/budget").text)]


def test_the_checks_page_is_reached_from_what_we_read(client):
    assert any(path(a.get("href", "")) == "/eligibility" and a["text"] == "What we can check"
               for a in anchors(page_of(client, "unread")))


def test_limits_stay_reachable_from_account(client):
    assert "/budget" in [path(a.get("href", "")) for a in anchors(client.get("/account").text)]


def test_opening_a_report_page_counts_as_having_walked(client, engine):
    from services.production.api.routes_identity import landing_for

    def landing() -> str:
        with make_session(engine) as sess:
            trader = sess.scalars(select(m.Trader).where(m.Trader.login_id == "fx")).one()
            return landing_for(sess, trader)

    assert landing().startswith("/imports/"), "no guess, no number, nothing read: the walk"
    read(engine, "fx", ORDER[0])
    assert landing() == "/"

def test_the_rail_sits_at_the_top_where_no_header_bar_is_above_it():
    """Page read, 13 Nov 2026: /sample has no header bar, and on desktop the rail
    stuck 72px down with the page showing above it."""
    css = Path("services/production/api/static/css/app.css").read_text(encoding="utf-8")
    assert "body:not(:has(.bottom-nav)) .rail { top: 0; }" in css
