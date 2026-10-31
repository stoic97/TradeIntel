"""The Scope's drawn components match the design kit's own screens.

The kit's screens (docs/design/scope-kit/screens) are Jinja templates, so the honest
test of a macro is to render the kit's fragment and the macro with the same data and
ask for the same page. Whitespace between tags, the kit's stray spaces inside class
lists, and the choice of entity for an apostrophe are not differences anyone sees, so
both sides are normalised for those and nothing else.
"""

from __future__ import annotations

import html
import json
import re
from pathlib import Path

import pytest
from jinja2 import Environment
from markupsafe import Markup

from services.production.api import dial
from services.production.api import formatting as F
from services.production.api import scope_geometry as G
from tests.unit.api.templating import template_env

SCREENS = Path("docs/design/scope-kit/screens")
CHARTS = json.loads(Path("tests/fixtures/scope_geometry/cases.json").read_text())["charts"]


def same(markup: str) -> str:
    """Markup as a reader meets it: no whitespace between tags, none padding a class."""
    out = re.sub(r">\s+<", "><", str(markup).strip())
    out = re.sub(r'class="([^"]*)"', lambda m: f'class="{" ".join(m[1].split())}"', out)
    return html.unescape(out)


def kit(fragment: str, **data) -> str:
    """A fragment of a kit screen, rendered as the kit means it to be."""
    return Environment(autoescape=True).from_string(fragment).render(**data)


def ours(source: str, **data) -> str:
    return template_env({"probe.html": source}).get_template("probe.html").render(**data)


# ---------- Charts ----------


@pytest.mark.parametrize("case", CHARTS, ids=[f"{c['kind']}-{c['w']}" for c in CHARTS])
def test_a_chart_is_drawn_as_the_kit_records_it(case):
    got = ours(
        '{% from "_components.html" import chart %}{{ chart(c, "chart--page") }}', c=case["out"]
    )
    assert got == case["svg"]


def test_a_chart_without_a_class_has_no_stray_space():
    c = G.chart_share(0.5, 350, 96)
    got = ours('{% from "_components.html" import chart %}{{ chart(c) }}', c=c)
    assert got.startswith('<svg class="chart" viewBox="0 0 350 96"')


# ---------- The path bar on a fact page ----------

FACTS = [  # screen, facts in the chapter, which fact, chapter, fact
    ("16-f01-worst-days", 3, 0, "Where your results came from", "Your worst trading days"),
    ("16-f02-share", 3, 1, "Where your results came from", "Share of your result"),
    ("16-f03-money", 3, 2, "Where your results came from", "Where the money came from"),
    ("16-f04-hold", 4, 0, "Your patterns", "How long you hold"),
    ("16-f05-strike", 4, 1, "Your patterns", "Strike rate"),
    ("16-f06-run", 4, 2, "Your patterns", "Longest losing run"),
    ("16-f07-clock", 4, 3, "Your patterns", "The clock"),
    ("16-f08-down", 2, 0, "Your behaviour", "Trading on while already down"),
    ("16-f09-busy", 2, 1, "Your behaviour", "Your busiest day"),
    ("16-f10-read", 3, 0, "What we couldn't read", "What we could not read"),
    ("16-f11-risk", 3, 1, "What we couldn't read", "Trades with a risk figure"),
    ("16-f12-not-told", 3, 2, "What we couldn't read", "What we have not told you"),
]
PATH = re.compile(r'<nav class="path" aria-label="Scope path">.*?</nav>', re.DOTALL)
LENS_HREF = re.compile(r'class="path__lens" href="([^"]+)"')


def path_of(screen: str) -> tuple[str, str]:
    """The kit's path bar on a screen, and the chapter link it uses (unescaped)."""
    nav = PATH.search((SCREENS / f"{screen}.html").read_text())[0]
    return nav, html.unescape(LENS_HREF.search(nav)[1])


@pytest.mark.parametrize(("screen", "n", "i", "chapter", "fact"), FACTS, ids=[f[0] for f in FACTS])
def test_the_path_bar_is_the_kits_on_every_fact_page(screen, n, i, chapter, fact):
    nav, href = path_of(screen)
    got = ours(
        '{% from "_components.html" import path %}{{ path(n, i, chapter, href, fact, "/scope") }}',
        n=n,
        i=i,
        chapter=chapter,
        href=href,
        fact=fact,
    )
    assert same(got) == same(nav)


def test_on_the_desktop_the_chapter_is_never_cut():
    _, href = path_of("16-f01-worst-days")
    desk = PATH.search((SCREENS / "desktop-fact-worst-days.html").read_text())[0]
    got = ours(
        '{% from "_components.html" import path %}'
        '{{ path(3, 0, "Where your results came from", href, "Your worst trading days",'
        ' "/scope", "desktop") }}',
        href=href,
    )
    assert same(got) == same(desk)


@pytest.mark.parametrize(
    ("chapter", "fact", "want"),
    [
        ("Your patterns", "Longest losing run", ("Your patterns", False)),
        ("Where your results came from", "Share of your result", ("Where your…", True)),
        ("Your behaviour", "Trading on while already down", ("Your…", True)),  # first word, always
    ],
)
def test_the_chapter_name_is_cut_to_whole_words(chapter, fact, want):
    assert dial.crumb(chapter, fact) == want


# ---------- The trades behind a fact ----------

TRADES = re.compile(r'<div class="trades">.*?\n  \{% endfor %\}\n</div>', re.DOTALL)

GROUP = {
    "title": "Day 1 · 07 Sep",
    "trade_count": 2,
    "net": -1500,
    "trades": [
        {
            "number": 3,
            "instrument": "NIFTY 5000 CE",
            "day": "07 Sep",
            "time_in": "09:20",
            "time_out": "09:50",
            "held_minutes": 30,
            "net": -2000,
            "fill_minutes": [0, 5, 30],
            "fills": [
                {"time": "09:20", "side": "Buy", "qty": 75, "price": "₹120.50", "row": 12},
                {"time": "09:25", "side": "Buy", "qty": 75, "price": "₹118.00", "row": 13},
                {"time": "09:50", "side": "Sell", "qty": 150, "price": "₹106.25", "row": 14},
            ],
        },
        {
            "number": 4,
            "instrument": "NIFTY 5000 PE",
            "day": "07 Sep",
            "time_in": "10:00",
            "time_out": "10:10",
            "held_minutes": 10,
            "net": 500,
            "fill_minutes": [0, 10],
            "fills": [
                {"time": "10:00", "side": "Sell", "qty": 75, "price": "₹90.00", "row": 20},
                {"time": "10:10", "side": "Buy", "qty": 75, "price": "₹83.25", "row": 21},
            ],
        },
    ],
}


def as_the_kit_gives_it(group: dict) -> dict:
    """The same day as the kit's screens take it: every figure already written."""
    return {
        "title": group["title"],
        "summary": f"{group['trade_count']} trades · {F.rupees(group['net'])}",
        "trades": [
            {
                **t,
                "held_minutes": F.count(t["held_minutes"]),
                "net": F.rupees(t["net"]),
                "net_tone": F.tone(t["net"]),
                "strip": dial.strip(t["fill_minutes"]),
                "fills": [
                    {**f, "qty": F.count(f["qty"]), "row": F.count(f["row"])} for f in t["fills"]
                ],
            }
            for t in group["trades"]
        ],
    }


@pytest.mark.parametrize(
    "screen", ["16-f01-worst-days", "16-f05-strike", "desktop-fact-worst-days"]
)
def test_every_trade_is_listed_as_the_kit_lists_it(screen):
    fragment = TRADES.search((SCREENS / f"{screen}.html").read_text())[0]
    want = kit(fragment, trade_groups=[as_the_kit_gives_it(GROUP)])
    got = ours('{% from "_components.html" import trades %}{{ trades(groups) }}', groups=[GROUP])
    assert same(got) == same(want)


def test_a_trade_strip_is_drawn_to_time():
    s = dial.strip([0, 5, 30])
    assert s["ticks"] == "M4 5V12M61 5V12M346 5V12"  # 5 of 30 minutes: a sixth of 342 px, from 4


def test_a_day_of_one_trade_says_trade():
    group = {**GROUP, "trade_count": 1, "trades": GROUP["trades"][:1]}
    got = ours('{% from "_components.html" import trades %}{{ trades(groups) }}', groups=[group])
    assert "<span>1 trade · " in got


# ---------- The figure on a fact page, and the story card ----------

FIGURE = re.compile(r'<figure class="figure">.*?</figure>', re.DOTALL)


def test_a_figure_is_the_kits():
    fragment = FIGURE.search((SCREENS / "16-f01-worst-days.html").read_text())[0]
    c = G.chart_worst([-300, -8000, -200, -2000], 350, 96)
    want = kit(fragment, worst_days_chart=c, first_day="01 Sep", last_day="04 Sep")
    axis_and_legend = fragment.split("</svg>", 1)[1].rsplit("</figure>", 1)[0]
    got = ours(
        '{% from "_components.html" import figure %}'
        '{% call figure(1, "Net (gross) for each trading day", c) %}'
        + axis_and_legend
        + "{% endcall %}",
        c=c,
        first_day="01 Sep",
        last_day="04 Sep",
    )
    assert same(got) == same(want)


CARD = re.compile(
    r'<a class="story-card" href="(/scope/results/worst-days[^"]*)">(.*?)</a>', re.DOTALL
)


def test_a_story_card_is_the_kits():
    href, inside = CARD.search((SCREENS / "15-chapter-1-results.html").read_text()).groups()
    body = inside.split("\n", 2)[2].rsplit('<span class="story-card__foot">', 1)[0]
    facts = {
        "worst_days": {
            "five_day_sum": F.rupees(-24000),
            "five_day_sum_tone": "loss",
            "trade_count": "12",
            "chart": G.chart_worst([-300, -8000], 302, 84),
        }
    }
    want = kit(f'<a class="story-card" href="{href}">{inside}</a>', facts=facts)
    got = ours(
        '{% from "_components.html" import story_card, money, trades_behind %}'
        '{% call story_card(1, "Your worst trading days", href, money(-24000), trades_behind(12)) %}'
        + body
        + "{% endcall %}",
        href=html.unescape(href),
        facts=facts,
    )
    assert same(got) == same(want)


def test_a_stacked_story_card_says_so():
    got = ours(
        '{% from "_components.html" import story_card %}'
        '{{ story_card(1, "How long you hold", "/x", "30 min", "6 trades", stacked=true) }}'
    )
    assert got.startswith('<a class="story-card story-card--stacked" href="/x">')


def test_one_trade_behind_a_fact_is_one_trade():
    got = ours('{% from "_components.html" import trades_behind %}{{ trades_behind(1) }}')
    assert got == '<span class="num">1</span> trade behind this'


def test_text_given_to_a_card_is_escaped_and_a_component_is_not():
    got = ours(
        '{% from "_components.html" import story_card %}{{ story_card(1, t, "/x", f, foot) }}',
        t="<b>",
        f=Markup('<span class="num">3</span>'),
        foot="a & b",
    )
    assert "&lt;b&gt;" in got and '<span class="num">3</span>' in got and "a &amp; b" in got
