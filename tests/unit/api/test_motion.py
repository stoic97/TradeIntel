"""Motion (handoff 7, Phase 3; T6): the parts motion.css cannot do alone.

The transitions are cross-document View Transitions that motion.css plays from the
class the server puts on <html>; test_scope_* hold the links' ?enter= and the class.
This file holds motion.js: loaded early enough to be ready before the first frame,
and its pure parts - which hints leave the address, which figures count and how -
run under Node, the way the geometry port's cases were recorded. Where Node is not
installed the script's tests are skipped, and say so; the layout's are not.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.unit.api.test_layout import PLAIN, render

SCRIPT = Path("services/production/api/static/js/motion.js")
MOTION_CSS = Path("services/production/api/static/css/motion.css")

node = pytest.mark.skipif(shutil.which("node") is None, reason="Node is not installed")


def run(expression: str):
    """Evaluate an expression against motion.js's exports (as `m`) under Node."""
    program = f"const m = require({json.dumps(str(SCRIPT.resolve()))});" \
              f"process.stdout.write(JSON.stringify({expression}));"
    done = subprocess.run(["node", "-e", program], capture_output=True, text=True,
                          check=True, timeout=30)
    return json.loads(done.stdout)


def test_the_script_loads_in_the_head_without_defer():
    """pagereveal fires before the first frame: a deferred script can miss it, and a
    page come back to would replay the motion of the tap that first opened it."""
    html = render(PLAIN)
    head = html.split("</head>")[0]
    assert '<script src="/static/js/motion.js"></script>' in head
    assert head.index("motion.js") < head.index("htmx.min.js")


def test_the_kits_motion_is_what_plays():
    css = MOTION_CSS.read_text()
    assert "@view-transition { navigation: auto; }" in css
    assert "@media (prefers-reduced-motion: reduce)" in css


@node
def test_a_shown_page_drops_its_motion_hints_and_keeps_the_rest():
    cases = {
        "http://x/mirror/chapter/2?enter=in&tap=2": "/mirror/chapter/2",
        "http://x/mirror?enter=out&tap=3": "/mirror",
        "http://x/mirror/chapter/1?enter=back&fact=2": "/mirror/chapter/1",
        "http://x/mirror/fact/share?enter=lens": "/mirror/fact/share",
        "http://x/mirror/fact/share?enter=lens&x=1#t": "/mirror/fact/share?x=1#t",
        "http://x/mirror/fact/share": None,  # nothing to drop: the address is left alone
    }
    got = run("[" + ",".join(f"m.withoutHints({json.dumps(u)})" for u in cases) + "]")
    assert got == list(cases.values())


@node
def test_only_a_whole_number_counts():
    cases = {
        "96%": {"to": 96, "suffix": "%"},
        " 10 ": {"to": 10, "suffix": ""},
        "15.8%": None,     # a decimal is shown as it is
        "3.0": None,
        "−₹24,000": None,  # a rupee figure is shown as it is (kit: fade only)
        "—": None,         # a state
        "4·6": None,
        "": None,
    }
    got = run("[" + ",".join(f"m.countable({json.dumps(t)})" for t in cases) + "]")
    assert got == list(cases.values())


@node
def test_a_count_starts_at_nothing_and_ends_on_the_value():
    frames = run("[0, 100, 300, 599, 600, 900].map(t => m.frame(96, t))")
    assert frames[0] == 0 and frames[-2:] == [96, 96]
    assert frames == sorted(frames)  # never goes back
    assert run("m.COUNT_MS") == 600  # handoff 7


@node
def test_figures_count_on_the_dial_opening_and_on_a_fact_rising():
    got = run('["vt-in vt-tap-2", "vt-lens", "vt-out vt-tap-1", "vt-back", ""]'
              ".map(c => m.countSelector(c))")
    assert got == [".scope__figure", ".fact__figure .num", None, None, None]
