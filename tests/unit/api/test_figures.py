"""A figure is a value and its noun, on every page a trader reads.

Two checks hold it, because each misses what the other catches. Reading the templates finds a
filter written without a figure on a page no scene reaches. Rendering finds a number that went
straight onto a page with no filter at all. All of it runs on made-up files.
"""

from __future__ import annotations

import hashlib
import re
from decimal import Decimal
from pathlib import Path

import jinja2
import pytest
from jinja2 import nodes
from markupsafe import Markup

from services.production.api.app import TEMPLATES, create_app
from services.production.api.figures import Figure, NoNoun, Written
from tests.unit.api import figure_pages

TEMPLATE_ROOT = Path("services/production/api/templates")
FORMATS = {"count", "rupees", "rupees_on_a_trade", "minutes", "hold", "price", "lots", "signed_percent"}
LOOKS_LIKE_A_NUMBER = re.compile(r"[+−-]?₹?\d[\d,]*(\.\d+)?[%×]?")


def trader_facing() -> list[Path]:
    return sorted(p for p in TEMPLATE_ROOT.rglob("*.html") if not p.name.startswith("admin"))


# ---------- The type ----------


def test_a_figure_holds_its_value_its_noun_and_what_it_is_of():
    figure = Figure(8, "trades", of="your busiest day")
    assert (figure.value, figure.noun, figure.of) == (8, "trades", "your busiest day")


def test_what_it_is_of_is_optional():
    assert Figure(8, "trades").of is None


@pytest.mark.parametrize("noun", ["", "   ", "\n", None, 3])
def test_a_figure_with_no_noun_cannot_be_made(noun):
    with pytest.raises(NoNoun):
        Figure(3, noun)


def test_a_figure_with_its_noun_left_out_cannot_be_made():
    with pytest.raises(TypeError):
        Figure(3)


def test_a_page_with_a_nounless_figure_fails_rather_than_draws():
    template = TEMPLATES.env.from_string('{{ Figure(3, "")|count }}')
    with pytest.raises(NoNoun):
        template.render()


def test_a_figure_cannot_be_changed_once_made():
    with pytest.raises(AttributeError):
        Figure(3, "trades").noun = ""


@pytest.mark.parametrize(("source", "plain"), [
    ("{{ Figure(1234567, 'rows')|count }}", "{{ 1234567|count }}"),
    ("{{ Figure(-1500, 'rupees')|rupees }}", "{{ -1500|rupees }}"),
    ("{{ Figure(1500, 'rupees')|rupees(signed=false) }}", "{{ 1500|rupees(signed=false) }}"),
    ("{{ Figure(-1500, 'rupees')|rupees_on_a_trade }}", "{{ -1500|rupees_on_a_trade }}"),
    ("{{ Figure(600, 'seconds')|minutes }}", "{{ 600|minutes }}"),
    ("{{ Figure(90000, 'seconds')|hold }}", "{{ 90000|hold }}"),
    ("{{ Figure(2345.5, 'rupees')|price }}", "{{ 2345.5|price }}"),
    ("{{ Figure(1.67, 'lots')|lots }}", "{{ 1.67|lots }}"),
    ("{{ Figure(-4.5, 'percent')|signed_percent }}", "{{ -4.5|signed_percent }}"),
    ("{{ Figure(8, 'trades') }}", "{{ 8 }}"),
    ("{{ Figure(xs|length, 'trades') }}", "{{ xs|length }}"),
])
def test_a_figure_writes_exactly_what_its_plain_value_writes(source, plain):
    env = TEMPLATES.env
    assert env.from_string(source).render(xs=[1, 2]) == env.from_string(plain).render(xs=[1, 2])


# ---------- Reading the templates ----------


def _figures_in(call: nodes.Call) -> bool:
    if not (isinstance(call.node, nodes.Name) and call.node.name == "Figure"):
        return False
    if len(call.args) < 2:
        return False
    noun = call.args[1]  # a noun worked out on the page is checked by the type when it is made
    return not isinstance(noun, nodes.Const) or (isinstance(noun.value, str) and bool(noun.value.strip()))


def _unwrapped(tree) -> list[str]:
    """Every number-writing filter not given a Figure, and every bare length or literal shown."""
    found = []
    for fil in tree.find_all(nodes.Filter):
        if fil.name in FORMATS and not (isinstance(fil.node, nodes.Call) and _figures_in(fil.node)):
            found.append(f"line {fil.lineno}: |{fil.name}")
    for output in tree.find_all(nodes.Output):
        for child in output.nodes:
            if isinstance(child, nodes.Filter) and child.name == "length":
                found.append(f"line {child.lineno}: |length shown bare")
            if isinstance(child, nodes.Const) and isinstance(child.value, int | float):
                found.append(f"line {child.lineno}: literal {child.value}")
    for call in tree.find_all(nodes.Call):
        if isinstance(call.node, nodes.Name) and call.node.name == "Figure" and not _figures_in(call):
            found.append(f"line {call.lineno}: a Figure with no noun")
    return found


@pytest.mark.parametrize("path", trader_facing(), ids=lambda p: str(p.relative_to(TEMPLATE_ROOT)))
def test_no_trader_facing_template_writes_a_number_outside_a_figure(path):
    tree = TEMPLATES.env.parse(path.read_text(encoding="utf-8"))
    assert _unwrapped(tree) == []


@pytest.mark.parametrize("source", [
    "{{ n|count }}", "{{ n|rupees(signed=false) }}", "{{ xs|length }}", "{{ 3 }}",
    '{{ Figure(n)|count }}', '{{ Figure(n, "")|count }}', '{{ Figure(n, " ")|count }}',
])
def test_that_reading_catches_each_way_of_getting_it_wrong(source):
    assert _unwrapped(TEMPLATES.env.parse(source))


def test_that_reading_passes_the_right_way_and_leaves_a_condition_alone():
    source = '{% if xs|length > 1 %}{{ Figure(xs|length, "trades") }}{{ Figure(n, "rows")|count }}{% endif %}'
    assert _unwrapped(TEMPLATES.env.parse(source)) == []


def test_the_admin_page_is_no_part_of_it():
    assert not any(p.name.startswith("admin") for p in trader_facing())
    assert (TEMPLATE_ROOT / "admin.html").exists()


# ---------- Rendering ----------


def is_bare(value) -> bool:
    # A macro's Markup is its own template's output, read for bare numbers in its own right.
    if isinstance(value, Figure | Written | Markup | bool | jinja2.Undefined):
        return False
    if isinstance(value, int | float | Decimal):
        return True
    return isinstance(value, str) and LOOKS_LIKE_A_NUMBER.fullmatch(value.strip()) is not None


OPEN, CLOSE = "\ue000", "\ue001"
"""Private-use characters a bare number is wrapped in on its way to a page, so it can be found
in the HTML. Being on a page is what matters: an id in a link or a size on an SVG is in a tag,
and is no figure a trader reads."""


def marked(value):
    return f"{OPEN}{value}{CLOSE}" if is_bare(value) else value


@pytest.fixture()
def marking(monkeypatch):
    env = TEMPLATES.env
    monkeypatch.setattr(env, "finalize", marked)
    env.cache.clear()
    yield
    env.cache.clear()


def bare_in_text(html: str) -> list[str]:
    """Every marked number a trader would read, with the words around it. Tags are out of it."""
    text = re.sub(r"<(script|style)\b.*?</\1>", " ", html, flags=re.DOTALL)
    text = re.sub(r"<[^>]*>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return [text[max(0, m.start() - 40):m.end() + 30]
            for m in re.finditer(f"{OPEN}[^{CLOSE}]*{CLOSE}", text)]


def test_no_bare_number_reaches_a_page_in_any_scene(marking):
    app = create_app()
    found = {}
    for scene, pages in figure_pages.scenes(app, app.state.engine).items():
        for path, (_status, html) in pages.items():
            for words in bare_in_text(html):
                found.setdefault(words, f"{scene} {path}")
    assert found == {}


def test_that_rendering_check_catches_a_bare_number_in_text(marking):
    html = TEMPLATES.env.from_string("<p>{{ n }} trades</p>").render(n=3)
    assert bare_in_text(html)


def test_that_rendering_check_leaves_a_tag_alone(marking):
    html = TEMPLATES.env.from_string('<a href="/journals/{{ n }}">Open</a>').render(n=3)
    assert OPEN in html
    assert bare_in_text(html) == []


def test_that_rendering_check_passes_a_figure(marking):
    source = "<p>{{ Figure(n, 'trades') }} {{ Figure(n, 'trades')|count }}</p>"
    assert OPEN not in TEMPLATES.env.from_string(source).render(n=3)


# ---------- The kit ----------


def test_the_kit_stylesheet_is_untouched():
    """Its digest on main before this work: a figure changes nothing about how a page is drawn."""
    css = Path("services/production/api/static/css/components.css").read_bytes()
    assert hashlib.sha256(css).hexdigest() == KIT_SHA


KIT_SHA = "01e8fe7836a1d3a9364111f14807399e041d0c3cd6fa3f4d164e4f857aa0d04d"
