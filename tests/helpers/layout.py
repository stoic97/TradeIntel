"""Moved out of tests/unit/api/test_layout.py by TICKET-945, so that no test file imports another."""

from __future__ import annotations

from tests.unit.api.templating import template_env


def render(child: str, **context) -> str:
    context.setdefault("title", "Sign in")
    return template_env({"probe.html": child}).get_template("probe.html").render(**context)


PLAIN = '{% extends "layout.html" %}{% block content %}<p>Body</p>{% endblock %}'
