"""The Scope dial and its charts, laid out on the server (handoff section 8, T3).

A line-for-line port of the design kit's docs/design/scope-kit/static/js/scope-geometry.js:
pure functions from a view (names, figures, states) to SVG path strings and markup. The
dial is drawn here, with the trader's real figures, because its layout depends on them -
a figure too wide for its wedge sets as a stacked pair - and because a page that needs no
JavaScript to draw its dial is a page that works before htmx loads.

tests/unit/api/test_scope_geometry.py holds every function to the outputs recorded from
the JavaScript itself (tests/fixtures/scope_geometry/cases.json), byte for byte. Where
Python and JavaScript differ, the JavaScript wins and the difference is written out here:

* Rounding. Math.round sends a half up (toward +infinity); Python's round() sends it to
  even. js_round() is Math.round.
* Printing. A JavaScript number prints without a trailing ".0" and -0 prints as "0";
  js_str() prints a float the same way. Both print the shortest digits that round-trip.
* Remainder. JavaScript's % keeps the dividend's sign, as math.fmod does; Python's %
  does not.
* Math.max of nothing is -Infinity; max() of nothing raises. Every call here has values.

One addition, which the kit's JavaScript does not have: on Home the centre's caption
may be given as captionLines. The kit always writes "of your result / in five days";
when the share is not a percentage (handoff 7, the second state) that would be false.
Without captionLines the output is the kit's, byte for byte.

Not ported: scopeInAt and easeInOut, which script frames for the prototype. The live
motion is CSS (motion.css), and nothing on the server animates.
"""

from __future__ import annotations

import math

# ---------- Numbers and paths ----------


def js_round(x: float) -> float:
    """JavaScript's Math.round: a half goes up, toward +infinity."""
    return math.floor(x + 0.5)


def js_str(n: float) -> str:
    """A number as JavaScript prints it: 179 not 179.0, 0 not -0."""
    if isinstance(n, bool):
        return "true" if n else "false"
    if n == int(n):
        return str(int(n))
    return repr(float(n))


def fmt(n: float) -> str:
    """Round to 2 decimals and print without trailing zeros, as the kit does."""
    return js_str(js_round(n * 100) / 100)


def clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def polar(cx: float, cy: float, r: float, a: float) -> tuple[float, float]:
    """Point at radius r and angle a (degrees clockwise from twelve o'clock)."""
    t = a * math.pi / 180
    return (cx + r * math.sin(t), cy - r * math.cos(t))


def radial(cx: float, cy: float, a: float, r1: float, r2: float) -> str:
    """Radial line at angle a from r1 to r2."""
    p, q = polar(cx, cy, r1, a), polar(cx, cy, r2, a)
    return f"M{fmt(p[0])} {fmt(p[1])}L{fmt(q[0])} {fmt(q[1])}"


def arc(cx: float, cy: float, r: float, a1: float, a2: float) -> str:
    """Arc on radius r from a1 to a2, clockwise."""
    if a2 - a1 < 0.2:
        return ""
    p, q = polar(cx, cy, r, a1), polar(cx, cy, r, a2)
    large = 1 if a2 - a1 > 180 else 0
    return f"M{fmt(p[0])} {fmt(p[1])}A{fmt(r)} {fmt(r)} 0 {large} 1 {fmt(q[0])} {fmt(q[1])}"


def circle(cx: float, cy: float, r: float) -> str:
    """A full circle as a path of two half arcs."""
    return (
        f"M{fmt(cx - r)} {fmt(cy)}a{fmt(r)} {fmt(r)} 0 1 0 {fmt(2 * r)} 0"
        f"a{fmt(r)} {fmt(r)} 0 1 0 {fmt(-2 * r)} 0"
    )


def wedge(cx: float, cy: float, a1: float, a2: float, r1: float, r2: float) -> str:
    """Annular wedge between radii r1 < r2 and angles a1 < a2; a full circle is a ring."""
    if a2 - a1 >= 359.9:
        return circle(cx, cy, r2) + circle(cx, cy, r1)
    p1, p2 = polar(cx, cy, r2, a1), polar(cx, cy, r2, a2)
    p3, p4 = polar(cx, cy, r1, a2), polar(cx, cy, r1, a1)
    lg = 1 if a2 - a1 > 180 else 0
    return (
        f"M{fmt(p1[0])} {fmt(p1[1])}A{fmt(r2)} {fmt(r2)} 0 {lg} 1 {fmt(p2[0])} {fmt(p2[1])}"
        f"L{fmt(p3[0])} {fmt(p3[1])}A{fmt(r1)} {fmt(r1)} 0 {lg} 0 {fmt(p4[0])} {fmt(p4[1])}Z"
    )


# ---------- Text measurement ----------

# IBM Plex Sans 500 advance widths in em, by character class: close enough to decide
# line breaks without a browser. Copied verbatim from the kit.
CHAR_WIDTH = {
    "space": 0.25,
    "narrow": 0.25,
    "punct": 0.27,
    "semi": 0.34,
    "wide": 0.85,
    "cap": 0.64,
    "digit": 0.6,
    "other": 0.55,
}


def _sans_char_em(ch: str) -> float:
    if ch == " ":
        return CHAR_WIDTH["space"]
    if ch in "iljI|!":
        return CHAR_WIDTH["narrow"]
    if ch in ".,:;'’":
        return CHAR_WIDTH["punct"]
    if ch in "frt()[]":
        return CHAR_WIDTH["semi"]
    if ch in "mwMW":
        return CHAR_WIDTH["wide"]
    if "A" <= ch <= "Z":
        return CHAR_WIDTH["cap"]
    if "0" <= ch <= "9":
        return CHAR_WIDTH["digit"]
    return CHAR_WIDTH["other"]


def sans_width(s: str, size: float) -> float:
    """Width in px of a string in IBM Plex Sans at size px."""
    w = 0.0
    for ch in s:
        w += _sans_char_em(ch)
    return w * size


def mono_width(s: str, size: float) -> float:
    """Width in px of a string in IBM Plex Mono at size px: every glyph is 0.6 em."""
    return len(s) * 0.6 * size


# ---------- The dial ----------

# Phone: a 260 px dial on a 358 px stage. Desktop: 440 px on 640 x 560. `edge` is how
# far a name may run from the stage centre (phone: to 8 px from a 390 px screen edge).
SIZES = {
    "phone": {
        "stageW": 358,
        "stageH": 358,
        "R": 130,
        "nameSize": 11,
        "nameLine": 14,
        "edge": 187,
        "figSizesHome": [22, 18],
        "figSizesChapter": [18, 15],
    },
    "desktop": {
        "stageW": 640,
        "stageH": 560,
        "R": 220,
        "nameSize": 13,
        "nameLine": 17,
        "edge": 312,
        "figSizesHome": [32, 22],
        "figSizesChapter": [22, 18],
    },
}

# Names that may take three lines on the phone dial; every other name takes two at most.
THREE_LINE_NAMES = [
    "Where the money came from",
    "Where your results came from",
    "What we have not told you",
]


def radii(R: float) -> dict:
    """Radii scaled from the kit's 300-unit master drawing (outer ring at 149.5)."""
    u = R / 150
    return {
        "u": u,
        "outer": 149.5 * u,  # outer hairline ring
        "tickEnd": 149 * u,  # all ticks end here
        "minorStart": 145.5 * u,  # minor tick, every 2.5 degrees
        "midStart": 142.5 * u,  # mid tick, every 30 degrees
        "majorStart": 139.5 * u,  # major tick, at each sector divider
        "inner": 137 * u,  # inner ring: the arc runs on it
        "divStart": 70 * u,  # dividers stop short of the centre ring...
        "divEnd": 132 * u,  # ...and of the inner ring
        "ring": 64 * u,  # fine ring around the centre disc
        "disc": 60 * u,  # centre disc
    }


def sectors(n: int, is_home: bool) -> dict:
    """Home: four chapters on the diagonals. Chapter: fact 1 centred at twelve o'clock,
    except four facts, which take the diagonals."""
    span = 360 / n
    offset = 0 if (is_home or n == 4) else -span / 2
    out = []
    for i in range(n):
        a1 = offset + i * span
        out.append({"index": i, "start": a1, "end": a1 + span, "mid": a1 + span / 2})
    return {"span": span, "offset": offset, "dividers": [s["start"] for s in out], "slices": out}


def _norm(a: float) -> float:
    return math.fmod(math.fmod(a, 360) + 360, 360)


def ticks(cx: float, cy: float, rr: dict, dividers: list, rotation: float = 0) -> dict:
    """The bezel: a tick every 2.5 degrees, major at each divider, mid every 30."""
    rotation = rotation or 0

    def is_div(a: float) -> bool:
        return any(abs(_norm(a) - _norm(d)) < 0.01 for d in dividers)

    minor = mid = major = ""
    for j in range(144):
        a = j * 2.5
        if is_div(a):
            continue
        if math.fmod(a, 30) == 0:
            mid += radial(cx, cy, a + rotation, rr["midStart"], rr["tickEnd"])
        else:
            minor += radial(cx, cy, a + rotation, rr["minorStart"], rr["tickEnd"])
    for a in dividers:
        major += radial(cx, cy, a + rotation, rr["majorStart"], rr["tickEnd"])
    return {"minor": minor, "mid": mid, "major": major}


def name_label(
    name: str, mid: float, cx: float, cy: float, rr: dict, size: dict, opts: dict | None = None
) -> dict:
    """A slice's name, upright and never curved, just outside the bezel at its arc
    midpoint on a 12 px leader: left-aligned on the right half, right-aligned on the
    left, centred at twelve and six. Two lines at most, three only for THREE_LINE_NAMES."""
    opts = opts or {}
    s = math.sin(mid * math.pi / 180)
    c = math.cos(mid * math.pi / 180)
    leader_start, leader_end = rr["outer"] + 2, rr["outer"] + 2 + 12
    e = polar(cx, cy, leader_end, mid)
    centred = abs(s) < 0.26
    avail = math.inf if centred else size["edge"] - abs(e[0] - cx) - 4

    def w(t: str) -> float:
        return sans_width(t, size["nameSize"])

    lines = [name]
    too_wide_centred = centred and w(name) > (260 if size["R"] > 150 else 170)
    if w(name) > avail or too_wide_centred:
        words = name.split(" ")
        best, bw = None, math.inf
        for j in range(1, len(words)):
            pair = [" ".join(words[:j]), " ".join(words[j:])]
            m = max(w(pair[0]), w(pair[1]))
            if m < bw:
                bw, best = m, pair
        if best:
            lines = best
        allow_three = name in (opts.get("threeLineNames") or [])
        if not centred and allow_three and max(w(line) for line in lines) > avail:
            b3, m3 = None, math.inf
            for a1 in range(1, len(words) - 1):
                for a2 in range(a1 + 1, len(words)):
                    triple = [" ".join(words[:a1]), " ".join(words[a1:a2]), " ".join(words[a2:])]
                    m = max(w(t) for t in triple)
                    if m < m3:
                        m3, b3 = m, triple
            if b3:
                lines = b3
    h = len(lines) * size["nameLine"]
    x = e[0]
    if centred:
        align = "center"
        top = e[1] - 3 - h if c > 0 else e[1] + 3
    elif s > 0:
        align, x, top = "left", e[0] + 4, e[1] - h / 2
    else:
        align, x, top = "right", e[0] - 4, e[1] - h / 2
    return {
        "lines": lines,
        "align": align,
        "x": x,
        "top": top,
        "lineHeight": size["nameLine"],
        "leader": radial(cx, cy, mid, leader_start, leader_end),
    }


def stacked_split(fig: str) -> list[str] | None:
    """Where a figure breaks when its wedge is too narrow: "[N] of [N]" -> "[N]" over
    "of [N]"; otherwise at the last space; None if it has no space."""
    k = fig.find(" of ")
    if k > 0:
        return [fig[:k], fig[k + 1 :]]
    j = fig.rfind(" ")
    return [fig[:j], fig[j + 1 :]] if j > 0 else None


def slice_block(item: dict, fig_size: float, stacked: bool) -> dict:
    """The box a slice's contents take: number, figure head, [tail], mini chart or state."""
    state = item.get("state") or ""
    split = stacked_split(item["figure"]) if (not state and stacked) else None
    head = "—" if state else (split[0] if split else item["figure"])
    tail = split[1] if split else ""
    tight = head.find(" · ") > 0
    head_w = mono_width(head, fig_size) - (2 * 0.45 * fig_size if tight else 0)
    tail_w = mono_width(tail, 11)
    lh = js_round(fig_size * 1.15)
    row_a = 13 + 4 + lh + (13 if tail else 0)
    row_b = 28 if state else (14 if item.get("chart") else 0)
    width = max(head_w, tail_w, (66 if state else 36) if row_b else 0, 8)
    return {
        "head": head,
        "tail": tail,
        "tight": tight,
        "figSize": fig_size,
        "lineHeight": lh,
        "rowA": row_a,
        "rowB": row_b,
        "w": width,
        "h": row_a + (3 + row_b if row_b else 0),
    }


def _sign(x: float) -> int:
    return 1 if x > 0 else -1 if x < 0 else 0


def block_clearance(slc: dict, span: float, rc: float, b: dict, rr: dict) -> float:
    """Clearance in px (negative: a collision) of a block centred on the slice's
    bisector at radius rc, against the centre ring, the inner ring and its dividers."""
    s = math.sin(slc["mid"] * math.pi / 180)
    c = -math.cos(slc["mid"] * math.pi / 180)
    px, py = rc * s, rc * c
    x0, x1, y0, y1 = px - b["w"] / 2, px + b["w"] / 2, py - b["h"] / 2, py + b["h"] / 2
    corners = [(x0, y0), (x1, y0), (x0, y1), (x1, y1)]
    nx, ny = max(x0, min(0, x1)), max(y0, min(0, y1))
    m = min(
        math.hypot(nx, ny) - rr["ring"] - 5,
        rr["inner"] - 4 - max(math.hypot(q[0], q[1]) for q in corners),
    )
    if span < 359:
        for a in (slc["start"], slc["end"]):
            ax, ay = math.sin(a * math.pi / 180), -math.cos(a * math.pi / 180)
            side = _sign(ax * py - ay * px) or 1
            for q in corners:
                if q[0] * ax + q[1] * ay < 0:
                    continue
                m = min(m, (ax * q[1] - ay * q[0]) * side - 4)
    return m


def layout_contents(items: list, sec: dict, rr: dict, fig_sizes: list) -> dict:
    """One figure size per view, the largest that fits. Every slice starts on one line;
    the least clear stacks until all fit; any stacked figure that would now fit on one
    line goes back. One shared radius when every slice fits at it."""

    def best(blocks: list) -> dict:
        br, bs = (rr["divStart"] + rr["divEnd"]) / 2, -math.inf
        rc = rr["ring"]
        while rc <= rr["inner"]:
            sc = math.inf
            for i, b in enumerate(blocks):
                sc = min(sc, block_clearance(sec["slices"][i], sec["span"], rc, b, rr))
            if sc > bs:
                bs, br = sc, rc
            rc += 0.5
        return {"rc": br, "score": bs}

    def can_stack(it: dict) -> bool:
        return not it.get("state") and stacked_split(it["figure"]) is not None

    for si, fs in enumerate(fig_sizes):
        forms = [False] * len(items)
        blocks = [slice_block(it, fs, False) for it in items]
        r = best(blocks)
        passes = 0
        while passes < 8 and r["score"] < 0:
            wi, wv = -1, math.inf
            for i, b in enumerate(blocks):
                if not forms[i] and can_stack(items[i]):
                    cl = block_clearance(sec["slices"][i], sec["span"], r["rc"], b, rr)
                    if cl < wv:
                        wv, wi = cl, i
            if wi < 0:
                break
            forms[wi] = True
            blocks = [slice_block(it, fs, forms[i]) for i, it in enumerate(items)]
            r = best(blocks)
            passes += 1
        if r["score"] >= 0:
            for i in range(len(items)):
                if not forms[i]:
                    continue
                f2 = list(forms)
                f2[i] = False
                b2 = [slice_block(x, fs, f2[j]) for j, x in enumerate(items)]
                r2 = best(b2)
                if r2["score"] >= 0:
                    forms[i], blocks, r = False, b2, r2
            return {
                "blocks": blocks,
                "radius": [r["rc"]] * len(blocks),
                "stacked": forms,
                "figSize": fs,
            }
        if si == len(fig_sizes) - 1:
            own = []
            for i, b in enumerate(blocks):
                br, bs = r["rc"], -math.inf
                rc = rr["ring"]
                while rc <= rr["inner"]:
                    cl = block_clearance(sec["slices"][i], sec["span"], rc, b, rr)
                    if cl > bs:
                        bs, br = cl, rc
                    rc += 0.5
                own.append(br)
            return {"blocks": blocks, "radius": own, "stacked": forms, "figSize": fs}
    raise ValueError("no figure sizes to lay out with")


def build_dial(view: dict, size_name: str = "phone", opts: dict | None = None) -> dict:
    """Every primitive of the dial.

    view = {"kind": "home" | "chapter",
            "items": [{"name", "figure", "href", "chart"?, "state"?, "opened"?}, ...],
            "centre": {"figure", "caption"} on home, {"name", "scopeHref"} in a chapter}
    """
    opts = opts or {}
    size_name = size_name or "phone"
    size = SIZES[size_name]
    cx, cy, rr = size["stageW"] / 2, size["stageH"] / 2, radii(size["R"])
    is_home = view["kind"] == "home"
    sec = sectors(len(view["items"]), is_home)
    t = ticks(cx, cy, rr, sec["dividers"], 0)
    lay = layout_contents(
        view["items"], sec, rr, size["figSizesHome"] if is_home else size["figSizesChapter"]
    )
    slices = []
    for i, sl in enumerate(sec["slices"]):
        it, b = view["items"][i], lay["blocks"][i]
        q = polar(cx, cy, lay["radius"][i], sl["mid"])
        top = q[1] - b["h"] / 2
        state = it.get("state") or ""
        figure = it["figure"]
        slices.append(
            {
                "index": i,
                "number": str(i + 1),
                "name": it["name"],
                "href": it["href"],
                "state": state,
                "opened": bool(it.get("opened")),
                "start": sl["start"],
                "end": sl["end"],
                "mid": sl["mid"],
                "hit": wedge(cx, cy, sl["start"], sl["end"], rr["ring"], rr["outer"]),
                "focusRing": wedge(
                    cx,
                    cy,
                    sl["start"] + 1.5,
                    sl["end"] - 1.5,
                    rr["divStart"] - 4 * rr["u"],
                    rr["inner"] - 2,
                ),
                "lift": wedge(
                    cx, cy, sl["start"], sl["end"], rr["divStart"] - 6 * rr["u"], rr["inner"]
                ),
                "hatch": (
                    wedge(cx, cy, sl["start"], sl["end"], rr["divStart"], rr["inner"])
                    if state == "not-enough"
                    else ""
                ),
                "dashed": (
                    wedge(
                        cx,
                        cy,
                        sl["start"] + 1.5,
                        sl["end"] - 1.5,
                        rr["divStart"] + 3,
                        rr["inner"] - 3,
                    )
                    if state == "not-in-file"
                    else ""
                ),
                "openedMark": polar(cx, cy, rr["inner"] - 3 * rr["u"], sl["mid"])
                if it.get("opened")
                else None,
                "contents": {
                    "x": q[0],
                    "numberY": top,
                    "headY": top + 17,
                    "tailY": top + 17 + b["lineHeight"],
                    "chartY": top + b["rowA"] + 3,
                    "head": b["head"],
                    "tail": b["tail"],
                    "tight": b["tight"],
                    "figSize": b["figSize"],
                    "lineHeight": b["lineHeight"],
                    "chart": "" if state else (it.get("chart") or ""),
                    "tone": "state"
                    if state
                    else ("rupee" if figure.startswith(("−₹", "-₹")) else "plain"),
                },
                "label": name_label(it["name"], sl["mid"], cx, cy, rr, size, opts),
            }
        )
    return {
        "size": size_name,
        "stageW": size["stageW"],
        "stageH": size["stageH"],
        "cx": cx,
        "cy": cy,
        "R": size["R"],
        "radii": rr,
        "kind": view["kind"],
        "centre": view.get("centre") or {},
        "outerRing": circle(cx, cy, rr["outer"]),
        "innerRing": circle(cx, cy, rr["inner"]),
        "ticks": t,
        "dividers": [radial(cx, cy, a, rr["divStart"], rr["divEnd"]) for a in sec["dividers"]],
        "arc": "" if is_home else arc(cx, cy, rr["inner"], -43, 43),
        "disc": circle(cx, cy, rr["disc"]),
        "centreRing": circle(cx, cy, rr["ring"]),
        "slices": slices,
        "figSize": lay["figSize"],
    }


# ---------- The SVG ----------


def _esc(s) -> str:
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _text_block(
    lines: list, x: float, top: float, line_height: float, size: float, align: str, cls: str
) -> str:
    """Lines as an SVG <text> of tspans; `top` is the top of the first line box."""
    anchor = "start" if align == "left" else "end" if align == "right" else "middle"
    base = top + line_height / 2 + size * 0.35
    spans = "".join(
        f'<tspan x="{fmt(x)}" dy="{js_str(line_height) if i else 0}">{_esc(line)}</tspan>'
        for i, line in enumerate(lines)
    )
    return f'<text class="{cls}" x="{fmt(x)}" y="{fmt(base)}" text-anchor="{anchor}">{spans}</text>'


def render_dial_svg(d: dict, mini_charts: dict | None = None) -> str:
    """The dial as inline SVG; class names are components.css's (.scope__*).

    Text in names and figures is escaped; an href is written as given, so the caller
    passes it already escaped (the dial macro does).
    """
    mini_charts = mini_charts or {}
    o = []
    pad = 40  # room for names outside the stage box on the phone
    label = (
        "The Scope: four chapters of your story"
        if d["kind"] == "home"
        else "The Scope inside this chapter"
    )
    o.append(
        f'<svg class="scope__svg" viewBox="{-pad} 0 {d["stageW"] + 2 * pad} {d["stageH"]}" '
        f'width="{d["stageW"] + 2 * pad}" height="{d["stageH"]}" role="img" aria-label="{label}">'
    )
    o.append(
        '<defs><pattern id="scope-hatch" width="5" height="5" patternUnits="userSpaceOnUse" '
        'patternTransform="rotate(45)"><path d="M0 0V5" class="scope__hatch-line"/></pattern></defs>'
    )
    o.append(f'<path class="scope__outer" d="{d["outerRing"]}"/>')
    for s in d["slices"]:
        if s["hatch"]:
            o.append(f'<path class="scope__state-hatch" d="{s["hatch"]}"/>')
        if s["dashed"]:
            o.append(f'<path class="scope__state-dashed" d="{s["dashed"]}"/>')
    tk = d["ticks"]
    o.append(
        f'<g class="scope__bezel"><path class="scope__tick scope__tick--minor" d="{tk["minor"]}"/>'
        f'<path class="scope__tick scope__tick--mid" d="{tk["mid"]}"/>'
        f'<path class="scope__tick scope__tick--major" d="{tk["major"]}"/></g>'
    )
    o.append(f'<path class="scope__inner" d="{d["innerRing"]}"/>')
    if d["arc"]:
        o.append(f'<path class="scope__arc" d="{d["arc"]}"/>')
    dividers = "".join(f'<path class="scope__divider" d="{p}"/>' for p in d["dividers"])
    o.append(f'<g class="scope__dividers">{dividers}</g>')
    for s in d["slices"]:
        c = s["contents"]
        state_class = f" scope__slice--{s['state']}" if s["state"] else ""
        o.append(
            f'<a class="scope__slice{state_class}" href="{s["href"]}" '
            f'aria-label="{_esc(s["number"] + ". " + s["name"] + ".")}">'
        )
        o.append(
            f'<path class="scope__hit" d="{s["hit"]}"/><path class="scope__lift" d="{s["lift"]}"/>'
            f'<path class="scope__focus" d="{s["focusRing"]}"/>'
        )
        if s["openedMark"]:
            r = 2 if d["size"] == "phone" else 2.5
            o.append(
                f'<circle class="scope__opened" cx="{fmt(s["openedMark"][0])}" '
                f'cy="{fmt(s["openedMark"][1])}" r="{js_str(r)}"/>'
            )
        o.append(
            _text_block([s["number"]], c["x"], c["numberY"], 13, 11, "center", "scope__number")
        )
        tight = " scope__figure--tight" if c["tight"] else ""
        o.append(
            _text_block(
                [c["head"]],
                c["x"],
                c["headY"],
                c["lineHeight"],
                c["figSize"],
                "center",
                f"scope__figure scope__figure--s{js_str(c['figSize'])} "
                f"scope__figure--{c['tone']}{tight}",
            )
        )
        if c["tail"]:
            o.append(
                _text_block(
                    [c["tail"]],
                    c["x"],
                    c["tailY"],
                    13,
                    11,
                    "center",
                    f"scope__figure-tail scope__figure--{c['tone']}",
                )
            )
        if s["state"]:
            words = (
                ["not enough", "trades yet"]
                if s["state"] == "not-enough"
                else ["not in", "your file"]
            )
            o.append(_text_block(words, c["x"], c["chartY"], 14, 11, "center", "scope__state"))
        elif c["chart"]:
            o.append(
                f'<g class="scope__mini chart chart--on-navy" '
                f'transform="translate({fmt(c["x"] - 18)} {fmt(c["chartY"])})">'
                f"{mini_charts.get(c['chart'], '')}</g>"
            )
        o.append("</a>")
        o.append(f'<path class="scope__leader" d="{s["label"]["leader"]}"/>')
        lb = s["label"]
        o.append(
            _text_block(
                lb["lines"], lb["x"], lb["top"], lb["lineHeight"], 11, lb["align"], "scope__name"
            )
        )
    o.append(
        f'<path class="scope__disc" d="{d["disc"]}"/><path class="scope__centre-ring" d="{d["centreRing"]}"/>'
    )
    R = d["radii"]
    phone = d["size"] == "phone"
    if d["kind"] == "home":
        figure = d["centre"].get("figure") or "{{ five_day_share_percent }}%"
        o.append(
            _text_block(
                [figure],
                d["cx"],
                d["cy"] - (26 if phone else 38),
                24 if phone else 34,
                22 if phone else 32,
                "center",
                "scope__centre-figure",
            )
        )
        o.append(
            _text_block(
                d["centre"].get("captionLines") or ["of your result", "in five days"],
                d["cx"],
                d["cy"] + 2,
                13,
                11,
                "center",
                "scope__centre-caption",
            )
        )
    else:
        words = (d["centre"].get("name") or "").split(" ")
        max_w, fs = R["disc"] * 1.55, 11 if phone else 15
        lines, cur = [], ""
        for word in words:
            t = f"{cur} {word}" if cur else word
            if sans_width(t, fs) > max_w and cur:
                lines.append(cur)
                cur = word
            else:
                cur = t
        if cur:
            lines.append(cur)
        lh = js_round(fs * 1.25)
        tot = len(lines) * lh + 4 + 13
        o.append(
            _text_block(lines, d["cx"], d["cy"] - tot / 2, lh, fs, "center", "scope__centre-name")
        )
        scope_href = d["centre"].get("scopeHref") or "/scope"
        o.append(
            f'<a class="scope__centre-link" href="{scope_href}" aria-label="Scope out to all four chapters">'
            f"{_text_block(['Scope'], d['cx'], d['cy'] + tot / 2 - 13, 13, 11, 'center', 'scope__centre-scope')}"
            f'<circle cx="{fmt(d["cx"])}" cy="{fmt(d["cy"])}" r="{fmt(R["disc"])}" class="scope__centre-hit"/></a>'
        )
    o.append("</svg>")
    return "".join(o)


# ---------- The lens (56 px) ----------


def build_lens(n_facts: int, fact_index: int) -> dict:
    """The lens in a fact page's path bar: the chapter's bezel and dividers, the fact lit."""
    c, sec = 28, sectors(n_facts, False)
    divs = [_norm(a) for a in sec["dividers"]]
    minor = mid = major = div = ""
    for a in range(0, 360, 10):
        if a in divs:
            continue
        if a % 30 == 0:
            mid += radial(c, c, a, 24, 27)
        else:
            minor += radial(c, c, a, 25, 27)
    for a in divs:
        major += radial(c, c, a, 22.5, 27)
        div += radial(c, c, a, 11.5, 20)
    s = sec["slices"][fact_index]
    return {
        "minor": minor,
        "mid": mid,
        "major": major,
        "div": div,
        "lit": wedge(c, c, s["start"], s["end"], 10.5, 21.5),
        "arc": arc(c, c, 21.5, -43, 43),
        "outer": circle(c, c, 27.5),
        "inner": circle(c, c, 21.5),
        "ring": circle(c, c, 10.5),
        "disc": circle(c, c, 9),
    }


# ---------- Charts ----------
# Every chart returns {"w", "h", "parts"}, parts a list of {"role", "d"}; the role is a
# CSS class suffix (.chart__<role>): ink, light, faint, red, green, hatch, axis, stroke,
# dash. Mini charts (36 x 14) are the same functions at a small w and h.


def _r2(x: float, y: float, w: float, h: float) -> str:
    return f"M{fmt(x)} {fmt(y)}h{fmt(w)}v{fmt(h)}h{fmt(-w)}Z"


def _parts(m: dict) -> list:
    return [{"role": k, "d": v} for k, v in m.items() if v]


def _chart(w, h, m):
    return {"w": w, "h": h, "parts": _parts(m)}


def chart_worst(daily_net: list, w: float, h: float) -> dict:
    """Net (gross) per trading day; the five worst days in ink, the rest light."""
    n = len(daily_net)
    bw, mx, z = w / n, max([abs(v) for v in daily_net] + [1]), h * 0.45
    order = sorted(range(n), key=lambda i: daily_net[i])[:5]
    m = {"ink": "", "light": "", "axis": f"M0 {fmt(z)}H{js_str(w)}"}
    for i, v in enumerate(daily_net):
        bh = max(0.6, abs(v) / mx * h * 0.5)
        r = _r2(i * bw + bw * 0.15, z - bh if v > 0 else z, bw * 0.7, bh)
        m["ink" if i in order else "light"] += r
    return _chart(w, h, m)


def chart_share(share: float, w: float, h: float, mini: bool = False) -> dict:
    """The five worst days as a share of the whole result, with a bracket for the whole."""
    bh, y0 = (h * 0.7, h * 0.15) if mini else (h * 0.42, h * 0.08)
    m = {
        "ink": _r2(0, y0, w * share, bh),
        "light": _r2(w * share + 1, y0, w * (1 - share) - 1, bh),
        "stroke": "",
    }
    if not mini:
        y, t = h * 0.8, h * 0.13
        m["stroke"] = (
            f"M0.5 {fmt(y - t)}V{fmt(y + t)}M0.5 {fmt(y)}H{fmt(w - 0.5)}M{fmt(w - 0.5)} {fmt(y - t)}V{fmt(y + t)}"
        )
    return _chart(w, h, m)


def chart_money(best5: list, worst5: list, w: float, h: float) -> dict:
    """Best five (green, to the right) and worst five (red, to the left) trades."""
    mx = max(list(best5) + [abs(v) for v in worst5] + [1])
    rh, cx = h / 10, w / 2
    m = {"green": "", "red": "", "axis": f"M{fmt(cx)} 0V{fmt(h)}"}
    for i, v in enumerate(best5):
        m["green"] += _r2(cx, i * rh + rh * 0.2, v / mx * cx * 0.96, rh * 0.6)
    for i, v in enumerate(worst5):
        length = abs(v) / mx * cx * 0.96
        m["red"] += _r2(cx - length, (i + 5) * rh + rh * 0.2, length, rh * 0.6)
    return _chart(w, h, m)


def _lower_median(a: list) -> float:
    s = sorted(a)
    return s[(len(s) - 1) // 2] if s else 0


def chart_hold(
    win_mins: list, loss_mins: list, max_mins: float, w: float, h: float, mini: bool = False
) -> dict:
    """Minutes open, a dot per trade: winners (ink) above, losers (faint) below, a
    median tick on each."""
    ys, r, t = [h * 0.3, h * 0.72], (1.3 if mini else 3.2), (3 if mini else 8)

    def x(v: float) -> float:
        return min(1, v / max_mins) * w

    mw, ml = x(_lower_median(win_mins)), x(_lower_median(loss_mins))
    m = {
        "ink": "".join(circle(x(v), ys[0], r) for v in win_mins),
        "faint": "".join(circle(x(v), ys[1], r) for v in loss_mins),
        "stroke": f"M{fmt(mw)} {fmt(ys[0] - t)}V{fmt(ys[0] + t)}M{fmt(ml)} {fmt(ys[1] - t)}V{fmt(ys[1] + t)}",
        "axis": f"M0 {fmt(ys[0])}H{js_str(w)}M0 {fmt(ys[1])}H{js_str(w)}",
    }
    return _chart(w, h, m)


def chart_strike(
    winners: int, losers: int, level: int, w: float, h: float, mini: bool = False
) -> dict:
    """Winners, losers and level trades as one bar."""
    tot = max(1, winners + losers + level)
    bh, y0 = (h * 0.7, h * 0.15) if mini else (h * 0.4, h * 0.3)
    a, b = w * winners / tot, w * losers / tot
    return _chart(
        w,
        h,
        {
            "ink": _r2(0, y0, a, bh),
            "faint": _r2(a + 1, y0, b - 1, bh),
            "hatch": _r2(a + b + 1, y0, w - a - b - 1, bh) if level else "",
        },
    )


def chart_run(
    n_trades: int, run_start: int, run_length: int, w: float, h: float, mini: bool = False
) -> dict:
    """A square per trade in order; the longest losing run in ink, bracketed."""
    g = w / n_trades
    s = min(3 if mini else 7, g * 0.8)
    m = {"ink": "", "light": "", "stroke": ""}
    for i in range(n_trades):
        r = _r2(i * g + (g - s) / 2, h * 0.5 - s / 2 - (0 if mini else 6), s, s)
        m["ink" if run_start <= i < run_start + run_length else "light"] += r
    if not mini:
        m["stroke"] = (
            f"M{fmt(run_start * g + 2)} {fmt(h * 0.5 + 6)}V{fmt(h * 0.5 + 12)}"
            f"H{fmt((run_start + run_length) * g - 2)}V{fmt(h * 0.5 + 6)}"
        )
    return _chart(w, h, m)


def chart_clock(hour_net: list, few_hours: list, w: float, h: float) -> dict:
    """Net (gross) by the hour a trade was opened; hours with few trades hatched."""
    n = len(hour_net)
    bw, z, mx = w / n, h * 0.5, max([abs(v) for v in hour_net] + [1])
    m = {"green": "", "red": "", "hatch": "", "axis": f"M0 {fmt(z)}H{js_str(w)}"}
    for i, v in enumerate(hour_net):
        bh = max(0.6, abs(v) / mx * h * 0.46)
        r = _r2(i * bw + bw * 0.18, z - bh if v > 0 else z, bw * 0.64, bh)
        m["hatch" if i in few_hours else "green" if v > 0 else "red"] += r
    return _chart(w, h, m)


def chart_down(after_two: float, others: float, w: float, h: float, mini: bool = False) -> dict:
    """Average result after two straight losses (top) against every other qualifying
    trade (bottom)."""
    mx = max(abs(after_two), abs(others), 1)
    bh = h * 0.3 if mini else h * 0.26
    red = _r2(0, h * 0.08 if mini else h * 0.12, w * abs(after_two) / mx, bh) + _r2(
        0, h * 0.58 if mini else h * 0.6, w * abs(others) / mx, bh
    )
    return _chart(w, h, {"red": red, "axis": f"M0.5 0V{js_str(h)}"})


def chart_busy(day_counts: list, normal: float, w: float, h: float) -> dict:
    """Trades per day; the busiest day in ink; the normal day as a dashed line."""
    n = len(day_counts)
    bw, mx = w / n, max(list(day_counts) + [1])
    bi = day_counts.index(mx) if mx in day_counts else -1
    m = {"ink": "", "light": "", "dash": f"M0 {fmt(h - normal / mx * h * 0.9)}H{js_str(w)}"}
    for i, v in enumerate(day_counts):
        bh = v / mx * h * 0.9
        m["ink" if i == bi else "light"] += _r2(i * bw + bw * 0.18, h - bh, bw * 0.64, bh)
    return _chart(w, h, m)


def chart_read(rows_read: int, rows_total: int, w: float, h: float, mini: bool = False) -> dict:
    """Rows read (ink) and rows set aside (hatched)."""
    f = rows_read / max(1, rows_total)
    bh, y0 = (h * 0.7, h * 0.15) if mini else (h * 0.4, h * 0.3)
    return _chart(
        w,
        h,
        {
            "ink": _r2(0, y0, w * f, bh),
            "hatch": _r2(w * f + 1, y0, w * (1 - f) - 1, bh) if f < 1 else "",
        },
    )


def chart_risk(
    budget: int, stop: int, premium: int, nothing: int, w: float, h: float, mini: bool = False
) -> dict:
    """Trades by what they were measured against: budget, stop, premium, nothing usable."""
    tot = max(1, budget + stop + premium + nothing)
    bh, y0 = (h * 0.7, h * 0.15) if mini else (h * 0.4, h * 0.3)
    a, b, c = w * budget / tot, w * stop / tot, w * premium / tot
    return _chart(
        w,
        h,
        {
            "ink": _r2(0, y0, a, bh),
            "faint": _r2(a + 1, y0, b - 1, bh),
            "light": _r2(a + b + 1, y0, c - 1, bh),
            "hatch": _r2(a + b + c + 1, y0, w - a - b - c - 1, bh),
        },
    )


def chart_notold(w: float, h: float, mini: bool = False) -> dict:
    """'What we have not told you' has no data: four quiet lines, like an unwritten page."""
    light = ""
    for i, v in enumerate([1, 0.86, 0.94, 0.6]):
        light += _r2(0, (i + 0.5) * h / 4 - (0.75 if mini else 2), v * w, 1.5 if mini else 4)
    return _chart(w, h, {"light": light})


CHARTS = {
    "worst": chart_worst,
    "share": chart_share,
    "money": chart_money,
    "hold": chart_hold,
    "strike": chart_strike,
    "run": chart_run,
    "clock": chart_clock,
    "down": chart_down,
    "busy": chart_busy,
    "read": chart_read,
    "risk": chart_risk,
    "notold": chart_notold,
}


def render_chart(c: dict, cls: str = "", wrap: bool = False) -> str:
    """A chart as SVG: its parts alone, or wrapped in an <svg> when wrap is true."""
    inner = "".join(f'<path class="chart__{p["role"]}" d="{p["d"]}"/>' for p in c["parts"])
    if not wrap:
        return inner
    return (
        f'<svg class="chart {cls or ""}" viewBox="0 0 {js_str(c["w"])} {js_str(c["h"])}" '
        f'width="{js_str(c["w"])}" height="{js_str(c["h"])}" aria-hidden="true">{inner}</svg>'
    )


# ---------- The trade strip ----------


def trade_strip(fill_times: list, width: float, height: float | None = None) -> dict:
    """A trade drawn to time: each fill a tick and a dot, the bar from first to last.
    fill_times are minutes since the trade's first fill."""
    height = height or 18
    t0 = min(fill_times)
    span = max(1, max(fill_times) - t0)
    xs = [4 + (t - t0) / span * (width - 8) for t in fill_times]
    base = height - 4.5
    return {
        "axis": f"M0 {fmt(base)}H{js_str(width)}",
        "ticks": "".join(f"M{fmt(x)} 5V{fmt(base - 1.5)}" for x in xs),
        "dots": "".join(circle(x, base, 3) for x in xs),
        "bar": f"M{fmt(xs[0])} 3H{fmt(xs[-1])}",
        # each fill lands 40 ms after the last, a 160 ms pause, then the bar in 200 ms
        "fillDelays": [i * 40 for i in range(len(xs))],
        "barDelay": len(xs) * 40 + 160,
    }
