"""The design kit's components as Jinja macros (templates/_components.html).

Each macro writes the kit's markup (docs/design/scope-kit/components.html) with the
handoff's wording, so a page uses a component by name and cannot drift from the kit
one class at a time. Rendered here through Jinja with the app's filters, without the
app, so each component is tested as itself.

The components that draw from the dial's geometry - the dial, the charts, the lens and
path, the trade record, the story card - are held to the kit's own screens in
test_dial.py and test_scope_components.py.
"""

from __future__ import annotations

import json
import re
from decimal import Decimal
from pathlib import Path

from tests.unit.api.templating import template_env

MINUS = "\u2212"


def call(macro: str, *args, **kwargs) -> str:
    module = template_env().get_template("_components.html").module
    return getattr(module, macro)(*args, **kwargs)


def test_the_lockup_draws_the_mark_exactly_as_the_kit_ships_it():
    """Never redrawn, respaced or recoloured: the same shapes as icons/mark.svg."""
    shapes = re.compile(r'<(?:path d="[^"]+"|circle cx="[^"]+" cy="[^"]+" r="[^"]+")')
    mark = Path("services/production/api/static/icons/mark.svg").read_text()
    html = str(call("lockup"))
    assert shapes.findall(html) == shapes.findall(mark)
    assert '<span class="lockup__name">PlusEV</span><span class="lockup__sub">Scope</span>' in html


def test_a_chip_on_navy_says_so():
    assert str(call("chip", "In development.")) == '<span class="chip">In development.</span>'
    assert 'class="chip chip--on-navy"' in str(call("chip", "In development.", on_navy=True))


def test_a_button_is_a_link_when_it_goes_somewhere_and_a_button_when_it_submits():
    assert str(call("button", "Continue", href="/budget")) == (
        '<a class="btn btn--primary" href="/budget">Continue</a>')
    assert str(call("button", "Sign in", block=True)) == (
        '<button class="btn btn--primary btn--block" type="submit">Sign in</button>')


def test_a_button_takes_the_kits_kinds_and_can_be_disabled():
    html = str(call("button", "Delete everything", disabled=True))
    assert html.endswith(" disabled>Delete everything</button>")
    assert 'class="btn btn--on-navy"' in str(call("button", "Show me those days",
                                                   href="/x", kind="on-navy"))


def test_money_is_written_by_the_filters_and_coloured_by_its_sign():
    assert str(call("money", Decimal("-12345.6"))) == (
        f'<span class="num num--loss">{MINUS}₹12,345</span>')
    assert str(call("money", Decimal(4500), size="medium")) == (
        '<span class="num num--medium num--gain">+₹4,500</span>')
    assert 'num--plain">₹0<' in str(call("money", 0))


def test_an_amount_is_never_red_or_green():
    """Red and green belong to signed results only (handoff section 7)."""
    assert str(call("money", 1500000, signed=False)) == (
        '<span class="num num--plain">₹15,00,000</span>')


def test_the_gross_line_is_the_mirrors_own_sentence():
    """Handoff section 7 fixes it; the frozen Mirror wording holds it word for word."""
    reference = json.loads(Path("tests/fixtures/mirror_wording/mirror_v1.json").read_text())
    blocks = [b for section in reference["sections"] for b in section["blocks"]]
    html = str(call("gross_line"))
    sentence = re.sub(r"<[^>]+>", "", html)
    assert html.startswith('<p class="gross-line">')
    assert sentence in blocks


def test_not_enough_trades_shows_both_counts_and_says_so_in_words():
    html = str(call("not_enough", 12, 30))
    assert 'class="result-state result-state--not-enough"' in html
    assert "Not enough trades yet" in html
    assert '<span class="num">12</span> trades, and it needs <span class="num">30</span>.' in html
    assert "We tell you what your history can't yet show, instead of guessing." in html


def test_not_in_your_file_carries_the_facts_own_sentence():
    sentence = "Your export has no stop column, and no budget is set."
    html = str(call("not_in_file", sentence))
    assert 'class="result-state result-state--not-in-file"' in html
    assert "Not in your file" in html and sentence in html


def test_the_two_states_differ_by_shape_not_colour_alone():
    """Handoff section 4: border, fill and marker, so a reader who cannot tell
    colours apart still tells the states apart."""
    assert "result-state__swatch-hatch" in str(call("not_enough", 1, 2))
    assert "result-state__swatch-dashed" in str(call("not_in_file", "x"))
    assert "result-state__swatch-hatch" not in str(call("not_in_file", "x"))


def test_a_field_has_its_label_and_its_error_is_announced():
    html = str(call("field", "Login id", "login_id", value="fx", autocomplete="username",
                    error=True))
    assert '<span class="field__label">Login id</span>' in html
    assert 'class="field field--error"' in html and 'aria-invalid="true"' in html
    assert 'name="login_id"' in html and 'value="fx"' in html
    assert 'autocomplete="username"' in html


def test_a_password_is_never_written_back_into_the_page():
    html = str(call("field", "Password", "password", type="password", value="hunter2-hunter2"))
    assert "hunter2" not in html and 'type="password"' in html


def test_a_field_shows_its_hint_and_its_own_error_sentence():
    html = str(call("field", "Password", "password", type="password",
                    error="A password needs at least 12 characters.",
                    hint="At least 12 characters."))
    assert '<span class="field__error">A password needs at least 12 characters.</span>' in html
    assert '<span class="field__hint">At least 12 characters.</span>' in html


def test_what_a_trader_types_is_escaped():
    assert "<script>" not in str(call("field", "Login id", "login_id", value="<script>"))


def test_a_field_can_be_required():
    assert 'autocomplete="username" required>' in str(
        call("field", "Login id", "login_id", autocomplete="username", required=True))
    assert " required" not in str(call("field", "Login id", "login_id"))
