"""TICKET-992: one chart toolkit every Scope chart draws with.

Six charts are coming, and the home card (987) already wrote its own axis label, ticks and
axis drawing. If each chart copies that they drift: one writes -₹47,500 as "-₹48k", another
doesn't. So the pieces live in one module of pure functions, and the card draws through it
and renders byte for byte as it did. All values here are made up.
"""
from __future__ import annotations

import ast
import hashlib
import importlib
import importlib.util
import re
from decimal import Decimal
from itertools import pairwise
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from markupsafe import Markup

from services.production.api.app import create_app
from services.production.api.figures import Figure
from tests.helpers.upload import CSRF, sign_up

D = Decimal
MINUS = "\u2212"
ROOT = Path(__file__).resolve().parents[3]
MODULE = ROOT / "services" / "production" / "api" / "charts.py"
APP_CSS = ROOT / "services" / "production" / "api" / "static" / "css" / "app.css"


def charts():
    assert importlib.util.find_spec("services.production.api.charts"), "no services/production/api/charts.py"
    return importlib.import_module("services.production.api.charts")


# ---------- 1. one module of pure functions ----------

def test_the_toolkit_is_one_module_with_nothing_but_drawing_in_it():
    c = charts()
    for name in ("short", "ticks", "axis", "time_labels", "cell_tone", "hatch", "text_table"):
        assert callable(getattr(c, name, None)), name
    tree = ast.parse(MODULE.read_text(encoding="utf-8"))
    imported = {n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
    imported |= {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    for banned in ("fastapi", "starlette", "sqlalchemy", "jinja2", "services.production.db",
                   "services.production.api.templating"):
        assert not any(m == banned or m.startswith(banned + ".") for m in imported), banned


# ---------- short: the axis label ----------

@pytest.mark.parametrize("value, said", [
    ("0", "₹0"),
    ("999", "₹999"), ("-999", f"{MINUS}₹999"),
    ("1000", "₹1k"), ("-1000", f"{MINUS}₹1k"),
    ("47500", "₹47.5k"), ("-47500", f"{MINUS}₹47.5k"),
    ("100000", "₹1L"), ("-100000", f"{MINUS}₹1L"),
    ("103439", "₹1.0L"), ("-103439", f"{MINUS}₹1.0L"),
    ("120000", "₹1.2L"),
])
def test_short_writes_an_axis_label_as_a_trader_reads_one(value, said):
    assert charts().short(D(value)) == said


def test_a_half_thousand_is_never_rounded_up_to_the_next_thousand():
    assert charts().short(D("-47500")) != f"{MINUS}₹48k"


# ---------- ticks ----------

def _steps_ok(lo, hi, tick):
    mantissa = tick / D(10) ** tick.adjusted()
    assert mantissa in (D(1), D(2), D("2.5"), D(5)), tick
    assert lo % tick == 0 and hi % tick == 0
    assert 3 <= (hi - lo) / tick <= 7


def test_ticks_on_a_range_holding_zero():
    lo, hi, tick = charts().ticks(D("-4300"), D("12100"))
    _steps_ok(lo, hi, tick)
    assert lo <= D("-4300") and hi >= D("12100") and lo < 0 < hi


def test_ticks_on_an_all_negative_range():
    lo, hi, tick = charts().ticks(D("-23950"), D("-2100"))
    _steps_ok(lo, hi, tick)
    assert lo <= D("-23950") and D("-2100") <= hi <= 0


def test_ticks_on_a_tiny_range_never_step_below_a_rupee():
    lo, hi, tick = charts().ticks(D("10"), D("12"))
    assert tick == 1 and lo <= 10 and hi >= 12
    lo, hi, tick = charts().ticks(D("5"), D("5"))
    assert tick >= 1 and lo <= 5 <= hi


# ---------- axis ----------

def _y(lo, hi):
    return lambda v: 12 + float((hi - v) / (hi - lo)) * 200


def test_axis_draws_grid_zero_reference_and_the_last_tag_by_sign():
    c = charts()
    lo, hi, tick = D("-10000"), D("20000"), D("5000")
    back, front = c.axis(lo, hi, tick, _y(lo, hi), left=6, right=58, width=358,
                         ref=(D("15000"), "Your high ₹15,000"), last=D("-2000"))
    assert isinstance(back, Markup) and isinstance(front, Markup)
    assert back.count('class="ch-grid"') == 7
    assert back.count('class="ch-axis"') == 7 and ">₹20k<" in back and f">{MINUS}₹10k<" in back
    assert back.count('class="ch-zero"') == 1
    assert 'class="ch-ref"' in back and "Your high ₹15,000" in back
    assert 'class="ch-last ch-last--loss"' in front and f">{MINUS}₹2k<" in front
    back2, front2 = c.axis(D(5000), D(20000), tick, _y(D(5000), D(20000)), left=6, right=58, width=358,
                           last=D(12000))
    assert "ch-zero" not in back2 and "ch-ref" not in back2 and "ch-last--gain" in front2


# ---------- time_labels ----------

def _texts(labels):
    return [lab.text for lab in labels]


def _gaps_ok(labels, gap=28):
    xs = [lab.x for lab in labels]
    assert all(b - a >= gap for a, b in pairwise(xs)), xs


def test_month_labels_on_102_weeks_skip_collisions_and_january_shows_its_year():
    from datetime import date, timedelta
    c = charts()
    start = date(2024, 9, 2)
    step = (358 - 6 - 58) / 102
    points = [(6 + step * (i + .5), (start + timedelta(weeks=i)).isoformat()) for i in range(102)]
    labels = c.time_labels(points, kind="month", y=294)
    _gaps_ok(labels)
    assert "2025" in _texts(labels) and "2026" in _texts(labels)
    assert all(t in ("2025", "2026") or re.fullmatch(r"[A-Z][a-z]{2}", t) for t in _texts(labels))
    assert len(labels) < 24  # 23 months would collide at this width


def test_minute_of_day_labels_for_a_trading_session():
    c = charts()
    minutes = list(range(9 * 60 + 15, 15 * 60 + 31, 15))  # 09:15 to 15:30
    step = (358 - 6 - 58) / len(minutes)
    labels = c.time_labels([(6 + step * (i + .5), m) for i, m in enumerate(minutes)], kind="minute", y=294)
    _gaps_ok(labels)
    assert _texts(labels)[0] == "09:15"
    assert all(re.fullmatch(r"\d\d:\d\d", t) for t in _texts(labels))


def test_minute_offsets_after_an_entry():
    c = charts()
    offsets = list(range(0, 31, 5))
    step = (358 - 6 - 58) / len(offsets)
    labels = c.time_labels([(6 + step * (i + .5), m) for i, m in enumerate(offsets)], kind="offset", y=294)
    assert _texts(labels) == ["0", "5", "10", "15", "20", "25", "30"]


# ---------- cell_tone, and colour in one place ----------

def test_cell_tone_colours_rupees_by_sign_in_four_steps():
    c = charts()
    scale = D(4000)
    assert c.cell_tone(D(1000), scale) == "ch-cell ch-cell--gain-1"
    assert c.cell_tone(D(2000), scale) == "ch-cell ch-cell--gain-2"
    assert c.cell_tone(D(3000), scale) == "ch-cell ch-cell--gain-3"
    assert c.cell_tone(D(4000), scale) == "ch-cell ch-cell--gain-4"
    assert c.cell_tone(D(9000), scale) == "ch-cell ch-cell--gain-4"
    assert c.cell_tone(D(-1), scale) == "ch-cell ch-cell--loss-1"
    assert c.cell_tone(D(-3500), scale) == "ch-cell ch-cell--loss-4"
    assert c.cell_tone(Figure(D(-2000), "rupees"), scale) == "ch-cell ch-cell--loss-2"


def test_a_zero_or_empty_cell_is_the_surface():
    c = charts()
    for value in (D(0), None, Figure(D(0), "rupees")):
        assert c.cell_tone(value, D(4000)) == "ch-cell ch-cell--surface"


def test_counts_and_rates_are_never_coloured():
    c = charts()
    for value in (12, Figure(12, "trades"), Figure(43, "percent"), 0.43, Figure(D("0.43"), "of 100")):
        assert c.cell_tone(value, D(4000)) == "ch-cell ch-cell--ink", value


# ---------- hatch ----------

def test_hatch_is_the_clock_s_own_pattern():
    out = charts().hatch(10, 20, 30, 40)
    assert out == Markup('<rect x="10.0" y="20.0" width="30.0" height="40.0" class="chart__hatch"/>')


# ---------- text_table ----------

def test_text_table_writes_every_figure_through_figure():
    c = charts()
    html = c.text_table([["Mon", Figure(D(-1500), "rupees"), Figure(7, "trades")]],
                        ["Day", "Result", "Trades"], caption="Every day as numbers")
    assert html.startswith('<table class="table ch-table">')
    assert "<caption>Every day as numbers</caption>" in html
    assert "<th>Day</th>" in html and f"{MINUS}₹1,500" in html and ">7<" in html
    with pytest.raises(TypeError):
        c.text_table([["Mon", D(-1500)]], ["Day", "Result"])


# ---------- 5. no script, no new CSS file ----------

def test_every_class_the_toolkit_draws_is_styled_in_one_app_css_block():
    css = APP_CSS.read_text(encoding="utf-8")
    assert css.count("/* charts toolkit */") == 1
    block = css.split("/* charts toolkit */", 1)[1].split("\n/*", 1)[0]
    drawn = set(re.findall(r'\bch-[a-z0-9-]+', MODULE.read_text(encoding="utf-8")))
    drawn = {d for d in drawn if not d.endswith("-")}
    assert drawn, "the toolkit draws no classes"
    for cls in drawn | {f"ch-cell--{t}-{n}" for t in ("gain", "loss") for n in range(1, 5)}:
        assert f".{cls}" in block, cls
    assert "<script" not in MODULE.read_text(encoding="utf-8")
    css_files = sorted(p.name for p in APP_CSS.parent.glob("*.css"))
    assert css_files == ["app.css", "components.css", "fonts.css", "motion.css", "tokens.css"], css_files


# ---------- 2. the home card draws through it, byte for byte ----------

# sha256 of the card's HTML for every book and timeframe on the demo file, taken on 987's
# branch before the card used the toolkit. The demo file is synthetic.
BEFORE = {
    "all/d": "0de84ee2fe1ba980a63acc449b528b569520aad70285d1ec92a6d714f64a9ac7",
    "all/w": "123d83ce13e6a879dfaed25ab6c0ed2db83ca382943515de8eb1f691949a885c",
    "all/m": "390f2b1a586a1609e2524712306efb923329d2eea598af42b6c782055f8742f6",
    "crude-options/d": "e96f4538e617eacc15866359fdd8dd0a2a94dfab138e9d3755a629ccdcc1cb23",
    "crude-options/w": "1f78c57df264b611cee51957b7ebe5fcf77a545b7bf7eae2bc192a531dc246c7",
    "crude-options/m": "fa1fbfc2e0a2b9dd6ce93fd48fb242be8d964bf69e2182730529fba87cad7c84",
    "nifty-options/d": "2baa3f20b843f313e3daf8f37d63f0720d7480be6db6e0124080602383ce4cdd",
    "nifty-options/w": "e0f80c18007b68f7a7287f8f418323ff215973801d2aa0cdc3d506a51c822314",
    "nifty-options/m": "d254898f74f3c04018606d957a4668db370c9d9ab0006bc0d903d0ceaf1a3230",
    "default": "123d83ce13e6a879dfaed25ab6c0ed2db83ca382943515de8eb1f691949a885c",
}


def _card(html):
    return re.search(r'<section[^>]*id="how".*?</section>', html, re.DOTALL).group(0)


def test_the_home_card_draws_through_the_toolkit():
    src = (ROOT / "services" / "production" / "api" / "how_you_got_here.py").read_text(encoding="utf-8")
    assert "from services.production.api import charts" in src or "import charts" in src
    assert "def short(" not in src and "def _ticks(" not in src


def test_the_home_card_renders_byte_for_byte_as_before(engine):
    client = sign_up(TestClient(create_app()), engine, "D-1", "visitor")
    token = CSRF.search(client.get("/upload").text).group(1)
    client.post("/upload/demo", data={"csrf_token": token})
    now = {"default": hashlib.sha256(_card(client.get("/").text).encode()).hexdigest()}
    for key in BEFORE:
        if key == "default":
            continue
        book, tf = key.split("/")
        now[key] = hashlib.sha256(_card(client.get(f"/?book={book}&tf={tf}").text).encode()).hexdigest()
    assert now == BEFORE
