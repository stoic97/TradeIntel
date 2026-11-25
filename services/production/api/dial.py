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

import re
from decimal import Decimal

from markupsafe import Markup, escape

from services.production.api import charts
from services.production.api import scope_geometry as G

MINI_W, MINI_H = G.MINI["w"], G.MINI["h"]  # the kit's: 72 x 20
FIT_ON_A_PHONE = 0  # the phone dial keeps its spacing whole, nothing touching the ring or a divider
FIT_ON_A_DESKTOP = -13  # the desktop dial as it was
SMALLER = ((64, 20), (56, 20), (48, 20), (48, 16))
"""Mini sizes a phone wedge steps down through when MINI_W x MINI_H will not clear it. A side wedge
of a three-wedge phone dial cannot hold 72 px at any figure size the kit has."""


def fitted(items: list, fig_sizes: list, size: str = "phone") -> list:
    """A chapter's wedges with each mini as wide as its wedge clears, MINI_W where it can.

    The most crowded wedge steps down first, one width at a time, and the dial is laid out again
    after each step, since one wedge's block moves the shared radius for all of them. A wedge
    that clears only without its mini draws none: its figure and reference line say the fact,
    and the fact page carries the chart. One that overflows for other reasons keeps the smallest."""
    rr, sec = G.dial_radii(size, False), G.sectors(len(items), False)
    limit = FIT_ON_A_PHONE if size == "phone" else FIT_ON_A_DESKTOP
    items = list(items)
    settled: set[int] = set()  # wedges whose overflow is not the mini's: they keep the smallest
    for _ in range(len(items) * (len(SMALLER) + 1)):
        lay = G.layout_contents(items, sec, rr, fig_sizes)
        worst = None
        for i, block in enumerate(lay["blocks"]):
            it = items[i]
            if it.get("state") or not it.get("chart") or i in settled:
                continue
            clear = G.block_clearance(sec["slices"][i], sec["span"], lay["radius"][i], block, rr)
            if clear < limit and (worst is None or clear < worst[1]):
                worst = (i, clear)
        if worst is None:
            break
        i = worst[0]
        if _step(items[i]) == len(SMALLER):
            bare = items[:i] + [{**items[i], "chart": ""}] + items[i + 1:]
            lay = G.layout_contents(bare, sec, rr, fig_sizes)
            if G.block_clearance(sec["slices"][i], sec["span"], lay["radius"][i], lay["blocks"][i], rr) >= limit:
                items = bare  # only dropping the mini clears this wedge
            else:
                settled.add(i)
        else:
            w, h = SMALLER[_step(items[i])]
            items[i] = {**items[i], "miniW": w, "miniH": h}
    return items


def _step(item: dict) -> int:
    """How many sizes down from MINI a wedge's mini already is."""
    now = (item.get("miniW") or MINI_W, item.get("miniH") or MINI_H)
    return SMALLER.index(now) + 1 if now in SMALLER else 0
OPTS = {"threeLineNames": G.THREE_LINE_NAMES}
CRUMB_LIMIT = 44  # characters in "Scope › chapter › fact" on the phone (the kit's path note)
STRIP_W = 350  # a trade strip's drawing width; the SVG stretches it to the column
HUB_FIG_SIZES_PHONE = [22, 18, 15, 13, 12]  # a hub wedge's figure has a noun now; "100 of 100" needs 12
RUPEES = re.compile(r"([−-]?)₹(\d[\d,]*)(?![\d.])")
"""A whole-rupee amount as formatting.rupees writes it."""


def phone_rupees(text: str) -> str:
    """A phone dial's rupees in the toolkit's short form (₹50.6k, −₹1.2L); under a thousand
    they stay whole. The desktop dial and every page keep the whole figure."""

    def short(m: re.Match) -> str:
        value = Decimal(m.group(2).replace(",", ""))
        if value < charts.THOUSAND:
            return m.group(0)
        return charts.short(-value if m.group(1) else value)

    return RUPEES.sub(short, text or "")



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
    if centre.get("readLine"):
        _text(centre["readLine"], "centre reading")
    if view.get("progressLabel"):
        _text(view["progressLabel"], "reading")
    if centre.get("scopeHref"):
        centre["scopeHref"] = str(escape(centre["scopeHref"]))

    if size == "phone" and view["kind"] == "home" and centre.get("figure"):
        full = centre["figure"]
        centre["figure"] = phone_rupees(full)
        if centre["figure"] != full:  # read out whole: the figure and what it is
            centre["spoken"] = " ".join([full, *(centre.get("captionLines") or ())])

    if size == "desktop" and view.get("desktop_items"):  # every fact keeps its wedge (Fact.on_phone_dial)
        view = {**view, "items": view["desktop_items"]}
        if view.get("desktop_progress"):
            view["progress"] = view["desktop_progress"]
    items, minis = [], {}
    if view["kind"] == "home" and size == "phone" and any("phone_label" in i for i in view["items"]):
        view = {**view, "figSizes": HUB_FIG_SIZES_PHONE}  # all of them the kit's own classes
    for item in view["items"]:
        if size == "phone":  # a phone's wedge can say the same fact in fewer words
            item = {**item, "figure": phone_rupees(item.get("phone_figure", item["figure"])),
                    "label": phone_rupees(item.get("phone_label", item.get("label", "")))}
        _text(item["name"], "name")
        _text(item["figure"], "figure")
        _text(item.get("label") or "", "label")
        _text(item.get("miniLabel") or "", "mini label")
        kind = item.get("chart") or ""
        if kind and not item.get("state"):
            if "mini" not in item:
                raise ValueError(f"slice {item['name']!r} names a {kind} chart but gives none")
            minis[kind] = G.render_chart(item["mini"])
        href = item.get("href")
        items.append({**item, "href": str(escape(href)) if href else ""})

    if view["kind"] == "chapter":
        items = fitted(items, view.get("figSizes") or G.SIZES[size]["figSizesChapter"], size)
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
