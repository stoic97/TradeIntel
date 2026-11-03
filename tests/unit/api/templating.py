"""A Jinja environment set up as the app sets up its own, for rendering templates in tests.

Starlette's Jinja2Templates escapes with Jinja's select_autoescape() (on for .html and
for string templates), and app.py registers the formatting filters and the dial on it.
Templates are tested through this environment rather than through the app, so a layout
or a component can be rendered without a database, a session or a route;
test_templating.py keeps the two alike.
"""

from __future__ import annotations

from pathlib import Path

from jinja2 import ChoiceLoader, DictLoader, Environment, FileSystemLoader, select_autoescape

from services.production.api import dial, formatting

TEMPLATES = Path("services/production/api/templates")


def template_env(extra: dict[str, str] | None = None) -> Environment:
    """The app's templates, plus any probe templates given by name."""
    loaders = [FileSystemLoader(str(TEMPLATES))]
    if extra:
        loaders.insert(0, DictLoader(extra))
    env = Environment(loader=ChoiceLoader(loaders), autoescape=select_autoescape())
    formatting.register(env)
    dial.register(env)
    return env
