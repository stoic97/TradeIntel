"""layout.html: the base every rebuilt page extends (handoff section 8, T8).

It carries the design kit's head, a navy stage block, a white content block and the
bottom nav. Rendered here through Jinja alone, with a one-line probe page per case, so
the layout is tested as a layout and not through any one screen that happens to use it.

Pages move onto it one at a time; base.html and scope.css serve the rest until the
last page has moved (Phase 4), so no page is ever left half-styled.
"""

from __future__ import annotations

import re
from pathlib import Path

from jinja2 import ChoiceLoader, DictLoader, Environment, FileSystemLoader

TEMPLATES = Path("services/production/api/templates")
STATIC = Path("services/production/api/static")

STYLESHEETS = ["/static/css/fonts.css", "/static/css/tokens.css",
               "/static/css/components.css", "/static/css/motion.css"]


def render(child: str, **context) -> str:
    env = Environment(loader=ChoiceLoader([DictLoader({"probe.html": child}),
                                           FileSystemLoader(str(TEMPLATES))]))
    context.setdefault("title", "Sign in")
    return env.get_template("probe.html").render(**context)


PLAIN = '{% extends "layout.html" %}{% block content %}<p>Body</p>{% endblock %}'


def test_the_stylesheets_are_the_kits_with_fonts_first_and_nothing_else():
    html = render(PLAIN)
    linked = re.findall(r'<link rel="stylesheet" href="([^"]+)">', html)
    assert linked == STYLESHEETS
    assert "scope.css" not in html


def test_htmx_and_the_icons_come_from_this_app():
    html = render(PLAIN)
    assert '<script src="/static/js/htmx.min.js" defer></script>' in html
    for icon in ("favicon.svg", "favicon-32.png", "favicon-16.png", "app-icon-180.png"):
        assert f'href="/static/icons/{icon}"' in html, icon


def test_every_file_the_layout_links_exists():
    for path in re.findall(r'(?:href|src)="/static/([^"]+)"', render(PLAIN)):
        assert (STATIC / path).is_file(), path


def test_nothing_reaches_outside_the_app():
    """The layout links no host at all, not even plusev.in (test_app_skeleton's rule)."""
    assert not re.search(r"""(?:src|href|action)\s*=\s*["'](https?:)?//""", render(PLAIN))


def test_the_title_names_the_page_then_the_product():
    assert "<title>Sign in · PlusEV Scope</title>" in render(PLAIN)


def test_the_chart_hatch_pattern_is_on_every_page():
    """components.css fills not-enough-trades marks with url(#hatch-light)."""
    assert 'id="hatch-light"' in render(PLAIN)


def test_the_stage_comes_before_the_record():
    html = render('{% extends "layout.html" %}'
                  '{% block stage %}<header class="stage on-navy">S</header>{% endblock %}'
                  '{% block content %}<p>Body</p>{% endblock %}')
    stage, body = html.index('<header class="stage on-navy">'), html.index("<p>Body</p>")
    main = html.index('<main class="screen__body')
    assert stage < main < body
    assert html.index('<div class="screen">') < stage


def test_a_page_without_a_stage_has_none():
    assert "stage" not in render(PLAIN).split("<body>")[1]


def test_an_in_app_page_names_its_tab_and_gets_the_bottom_nav():
    html = render('{% extends "layout.html" %}{% set nav = "journal" %}'
                  '{% block content %}<p>Body</p>{% endblock %}')
    items = re.findall(r'<a class="bottom-nav__item" href="([^"]+)"( aria-current="page")?>([^<]+)</a>',
                       html)
    assert items == [("/mirror", "", "Scope"),
                     ("/journals", ' aria-current="page"', "Journal"),
                     ("/account", "", "Account")]
    assert 'class="screen__body screen__body--with-nav"' in html


def test_the_bottom_nav_has_no_sign_out():
    """D6: sign out moves to the Account page."""
    html = render('{% extends "layout.html" %}{% set nav = "scope" %}'
                  '{% block content %}{% endblock %}')
    assert "/logout" not in html and "Sign out" not in html


def test_a_page_that_names_no_tab_has_no_bottom_nav():
    """Fact pages and the pages before sign-in."""
    html = render(PLAIN)
    assert "bottom-nav" not in html
    assert 'class="screen__body"' in html


def test_the_motion_class_is_set_only_when_the_server_gives_one():
    assert '<html lang="en" class="vt-in vt-tap-2">' in render(PLAIN, enter_class="vt-in vt-tap-2")
    assert '<html lang="en">' in render(PLAIN)
