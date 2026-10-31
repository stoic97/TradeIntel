"""The Scope dial on a page: scope_geometry's SVG, made safe to put in a template.

scope_geometry is the kit's JavaScript ported line for line, and like the JavaScript
it writes an href as given and escapes text for an element, not for an attribute. This
is the one door a page goes through to draw a dial, and it closes both gaps: every href
is escaped here, and a name or figure that would break out of the aria-label it is
written into is refused rather than drawn. The result is marked safe, so Jinja does
not escape the SVG a second time.

A chapter's slices carry their mini charts: an item names its chart kind in "chart"
and gives the chart itself, from scope_geometry.CHARTS at MINI_W x MINI_H, in "mini".

The dial in miniature is here too: the lens and the path on a fact page, and the trade
strip under each trade, each a pure drawing a template asks for by name.
"""

from __future__ import annotations

from markupsafe import Markup, escape

from services.production.api import scope_geometry as G

MINI_W, MINI_H = 36, 14
OPTS = {"threeLineNames": G.THREE_LINE_NAMES}
CRUMB_LIMIT = 44  # characters in "Scope › chapter › fact" on the phone (the kit's path note)
STRIP_W = 350  # a trade strip's drawing width; the SVG stretches it to the column


def _text(value: str, what: str) -> str:
    if '"' in value:
        raise ValueError(f"a dial {what} cannot contain a double quote: {value!r}")
    return value


def scope_dial(view: dict, size: str = "phone") -> Markup:
    """The dial for a view (scope_geometry.build_dial's shape, hrefs unescaped)."""
    centre = dict(view.get("centre") or {})
    if view["kind"] == "home" and not centre.get("figure"):
        raise ValueError("a home dial needs its centre figure")
    for key in ("figure", "name"):
        if centre.get(key):
            _text(centre[key], f"centre {key}")
    for line in centre.get("captionLines") or ():
        _text(line, "centre caption")
    if centre.get("scopeHref"):
        centre["scopeHref"] = str(escape(centre["scopeHref"]))

    items, minis = [], {}
    for item in view["items"]:
        _text(item["name"], "name")
        _text(item["figure"], "figure")
        kind = item.get("chart") or ""
        if kind and not item.get("state"):
            if "mini" not in item:
                raise ValueError(f"slice {item['name']!r} names a {kind} chart but gives none")
            minis[kind] = G.render_chart(item["mini"])
        items.append({**item, "href": str(escape(item["href"]))})

    built = G.build_dial({**view, "items": items, "centre": centre}, size, OPTS)
    return Markup(G.render_dial_svg(built, minis))


def crumb(chapter: str, fact: str) -> tuple[str, bool]:
    """The chapter's name in the phone path bar, and whether it was shortened.

    The whole path fits in CRUMB_LIMIT characters or the chapter's name is cut to as
    many whole words as fit, then an ellipsis - always at least its first word. Read
    off the kit's twelve fact screens, which this reproduces exactly.
    """

    def fits(name: str) -> bool:
        return len(f"Scope › {name} › {fact}") <= CRUMB_LIMIT

    if fits(chapter):
        return chapter, False
    words = chapter.split(" ")
    short = words[0] + "…"
    for j in range(2, len(words)):
        if not fits(" ".join(words[:j]) + "…"):
            break
        short = " ".join(words[:j]) + "…"
    return short, True


def strip(fill_minutes: list) -> dict:
    """A trade drawn to time; fill_minutes count from the trade's first fill."""
    return G.trade_strip(fill_minutes, STRIP_W)


def register(env) -> None:
    """Make the drawings callable from every template, as the app's environment does."""
    env.globals.update(
        scope_dial=scope_dial, scope_lens=G.build_lens, scope_crumb=crumb, scope_strip=strip
    )
