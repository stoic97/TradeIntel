"""Templates are tested through tests/unit/api/templating.py, not through the app.

That lets a layout or a component be rendered without a database, a session or a
route. It is only honest if the test environment renders as the app's does: HTML
escaped, the same formatting filters, and the same dial.
"""

from __future__ import annotations

from tests.unit.api.templating import template_env


def escapes(env, name) -> bool:
    """Whether env escapes a template of this name (None: a template from a string)."""
    return env.autoescape(name) if callable(env.autoescape) else env.autoescape


def test_the_test_environment_matches_the_apps():
    from services.production.api.app import TEMPLATES as APP

    ours = template_env()
    for name in ("page.html", "_components.html", "notes.txt", None):
        assert escapes(ours, name) == escapes(APP.env, name), name
    for env in (ours, APP.env):
        assert env.from_string("{{ x }}").render(x="<b>") == "&lt;b&gt;"
    for name in ("rupees", "tone", "count", "minutes"):
        assert ours.filters[name] is APP.env.filters[name], name
    assert ours.globals["scope_dial"] is APP.env.globals["scope_dial"]


def test_a_probe_template_is_rendered_alongside_the_apps():
    env = template_env({"probe.html": '{% extends "layout.html" %}'})
    assert "<!doctype html>" in env.get_template("probe.html").render(title="x")
