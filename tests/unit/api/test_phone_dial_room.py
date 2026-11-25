"""TICKET-1039: the phone dial makes room inside the same 260 px.

The phone dial's fit limit was -13 px: a wedge's words could run 13 px into the spacing kept
around the centre ring, the inner ring and the dividers. On the phone the dial now draws a
smaller centre where its words allow (a chapter's name wraps into 50 units; Home's caption
"before charges" needs 56), runs the wedge band out to 147 units where the bezel ticks were,
gives a state's words the 56 px they take, keeps a 13 px figure as the last size, and writes
rupees short (the toolkit's ₹50.6k). So every wedge clears with the spacing intact: limit 0.
The desktop dial is drawn exactly as before.
"""

from __future__ import annotations

import hashlib
import re
from decimal import Decimal

import pytest

from services.production.api import charts
from services.production.api import dial as D
from services.production.api import scope_geometry as G
from tests.unit.api import figure_pages as P

PAGES = ("/mirror", "/mirror/chapter/1", "/mirror/chapter/2", "/mirror/chapter/3", "/mirror/chapter/4")
DESKTOP_ON_MAIN = {  # each page's desktop dial on main before this change (test_phone_dial_list's)
    "/mirror": "dc43965c99e54af2e71865fa7dec525fe65704149d05658b0936a2d17ddc4737",
    "/mirror/chapter/1": "e46f24ba3412133fc56f901c6bc7b0c91769f59e58b516ebc4c7d9dd2fa95408",
    "/mirror/chapter/2": "33301fff41ee1ea2529d14f40725b79554f8ba90de05584ac10fc8dff3bc2a9e",
    "/mirror/chapter/3": "92c4f85a96d11c91fbbf94ba0e3d0194780eb84fac534cf1ca51b0732bfa0dcf",
    "/mirror/chapter/4": "bcfed94c9cbbff5e1e5bd9d928a4d26731055ae99423a8ca1348d72550cbb572",
}


def dials(html: str) -> list[str]:
    return re.findall(r'<div class="scope[^"]*">.*?</svg>', html, flags=re.DOTALL)


def sha(text) -> str:
    return hashlib.sha256(str(text).encode()).hexdigest()

FIT_ON_A_PHONE = 0


@pytest.fixture()
def demo():
    """Every page with a dial on the demo upload, and the views its phone dials were laid out
    from (as scope_geometry.build_dial received them, phone words and all)."""
    from fastapi.testclient import TestClient

    from services.production.api.app import create_app

    seen: dict[str, list] = {}
    orig = G.build_dial

    def record(view, size_name="phone", opts=None):
        if size_name == "phone":
            seen.setdefault("now", []).append(view)
        return orig(view, size_name, opts)

    mp = pytest.MonkeyPatch()
    mp.setattr(G, "build_dial", record)
    try:
        app = create_app()
        client = TestClient(app)
        P._sign_up(client, app.state.engine, "visitor")
        P._consent(client)
        client.post("/upload/demo", data={"csrf_token": P._token(client, "/upload")},
                    follow_redirects=False)
        pages, views = {}, {}
        for path in PAGES:
            seen["now"] = []
            pages[path] = client.get(path).text
            views[path] = list(seen["now"])
    finally:
        mp.undo()
    return pages, views


# ---------- the geometry ----------

def test_the_phone_chapter_dial_has_a_smaller_centre_and_a_wider_band():
    rr, u = G.dial_radii("phone", False), 130 / 150
    assert rr["disc"] == pytest.approx(50 * u) and rr["ring"] == pytest.approx(53 * u)
    assert rr["divStart"] == pytest.approx(59 * u) and rr["inner"] == pytest.approx(147 * u)
    assert rr["outer"] == pytest.approx(149.5 * u)  # the dial's size is unchanged
    assert rr["stateW"] == 56


def test_the_phone_hub_keeps_room_for_its_caption():
    rr, u = G.dial_radii("phone", True), 130 / 150
    assert rr["disc"] == pytest.approx(56 * u) and rr["inner"] == pytest.approx(147 * u)
    caption = max(G.sans_width(w, 11) for w in ("your result,", "before charges"))
    y = 2 + 13 + 13  # the caption's last line ends here below the centre
    assert 2 * (rr["disc"] ** 2 - y**2) ** 0.5 >= caption


def test_the_desktop_dial_is_unchanged():
    for is_home in (True, False):
        assert G.dial_radii("desktop", is_home) == G.radii(220)


def test_the_phone_has_no_bezel_ticks():
    t = G.ticks(179, 179, G.dial_radii("phone", False), [0, 120, 240])
    assert t == {"minor": "", "mid": "", "major": ""}


# ---------- short rupees on the phone ----------

@pytest.mark.parametrize(("text", "want"), [
    ("−₹47,780", "−₹47.8k"), ("₹11,492", "₹11.5k"), ("came to\n−₹50,645", "came to\n−₹50.6k"),
    ("₹620", "₹620"), ("−₹1,23,456", "−₹1.2L"), ("46 of 100", "46 of 100"), ("₹11.5k", "₹11.5k"),
])
def test_phone_rupees_are_the_toolkits_short_form(text, want):
    assert D.phone_rupees(text) == want


def test_one_formatter_writes_them():
    assert D.phone_rupees("−₹47,780") == charts.short(Decimal(-47780))


def test_the_phone_dial_writes_rupees_short_and_the_desktop_whole(demo):
    pages, _ = demo
    phone, desk = dials(pages["/mirror/chapter/1"])
    shown = re.sub(r'aria-label="[^"]*"', "", phone)  # what a phone draws; its spoken names keep the whole figure
    assert "₹11.5k" in shown and "₹11,492" not in shown
    assert "₹11,492" in desk


def test_the_phone_hub_centre_is_short_and_read_out_whole(demo):
    pages, _ = demo
    phone, desk = dials(pages["/mirror"])
    assert ">−₹47.8k<" in phone
    assert 'aria-label="The Scope: four chapters of your story. −₹47,780 your result, before charges' in phone
    assert ">−₹47,780<" in desk


# ---------- nothing overlaps ----------

def test_every_demo_phone_wedge_clears_with_its_spacing_intact(demo):
    _, views = demo
    assert set(views) == set(PAGES)
    for path, [view] in views.items():
        is_home = view["kind"] == "home"
        items, rr = view["items"], G.dial_radii("phone", is_home)
        sec = G.sectors(len(items), is_home)
        z = G.SIZES["phone"]
        sizes = view.get("figSizes") or (z["figSizesHome"] if is_home else z["figSizesChapter"])
        lay = G.layout_contents(items, sec, rr, sizes)
        for i, b in enumerate(lay["blocks"]):
            clear = G.block_clearance(sec["slices"][i], sec["span"], lay["radius"][i], b, rr)
            assert clear >= FIT_ON_A_PHONE, (path, items[i]["name"], round(clear, 1))


def test_the_desktop_dials_are_drawn_as_on_main(demo):
    pages, _ = demo
    for path in PAGES:
        assert sha(dials(pages[path])[1]) == DESKTOP_ON_MAIN[path], path


def test_a_phone_figure_can_step_down_to_13px():
    # A hub answer goes one step further: "100 of 100" over "made money" clears only at 12.
    assert G.SIZES["phone"]["figSizesChapter"][-1] == 13 and D.HUB_FIG_SIZES_PHONE[-2:] == [13, 12]
    css = (P.ROOT if hasattr(P, "ROOT") else __import__("pathlib").Path(__file__).parents[3])
    text = (css / "services/production/api/static/css/components.css").read_text()
    assert re.search(r"\.scope__figure--s13 \{ font-size: 13px; \}", text)
    assert re.search(r"\.scope__figure--s12 \{ font-size: 12px; \}", text)
