"""Every figure opens its trades and every date opens its day (TICKET-905)."""

from __future__ import annotations

import re

from markupsafe import Markup

from services.production.api import dial, formatting
from services.production.api import scope_facts as SF
from services.production.api import scope_map as S
from services.production.api.figures import Figure, through_figure
from tests.unit.api.test_read_again import send, words
from tests.unit.api.test_scope_chapters import FIGS, IMP, TRIPS
from tests.unit.api.test_upload import client, engine  # noqa: F401

CTX = SF.record_context(TRIPS)


# ---- the mechanism is the figure's own

def test_a_figure_that_opens_is_a_link_and_one_that_doesnt_is_plain():
    count = through_figure(formatting.count)
    opened = count(Figure(5, "days", opens="/mirror/fact/worst-days/trades"))
    assert isinstance(opened, Markup)
    assert '<a class="figure-link" href="/mirror/fact/worst-days/trades"' in opened
    assert 'aria-label="5 days: open the trades behind it"' in opened and ">5</a>" in opened
    plain = count(Figure(5, "days"))
    assert "<a" not in plain and plain == "5"


def test_a_figure_link_escapes_what_it_writes():
    link = formatting.opens(Figure('<b>"x"</b>', "things", opens='/a?b="c"'))
    assert "<b>" not in link and "&#34;" in link


# ---- each fact's figure opens the trades from the same object

def test_every_fact_with_trades_opens_them_and_the_rest_do_not():
    for key, fig in FIGS.items():
        if key not in SF.TRADES_BEHIND or fig["state"]:  # share has no page of its own
            assert fig["opens"] is None, key
        else:
            assert fig["opens"] and fig["opens"].startswith(f"/mirror/fact/{key}/trades"), key
            assert fig["lead_figure"].opens == fig["opens"]


def test_the_clocks_figure_opens_its_own_hour():
    href = FIGS["clock"]["opens"]
    assert "hour=" in href and "book=" in href


# ---- the dials: each wedge opens its trades, or is plain

def test_each_chapter_wedge_opens_its_trades_or_is_visibly_not_a_link():
    for n in (1, 2, 3, 4):
        svg = str(dial.scope_dial(SF.chapter_view(n, FIGS)))
        for f in S.chapter(n).facts:
            opens = FIGS[f.key]["opens"]
            if opens:
                assert f'href="{opens.replace("&", "&amp;")}"' in svg, f.key
        plain = re.findall(r'<a class="scope__slice scope__slice--plain[^"]*" aria-label="([^"]+)"', svg)
        assert all("href" not in p for p in plain)
    svg4 = str(dial.scope_dial(SF.chapter_view(4, FIGS)))
    assert svg4.count("scope__slice--plain") == 2  # what we read, what we have not told you


def test_the_hub_wedges_open_the_trades_behind_their_figures():
    view = SF.home_view(CTX, IMP)
    assert view["items"][0]["href"] == FIGS["worst-days"]["opens"]
    assert view["items"][1]["href"] == FIGS["math"]["opens"]
    assert view["items"][2]["href"] in (FIGS["busiest"]["opens"], None)
    assert view["items"][3]["href"] is None  # no number is set: nothing behind "no number"


# ---- the pages

def test_a_facts_large_figure_opens_its_trades(client):  # noqa: F811
    send(client)
    for key in ("math", "risk", "clock"):
        page = client.get(f"/mirror/fact/{key}").text
        if key == "risk" and "num--hero" not in page:
            continue  # this record's risk page is the trades-with-a-figure state
        assert "trades trades" not in page and "hour hour" not in page
        hero = re.search(r'num--hero">(.*?)</span>', page, re.DOTALL).group(1)
        assert '<a class="figure-link" href="/mirror/fact/' in hero, key
    unread = client.get("/mirror/fact/unread").text
    assert '<a class="figure-link"' not in re.search(r'num--hero">(.*?)</span>', unread, re.DOTALL).group(1)


def test_what_a_figure_opens_lists_every_trade_it_counted(client):  # noqa: F811
    """The math figure counts same-day trades; its link lists all of them, none missing."""
    from services.production.mirror import metrics as mx
    send(client)
    page = client.get("/mirror/fact/math").text
    href = re.search(r'num--hero"><a class="figure-link" href="([^"]+)"', page).group(1)
    listed = client.get(href.replace("&amp;", "&")).text
    assert listed.count('<article class="trade">') == len(mx.same_day_trips(_trips(client)))


def _trips(client):  # noqa: F811
    from sqlalchemy import select

    from services.production.db import models as m
    from services.production.db.session import make_session
    from services.production.mirror import loader
    with make_session(client.app.state.engine) as sess:
        trips, _ = loader.load_for(sess, sess.scalars(select(m.Trader)).one())
    return trips


def test_a_date_opens_its_day_with_every_trade_on_it(client):  # noqa: F811
    send(client)
    trips = _trips(client)
    day = trips[0].trading_day
    page = client.get(f"/mirror/day/{day}")
    assert page.status_code == 200
    said = words(page.text)
    count = sum(1 for t in trips if t.trading_day == day)
    assert f"{count} trade" in said and "opened this day, every one of them." in said
    assert page.text.count('<article class="trade">') == count


def test_a_day_the_record_does_not_hold_is_not_found(client):  # noqa: F811
    send(client)
    assert client.get("/mirror/day/1999-01-01").status_code == 404
    assert client.get("/mirror/day/not-a-day").status_code == 404


def test_home_writes_a_books_worst_day_as_a_link_to_that_day(client):  # noqa: F811
    send(client)
    page = client.get("/mirror").text
    if "Worst day:" in page:
        assert re.search(r'Worst day: <a class="figure-link" href="/mirror/day/\d{4}-\d{2}-\d{2}">', page)


def test_the_link_filters_are_registered_where_templates_are_tested():
    from tests.unit.api.templating import template_env
    env = template_env()
    assert "opens" in env.filters and "day_link" in env.filters
